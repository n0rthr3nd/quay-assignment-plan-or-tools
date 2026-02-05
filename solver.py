"""BAP + QCAP solver using Google OR-Tools CP-SAT."""

from ortools.sat.python import cp_model

from models import Berth, Problem, Solution, Vessel, VesselSolution


def solve(problem: Problem, time_limit_seconds: int = 60) -> Solution:
    """Solve the integrated BAP + QCAP problem.

    Args:
        problem: The problem instance to solve.
        time_limit_seconds: Maximum solver time.

    Returns:
        A Solution object with berth positions, schedules, and crane assignments.
    """
    model = cp_model.CpModel()
    berth = problem.berth
    vessels = problem.vessels
    T = problem.num_shifts
    n = len(vessels)

    # =============================================
    # CONSTANTS
    # =============================================
    GAP = 40  # Minimum distance (meters) between vessels and from berth edges

    # --- Spatial discretization for depth constraints ---
    # We discretize berth positions in 1-meter increments.
    # For depth constraints, we precompute valid positions per vessel.
    valid_positions = {}
    for i, v in enumerate(vessels):
        valid_positions[i] = []
        # Enforce boundary margins: start >= GAP, end <= Length - GAP
        start_p = GAP
        end_p = berth.length - v.loa - GAP
        
        # Ensure the range is valid (start_p <= end_p)
        if start_p <= end_p:
            for p in range(start_p, end_p + 1):
                # Check depth at all meters the vessel occupies
                min_depth = min(berth.get_depth_at(p + m) for m in range(v.loa))
                if min_depth >= v.draft:
                    valid_positions[i].append(p)
        
        if not valid_positions[i]:
            print(f"WARNING: No valid berth position for vessel {v.name} "
                  f"(draft={v.draft}, loa={v.loa}) with {GAP}m margins")
            return Solution([], 0, "INFEASIBLE")

    # =============================================
    # DECISION VARIABLES
    # =============================================

    # 1. Berth position p_i (integer variable, meter on the berth)
    pos = {}
    for i, v in enumerate(vessels):
        pos[i] = model.new_int_var(
            min(valid_positions[i]),
            max(valid_positions[i]),
            f"pos_{v.name}",
        )
        # Restrict to valid positions (depth constraint)
        if len(valid_positions[i]) < (max(valid_positions[i]) - min(valid_positions[i]) + 1):
            model.add_allowed_assignments([pos[i]], [[p] for p in valid_positions[i]])

    # 2. Start/End shifts
    start = {}
    end = {}
    duration = {}
    for i, v in enumerate(vessels):
        start[i] = model.new_int_var(v.etw, T - 1, f"start_{v.name}")
        end[i] = model.new_int_var(v.etw + 1, T, f"end_{v.name}")
        duration[i] = model.new_int_var(1, T - v.etw, f"dur_{v.name}")
        model.add(end[i] == start[i] + duration[i])

    # 3. Crane assignment q_{i,t}: cranes for vessel i in shift t
    q = {}
    for i, v in enumerate(vessels):
        for t in range(T):
            q[i, t] = model.new_int_var(0, v.max_cranes, f"q_{v.name}_{t}")

    # =============================================
    # CONSTRAINTS
    # =============================================

    # --- 4.1 Spatial constraints ---

    # Berth length: vessel must fit within berth (redundant with domain but explicit)
    # Also enforce 40m margin from edges
    for i, v in enumerate(vessels):
        model.add(pos[i] >= GAP)
        model.add(pos[i] + v.loa <= berth.length - GAP)

    # --- 4.2 Non-overlap: spatial + temporal ---
    # Two vessels cannot overlap in BOTH space and time simultaneously.
    # We use interval variables and no-overlap-2d constraint.
    # We increase the spatial size by GAP to enforce distance BETWEEN vessels.
    
    # Create interval variables for the 2D no-overlap constraint
    x_intervals = []  # spatial intervals
    y_intervals = []  # temporal intervals

    for i, v in enumerate(vessels):
        # "Padding" the vessel size with GAP ensures that if two intervals don't overlap,
        # their start positions are at least (LOA + GAP) apart.
        x_size = v.loa + GAP
        x_interval = model.new_fixed_size_interval_var(pos[i], x_size, f"x_int_{v.name}")
        x_intervals.append(x_interval)

        y_interval = model.new_interval_var(
            start[i], duration[i], end[i], f"y_int_{v.name}"
        )
        y_intervals.append(y_interval)

    model.add_no_overlap_2d(x_intervals, y_intervals)

    # --- 4.3 Temporal constraints ---

    # Vessel cannot start before its earliest arrival
    for i, v in enumerate(vessels):
        model.add(start[i] >= v.etw)

    # --- 4.4 Crane assignment constraints ---
    # For each vessel i and shift t, define whether the vessel is active.
    active = {}
    for i, v in enumerate(vessels):
        for t in range(T):
            active[i, t] = model.new_bool_var(f"active_{v.name}_{t}_v2")

            # active[i,t] == 1  <=>  start[i] <= t AND t < end[i]
            # We linearize with:
            #   active => start[i] <= t
            #   active => t < end[i]  (i.e., t + 1 <= end[i])
            #   NOT active => (start[i] > t) OR (t >= end[i])
            model.add(start[i] <= t).only_enforce_if(active[i, t])
            model.add(end[i] >= t + 1).only_enforce_if(active[i, t])

            # If not active, at least one bound must be violated.
            # start[i] > t  OR  end[i] <= t
            b1 = model.new_bool_var(f"b1_{v.name}_{t}")
            b2 = model.new_bool_var(f"b2_{v.name}_{t}")
            model.add(start[i] > t).only_enforce_if(b1)
            model.add(end[i] <= t).only_enforce_if(b2)
            model.add_bool_or([b1, b2]).only_enforce_if(~active[i, t])

            # Cranes only when active
            model.add(q[i, t] == 0).only_enforce_if(~active[i, t])

            # Shift availability: if the vessel is not available in this shift
            if v.available_shifts is not None and t not in v.available_shifts:
                model.add(q[i, t] == 0)
                model.add(active[i, t] == 0)

    # At least 1 crane when active (vessel must be worked on)
    for i, v in enumerate(vessels):
        for t in range(T):
            model.add(q[i, t] >= 1).only_enforce_if(active[i, t])

    # Workload fulfillment: sum of (cranes * productivity) >= workload
    for i, v in enumerate(vessels):
        model.add(
            sum(q[i, t] * v.productivity for t in range(T)) >= v.workload
        )

    # Max cranes per vessel (already bounded by variable domain, but explicit)
    for i, v in enumerate(vessels):
        for t in range(T):
            model.add(q[i, t] <= v.max_cranes)

    # Global crane capacity per shift
    for t in range(T):
        model.add(
            sum(q[i, t] for i in range(n)) <= problem.total_cranes_per_shift[t]
        )

    # =============================================
    # OBJECTIVE FUNCTION
    # =============================================
    # Minimize a weighted combination of:
    #   1. Total waiting/turnaround time: sum(end[i] - etw[i])
    #   2. Makespan: max(end[i])
    #   3. Total crane usage (secondary)

    makespan = model.new_int_var(0, T, "makespan")
    for i in range(n):
        model.add(makespan >= end[i])

    total_turnaround = model.new_int_var(0, T * n * 2, "total_turnaround")
    turnaround_terms = []
    
    total_waiting_time = model.new_int_var(0, T * n, "total_waiting_time")
    waiting_terms = []
    
    for i, v in enumerate(vessels):
        # Turnaround calculation: end - etw
        t_i = model.new_int_var(0, T, f"turnaround_{v.name}")
        model.add(t_i == end[i] - v.etw)
        turnaround_terms.append(t_i)
        
        # Waiting time calculation: start - etw
        w_i = model.new_int_var(0, T, f"waiting_{v.name}")
        model.add(w_i == start[i] - v.etw)
        waiting_terms.append(w_i)
        
    model.add(total_turnaround == sum(turnaround_terms))
    model.add(total_waiting_time == sum(waiting_terms))

    total_cranes_used = model.new_int_var(0, T * n * 20, "total_cranes")
    model.add(total_cranes_used == sum(q[i, t] for i in range(n) for t in range(T)))

    # Weighted objective: prioritize turnaround, then makespan, then crane compactness
    # Added W_WAITING to prioritize starting as close to ETW as possible.
    W_TURNAROUND = 10
    W_WAITING = 20  # High penalty for delaying the start
    W_MAKESPAN = 5
    W_CRANES = 1

    model.minimize(
        W_TURNAROUND * total_turnaround
        + W_WAITING * total_waiting_time
        + W_MAKESPAN * makespan
        + W_CRANES * total_cranes_used
    )

    # =============================================
    # SOLVE
    # =============================================
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.log_search_progress = True
    solver.parameters.num_workers = 8

    status = solver.solve(model)

    status_name = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.UNKNOWN: "UNKNOWN",
    }.get(status, "UNKNOWN")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Solution([], 0, status_name)

    # =============================================
    # EXTRACT SOLUTION
    # =============================================
    vessel_solutions = []
    for i, v in enumerate(vessels):
        cranes_per_shift = {}
        s = solver.value(start[i])
        e = solver.value(end[i])
        for t in range(s, e):
            crane_val = solver.value(q[i, t])
            if crane_val > 0:
                cranes_per_shift[t] = crane_val

        vs = VesselSolution(
            vessel_name=v.name,
            berth_position=solver.value(pos[i]),
            start_shift=s,
            end_shift=e,
            cranes_per_shift=cranes_per_shift,
        )
        vessel_solutions.append(vs)

    return Solution(
        vessel_solutions=vessel_solutions,
        objective_value=solver.objective_value,
        status=status_name,
    )
