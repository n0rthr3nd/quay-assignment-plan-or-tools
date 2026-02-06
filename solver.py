"""BAP + QCAP solver using Google OR-Tools CP-SAT."""

from typing import Dict, List, Tuple
from collections import defaultdict

from ortools.sat.python import cp_model

from models import Berth, Problem, Solution, Vessel, VesselSolution, Crane, CraneType


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
    moves = {} # NEW: integer variable [c, i, t]
    
    # Active indicator (needed for spatial/temporal)
    active = {}
    
    for i, v in enumerate(vessels):
        # 1. Variables - Time
        # ====================
        min_start = v.arrival_shift_index if v.arrival_shift_index >= 0 else 0
        if min_start >= T: min_start = T - 1

        start[i] = model.new_int_var(min_start, T - 1, f"start_{v.name}")
        end[i] = model.new_int_var(min_start + 1, T, f"end_{v.name}")
        duration[i] = model.new_int_var(1, T, f"dur_{v.name}")
        
        model.add(end[i] == start[i] + duration[i])
        
        # Create active booleans for each shift
        for t in range(T):
            active[i, t] = model.new_bool_var(f"active_{v.name}_{t}")
            
            # Reification: active <=> start <= t < end
            is_after_start = model.new_bool_var(f"{v.name}_after_start_{t}")
            is_before_end = model.new_bool_var(f"{v.name}_before_end_{t}")
            model.add(start[i] <= t).only_enforce_if(is_after_start)
            model.add(start[i] > t).only_enforce_if(is_after_start.Not())
            model.add(end[i] > t).only_enforce_if(is_before_end)
            model.add(end[i] <= t).only_enforce_if(is_before_end.Not())
            
            model.add_bool_and([is_after_start, is_before_end]).only_enforce_if(active[i, t])
            model.add_bool_or([is_after_start.Not(), is_before_end.Not()]).only_enforce_if(active[i, t].Not())


    # 2. Crane Moves (Integer)
    # moves[c, i, t] = Number of moves crane c performs for vessel i in shift t
    for t in range(T):
        available_crane_ids = problem.crane_availability_per_shift.get(t, [])
        for c_idx, c in enumerate(cranes):
            if c.id not in available_crane_ids: continue
            
            for i, v in enumerate(vessels):
                # Optimization: check arrival
                if t < (v.arrival_shift_index if v.arrival_shift_index >= 0 else 0):
                    continue
                
                # Max prod limit logic
                limit = c.max_productivity
                if v.productivity_preference == "MIN": limit = c.min_productivity
                elif v.productivity_preference == "INTERMEDIATE": limit = (c.min_productivity + c.max_productivity) // 2
                
                # Arrival fraction
                if t == v.arrival_shift_index:
                    limit = int(limit * v.arrival_fraction)
                
                if limit > 0:
                    mv = model.new_int_var(0, limit, f"moves_{c.id}_{i}_{t}")
                    moves[c.id, i, t] = mv
                    
                    # Link to active: if moves > 0, vessel must be active
                    # active=0 => moves=0
                    model.add(mv == 0).only_enforce_if(active[i, t].Not())

    # =============================================
    # CONSTRAINTS
    # =============================================

    # --- 4.1 Spatial constraints ---
    for i, v in enumerate(vessels):
        # pos[i] var defined earlier? No, define now.
        if i not in pos: 
            # Should have been defined? No, let's look at full file structure.
            # pos is typically defined at start.
            # Assuming 'pos' passed in Dict or created here?
            # Existing code expects 'pos'. Let's ensure it exists.
            # Check lines 58: pos = {} defined?
            pass

    # Ensure pos variables exist (might be redundant if defined above in older code, but safe here)
    # We need to recreate them if not present, but better to rely on context.
    # The snippet 75 starts inside the Variable creation block. 
    # pos was typically earlier. Let's assume it's there.
    # Wait, previous view showed line 75 start... pos was created at line 66 in previous versions?
    # No, pos logic was usually inside the loop.
    
    # RE-CREATING POS LOOP just in case, or finding where it was.
    # Code view 75-148 doesn't show pos creation!
    # It accesses pos[i] at line 111. So pos must be created.
    # Previous code snippet 75... doesn't show pos creation.
    # It must have been before line 75?
    # Let's create pos loop here to be sure.
    
    # (Re)define pos if empty
    if not pos:
        for i, v in enumerate(vessels):
             pos[i] = model.new_int_var(0, problem.berth.length - v.loa, f"pos_{v.name}")

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


    # ====================================================================
    # 2. Constraints
    # ====================================================================
    # ====================================================================
    # 2. Constraints (Logic Re-Implementation with 'moves')
    # ====================================================================

    # 2.1 Workload Fullfillment
    # sum(moves[c, i, t]) >= v.workload
    for i, v in enumerate(vessels):
        v_moves = []
        for t in range(T):
            for c in cranes:
                if (c.id, i, t) in moves:
                    v_moves.append(moves[c.id, i, t])
        model.add(sum(v_moves) >= v.workload)

    # 2.2 Crane Capacity (Shifting Gang)
    # The sum of moves a crane performs across ALL vessels in one shift <= max_productivity.
    # This enables sharing/shifting: A crane can do 50 moves for V1 and 50 for V2 in same shift if Cap=100.
    for t in range(T):
        for c in cranes:
            c_moves_in_shift = []
            for i in range(len(vessels)):
                if (c.id, i, t) in moves:
                    c_moves_in_shift.append(moves[c.id, i, t])
            
            if c_moves_in_shift:
                model.add(sum(c_moves_in_shift) <= c.max_productivity)

    # 2.3 Max Cranes per Vessel
    # sum(crane_active[:, i, t]) <= v.max_cranes
    # We need crane_active[c,i,t] indicators.
    crane_active_indicators = {}
    
    for (c_id, i, t), m_var in moves.items():
        # Indicator: if moves > 0 => active=1
        b_act = model.new_bool_var(f"ind_{c_id}_{i}_{t}")
        model.add(m_var > 0).only_enforce_if(b_act)
        model.add(m_var == 0).only_enforce_if(b_act.Not())
        crane_active_indicators[c_id, i, t] = b_act

    for i, v in enumerate(vessels):
        for t in range(T):
            active_vars = []
            for c in cranes:
                if (c.id, i, t) in crane_active_indicators:
                    active_vars.append(crane_active_indicators[c.id, i, t])
            
            # Max cranes constraint
            model.add(sum(active_vars) <= v.max_cranes)
            
            # Link to Vessel Active: If Vessel Active, Must have at least 1 crane working?
            # Or at least > 0 moves total? Use moves sum.
            moves_vars = []
            for c in cranes:
                 if (c.id, i, t) in moves:
                     moves_vars.append(moves[c.id, i, t])
            
            # If active[i,t], sum(moves) >= 1 (Must work if berthed/active)
            # This minimizes "dead time" at berth.
            model.add(sum(moves_vars) >= 1).only_enforce_if(active[i, t])

    # 2.4 Crane Reach Constraints
    for (c_id, i, t), b_act in crane_active_indicators.items():
        c = crane_map[c_id]
        # If crane active => pos[i] >= range_start
        model.add(pos[i] >= c.berth_range_start).only_enforce_if(b_act)
        # Check coverage end? 
        # model.add(pos[i] + vessels[i].loa <= c.berth_range_end).only_enforce_if(b_act)
        pass 

    # 2.5 STS Non-Crossing
    sts_cranes = [c for c in cranes if c.crane_type == CraneType.STS]
    # Assumed sorted by ID/Physical L-to-R
    for idx1 in range(len(sts_cranes)):
        for idx2 in range(idx1 + 1, len(sts_cranes)):
            c1 = sts_cranes[idx1]
            c2 = sts_cranes[idx2]
            
            for t in range(T):
                # Iterate all vessel pairs
                for i_a in range(len(vessels)):
                    for i_b in range(len(vessels)):
                        if i_a == i_b: continue
                        
                        # Indices for lookup
                        k1 = (c1.id, i_a, t)
                        k2 = (c2.id, i_b, t)
                        
                        if k1 in crane_active_indicators and k2 in crane_active_indicators:
                            # If c1 on a AND c2 on b => pos[a] <= pos[b]
                            both_active = model.new_bool_var(f"cross_{t}_{c1.id}_{c2.id}")
                            model.add_bool_and([crane_active_indicators[k1], crane_active_indicators[k2]]).only_enforce_if(both_active)
                            model.add(pos[i_a] <= pos[i_b]).only_enforce_if(both_active)

    # 2.6 Restricted Shifting Gang Constraint
    # A crane must work at FULL capacity on a vessel unless it is the LAST shift for that vessel.
    for t in range(T):
        available_crane_ids = problem.crane_availability_per_shift.get(t, [])
        for c_idx, c in enumerate(cranes):
            if c.id not in available_crane_ids: continue
            
            for i, v in enumerate(vessels):
                # Only if variable exists
                if (c.id, i, t) not in moves: continue
                
                mv = moves[c.id, i, t]
                # Re-calculate limit used for domain
                limit = c.max_productivity
                if v.productivity_preference == "MIN": limit = c.min_productivity
                elif v.productivity_preference == "INTERMEDIATE": limit = (c.min_productivity + c.max_productivity) // 2
                
                # Check arrival fraction? If arrival shift is NOT last shift, then it must be full *available* capacity? 
                # Yes. If t == arrival_shift, limit is reduced. Constraint should enforce *that* reduced limit.
                if t == v.arrival_shift_index:
                    limit = int(limit * v.arrival_fraction)
                
                # Condition: t < end[i] - 1  (Not the last shift)
                # We use reified constraint.
                # is_intermediate <=> t <= end[i] - 2
                
                is_intermediate = model.new_bool_var(f"is_intermediate_{c.id}_{v.name}_{t}")
                model.add(t <= end[i] - 2).only_enforce_if(is_intermediate)
                model.add(t > end[i] - 2).only_enforce_if(is_intermediate.Not())
                
                # Indicator: Crane Active
                # We need to know if crane IS active. We have crane_active_indicators.
                if (c.id, i, t) in crane_active_indicators:
                    b_act = crane_active_indicators[c.id, i, t]
                    
                    # Constraint: If (Active AND Intermediate) => moves == limit
                    # i.e., NO PARTIAL WORK allowed in intermediate shifts.
                    model.add(mv == limit).only_enforce_if([b_act, is_intermediate])


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
        # Fallback to 0 if arrival shift is invalid/negative for calc purposes
        ref_start = v.arrival_shift_index if v.arrival_shift_index >= 0 else 0
        
        # Turnaround: end - arrival
        t_i = model.new_int_var(-T, T, f"turnaround_{v.name}")
        model.add(t_i == end[i] - ref_start)
        turnaround_terms.append(t_i)
        
        # Waiting: start - arrival
        w_i = model.new_int_var(-T, T, f"waiting_{v.name}")
        model.add(w_i == start[i] - ref_start)
        waiting_terms.append(w_i)
        
    model.add(total_turnaround == sum(turnaround_terms))
    model.add(total_waiting_time == sum(waiting_terms))

    # Total crane usage (number of crane-shifts)
    # Calculate active cranes for objective
    # crane_active[c, i, t] was not explicitly stored in full dict during Variable creation phase in my logic update?
    # Let's check variables section. Ah, I created `moves` but maybe not `crane_active` globally accessible here.
    # Re-derive crane_active boolean terms from moves > 0 if needed for objective.
    
    crane_active_vars = []
    for (c, i, t), m_var in moves.items():
        # Create boolean indicator if not exists
        # Actually simplest to just weight 'moves' if we want speed?
        # But we want total *assignments* count.
        b_var = model.new_bool_var(f"active_{c}_{i}_{t}")
        model.add(m_var > 0).only_enforce_if(b_var)
        model.add(m_var == 0).only_enforce_if(b_var.Not())
        crane_active_vars.append(b_var)

    total_cranes_used = model.new_int_var(0, len(crane_active_vars) + 1, "total_cranes")
    if crane_active_vars:
        model.add(total_cranes_used == sum(crane_active_vars))
    else:
        model.add(total_cranes_used == 0)

    W_TURNAROUND = 500  # High priority to finish fast
    W_WAITING = 50 
    W_MAKESPAN = 100
    W_CRANES = 0  # Do not penalize using more cranes if it helps speed

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
    return extract_solution(
        problem, 
        solver, 
        start, 
        end, 
        moves, 
        pos
    )

