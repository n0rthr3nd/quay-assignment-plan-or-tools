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
    cranes = problem.cranes
    T = problem.num_shifts
    n = len(vessels)
    
    # Map crane id to object for easy lookup
    crane_map = {c.id: c for c in cranes}
    
    # =============================================
    # CONSTANTS
    # =============================================
    GAP = 40  # Minimum distance (meters) between vessels and from berth edges

    # --- Spatial discretization for depth constraints ---
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

    # 3. Crane assignment assign[c_id, i, t]: is crane c assigned to vessel i in shift t?
    # Only create variables if crane is available in that shift
    assign = {} 
    
    # Pre-process available cranes per shift for easier access
    # problem.crane_availability_per_shift is Dict[int, List[str]]
    
    for t in range(T):
        available_crane_ids = problem.crane_availability_per_shift.get(t, [])
        for c_id in available_crane_ids:
            if c_id not in crane_map:
                continue
            for i, v in enumerate(vessels):
                assign[c_id, i, t] = model.new_bool_var(f"assign_{c_id}_{v.name}_{t}")

    # =============================================
    # CONSTRAINTS
    # =============================================

    # --- 4.1 Spatial constraints ---
    for i, v in enumerate(vessels):
        model.add(pos[i] >= GAP)
        model.add(pos[i] + v.loa <= berth.length - GAP)

    # --- 4.2 Non-overlap: spatial + temporal ---
    x_intervals = []
    y_intervals = []

    for i, v in enumerate(vessels):
        x_size = v.loa + GAP
        x_interval = model.new_fixed_size_interval_var(pos[i], x_size, f"x_int_{v.name}")
        x_intervals.append(x_interval)

        y_interval = model.new_interval_var(
            start[i], duration[i], end[i], f"y_int_{v.name}"
        )
        y_intervals.append(y_interval)

    model.add_no_overlap_2d(x_intervals, y_intervals)

    # --- 4.2b Forbidden Zones ---
    for i, v in enumerate(vessels):
        for z in problem.forbidden_zones:
            z_x_interval = model.new_fixed_size_interval_var(
                z.start_berth_position, 
                z.end_berth_position - z.start_berth_position, 
                f"z_x_{z.description}_{i}"
            )
            z_y_interval = model.new_fixed_size_interval_var(
                z.start_shift, 
                z.end_shift - z.start_shift, 
                f"z_y_{z.description}_{i}"
            )
            model.add_no_overlap_2d(
                [x_intervals[i], z_x_interval], 
                [y_intervals[i], z_y_interval]
            )

    # --- 4.3 Temporal constraints ---
    for i, v in enumerate(vessels):
        model.add(start[i] >= v.etw)

    # --- 4.4 Crane assignment constraints ---
    
    # 4.4.1 Active vessel constraints
    active = {}
    for i, v in enumerate(vessels):
        for t in range(T):
            active[i, t] = model.new_bool_var(f"active_{v.name}_{t}")

            # active <=> start <= t < end
            model.add(start[i] <= t).only_enforce_if(active[i, t])
            model.add(end[i] >= t + 1).only_enforce_if(active[i, t])
            
            b1 = model.new_bool_var(f"b1_{v.name}_{t}")
            b2 = model.new_bool_var(f"b2_{v.name}_{t}")
            model.add(start[i] > t).only_enforce_if(b1)
            model.add(end[i] <= t).only_enforce_if(b2)
            model.add_bool_or([b1, b2]).only_enforce_if(~active[i, t])

            # Shift availability
            if v.available_shifts is not None and t not in v.available_shifts:
                model.add(active[i, t] == 0)

    # 4.4.2 Crane assignment logic
    # Iterate over all possible assignments
    for (c_id, i, t), var in assign.items():
        # Crane can only be assigned if vessel is active
        model.add(var == 0).only_enforce_if(~active[i, t])
        
        # Spatial Coverage: if assigned, vessel must be within crane range
        c = crane_map[c_id]
        # range_start <= pos[i]  AND pos[i] + loa <= range_end
        # The user requested specific coverage ranges.
        # We enforce strict containment.
        model.add(pos[i] >= c.berth_range_start).only_enforce_if(var)
        model.add(pos[i] + v.loa <= c.berth_range_end).only_enforce_if(var)
        
        # One vessel per crane per shift
        # Handled globally below, but implicit here is fine too.
        # Actually logic is grouped below.

    # 4.4.3 One vessel per crane per shift
    # Group assignments by crane and shift
    assignments_by_crane_shift = {}
    for (c_id, i, t), var in assign.items():
        if (c_id, t) not in assignments_by_crane_shift:
            assignments_by_crane_shift[c_id, t] = []
        assignments_by_crane_shift[c_id, t].append(var)
    
    for _, vars in assignments_by_crane_shift.items():
        model.add(sum(vars) <= 1)

    # 4.4.4 Max cranes per vessel
    # Group assignments by vessel and shift
    assignments_by_vessel_shift = {}
    for (c_id, i, t), var in assign.items():
        if (i, t) not in assignments_by_vessel_shift:
            assignments_by_vessel_shift[i, t] = []
        assignments_by_vessel_shift[i, t].append(var)

    for i, v in enumerate(vessels):
        for t in range(T):
            if (i, t) in assignments_by_vessel_shift:
                # Max cranes limit
                model.add(sum(assignments_by_vessel_shift[i, t]) <= v.max_cranes)
                
                # At least one crane if active (must be worked on if active)
                # This prevents "active" but 0 cranes, which prolongs duration artificially
                model.add(sum(assignments_by_vessel_shift[i, t]) >= 1).only_enforce_if(active[i, t])
            else:
                # If no cranes *possible* for this vessel in this shift (e.g. no availability),
                # then it cannot be active!
                model.add(active[i, t] == 0)

    # =============================================
    # 4.4.5 Workload fulfillment
    # =============================================
    # Sum of (crane_assigned * crane_productivity) >= workload
    
    # We need to construct the sum efficiently.
    # Group vars by vessel.
    vessel_work = {i: [] for i in range(n)}
    
    for (c_id, i, t), var in assign.items():
        c = crane_map[c_id]
        v = vessels[i]
        
        # Determine productivity based on vessel preference
        productivity = 0
        if v.productivity_preference == "MAX":
            productivity = c.max_productivity
        elif v.productivity_preference == "MIN":
            productivity = c.min_productivity
        else: # INTERMEDIATE
            productivity = (c.min_productivity + c.max_productivity) // 2

        # Multiply var by determined productivity
        vessel_work[i].append(var * productivity)

        
    for i, v in enumerate(vessels):
        if vessel_work[i]:
            model.add(sum(vessel_work[i]) >= v.workload)
        else:
            # If no assignments possible at all? Infeasible.
            print(f"Warning: No possible crane assignments for vessel {v.name}")
            return Solution([], 0, "INFEASIBLE")

    # =============================================
    # 4.5 STS Crane Non-Crossing Constraints
    # =============================================
    # STS cranes must maintain physical order: i < j => pos(crane_i) <= pos(crane_j)
    # We assume 'STS' type cranes are physically ordered by their ID.
    sts_cranes = sorted([c for c in cranes if c.crane_type == "STS"], key=lambda k: k.id)
    
    for idx1 in range(len(sts_cranes)):
        for idx2 in range(idx1 + 1, len(sts_cranes)):
            c1 = sts_cranes[idx1]
            c2 = sts_cranes[idx2]
            
            for t in range(T):
                # For every pair of vessels (v1, v2) assigned to (c1, c2)
                for i1 in range(n):
                    if (c1.id, i1, t) not in assign:
                        continue
                    lit1 = assign[c1.id, i1, t]
                    
                    for i2 in range(n):
                        # Optimization: if i1 == i2, pos[i1] <= pos[i2] is trivial
                        if i1 == i2:
                            continue

                        if (c2.id, i2, t) not in assign:
                            continue
                        lit2 = assign[c2.id, i2, t]
                        
                        # Constraint: if both active, v1 must be left of v2
                        # Since vessels don't overlap, this effectively means v1 is strictly left of v2
                        model.add(pos[i1] <= pos[i2]).only_enforce_if([lit1, lit2])


    # =============================================
    # OBJECTIVE FUNCTION
    # =============================================
    
    makespan = model.new_int_var(0, T, "makespan")
    for i in range(n):
        model.add(makespan >= end[i])

    total_turnaround = model.new_int_var(0, T * n * 2, "total_turnaround")
    turnaround_terms = []
    
    total_waiting_time = model.new_int_var(0, T * n, "total_waiting_time")
    waiting_terms = []
    
    for i, v in enumerate(vessels):
        t_i = model.new_int_var(0, T, f"turnaround_{v.name}")
        model.add(t_i == end[i] - v.etw)
        turnaround_terms.append(t_i)
        
        w_i = model.new_int_var(0, T, f"waiting_{v.name}")
        model.add(w_i == start[i] - v.etw)
        waiting_terms.append(w_i)
        
    model.add(total_turnaround == sum(turnaround_terms))
    model.add(total_waiting_time == sum(waiting_terms))

    # Total crane usage (number of crane-shifts)
    crane_usage_vars = list(assign.values())
    total_cranes_used = model.new_int_var(0, max(1, len(crane_usage_vars)), "total_cranes")
    if crane_usage_vars:
        model.add(total_cranes_used == sum(crane_usage_vars))
    else:
        model.add(total_cranes_used == 0)

    W_TURNAROUND = 10
    W_WAITING = 20
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
        assigned_cranes_map = {} # shift -> list of crane ids
        s = solver.value(start[i])
        e = solver.value(end[i])
        
        for t in range(s, e):
            # assigned_cranes_map initialization moved inside loop to only capture active shifts?
            # Or should return dict for shifts
            current_cranes = []
            
            # Check assignments
            for (c_id, v_idx, shift), var in assign.items():
                if v_idx == i and shift == t:
                    if solver.value(var) == 1:
                        current_cranes.append(c_id)
            
            if current_cranes:
                assigned_cranes_map[t] = current_cranes

        vs = VesselSolution(
            vessel_name=v.name,
            berth_position=solver.value(pos[i]),
            start_shift=s,
            end_shift=e,
            assigned_cranes=assigned_cranes_map,
        )
        vessel_solutions.append(vs)

    return Solution(
        vessel_solutions=vessel_solutions,
        objective_value=solver.objective_value,
        status=status_name,
    )