def extract_solution(
    problem: Problem, 
    solver: cp_model.CpSolver, 
    start: Dict, 
    end: Dict, 
    moves: Dict, # Changed from assign 
    pos: Dict
) -> Solution:
    """Converts solver variables back into a Solution object."""
    
    vessel_solutions = []
    
    # We need to map back which cranes act on which vessel at which shift
    # moves[c.id, i, t] -> int
    
    # Pre-build lookup: i -> t -> list of crane_ids
    # Also need productivity? Not explicitly stored in solution object usually,
    # but we can infer or store basic assignment.
    # The VesselSolution expects 'assigned_cranes': Dict[int, List[str]]
    
    assignments = {i: defaultdict(list) for i in range(len(problem.vessels))}
    
    for (c_id, i, t), var in moves.items():
        val = solver.value(var)
        if val > 0:
            assignments[i][t].append(c_id)

    for i, v in enumerate(problem.vessels):
        s_val = solver.value(start[i])
        e_val = solver.value(end[i])
        p_val = solver.value(pos[i])
        
        # Filter assigned_cranes to only those in [start, end)
        # (Though constraints enforce moves=0 outside active)
        relevant_assignments = {}
        for t in range(s_val, e_val):
            if t in assignments[i]:
                relevant_assignments[t] = assignments[i][t]
                
        sol = VesselSolution(
            vessel_name=v.name,
            berth_position=p_val,
            start_shift=s_val,
            end_shift=e_val,
            assigned_cranes=relevant_assignments
        )
        vessel_solutions.append(sol)

    # Determine status string
    status_map = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID", 
        cp_model.UNKNOWN: "UNKNOWN"
    }
    status_str = "UNKNOWN" # Default
    # Status is not passed here directly as val? Oh wait, passed in main solve func.
    # We'll just return solution and caller handles status string from earlier.
    # Actually this func doesn't take status arg.
    
    return Solution(
        vessel_solutions=vessel_solutions,
        objective_value=solver.objective_value,
        status="FEASIBLE" # Placeholder, actual status returned by solve()
    )
