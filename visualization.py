"""Visualization for BAP + QCAP solutions: Space-Time Gantt chart."""

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from collections import defaultdict

from models import Problem, Solution


COLORS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    "#86bcb6", "#8cd17d", "#b6992d", "#499894", "#d37295",
]


def plot_solution(problem: Problem, solution: Solution, output_path: str = "gantt.png"):
    """Generate a Space-Time Gantt chart of the solution.

    X-axis: Shifts (time)
    Y-axis: Berth position (meters)
    Each vessel is drawn as a rectangle (position x time) with crane info.
    """
    if not solution.vessel_solutions:
        print("No solution to plot.")
        return

    # Create a figure with two subplots: Main Gantt and Depth Profile
    fig, (ax, ax_depth) = plt.subplots(
        1, 2, 
        sharey=True, 
        figsize=(16, 8), 
        gridspec_kw={'width_ratios': [7, 1], 'wspace': 0.05}
    )

    vessels_by_name = {v.name: v for v in problem.vessels}

    # Draw forbidden zones first
    added_forbidden_label = False
    for z in problem.forbidden_zones:
        width = z.end_shift - z.start_shift
        height = z.end_berth_position - z.start_berth_position
        
        # Only add label once for the legend
        label = "Restricted Zone" if not added_forbidden_label else None
        
        rect = mpatches.Rectangle(
            (z.start_shift, z.start_berth_position),
            width, height,
            hatch='//', facecolor='red', alpha=0.2, edgecolor='darkred',
            label=label
        )
        ax.add_patch(rect)
        
        # Add text description
        ax.text(
            z.start_shift + width/2, z.start_berth_position + height/2,
            z.description,
            ha='center', va='center', color='darkred', 
            fontsize=8, fontweight='bold', clip_on=True
        )
        
        if label:
            added_forbidden_label = True

    for idx, vs in enumerate(solution.vessel_solutions):
        vessel = vessels_by_name[vs.vessel_name]
        color = COLORS[idx % len(COLORS)]

        # Add a small visual margin to prevent overlap with grid lines
        margin_x = 0.1  # 10% of a shift width
        margin_y = 2.0  # 2 meters vertical gap (adjust based on typical LOA)

        x = vs.start_shift + margin_x
        y = vs.berth_position + margin_y
        width = (vs.end_shift - vs.start_shift) - (2 * margin_x)
        height = vessel.loa - (2 * margin_y)

        # Ensure height doesn't become negative if vessel is tiny (unlikely)
        if height < 1:
            height = vessel.loa
            y = vs.berth_position

        rect = mpatches.FancyBboxPatch(
            (x, y), width, height,
            boxstyle="round,pad=0.02", # Reduced pad slightly to be tighter
            facecolor=color, edgecolor="black", linewidth=1.2, alpha=0.85,
        )
        ax.add_patch(rect)

        # Label with vessel name, crane count per shift, and productivity details
        # We need crane_map to lookup productivity
        crane_map = {c.id: c for c in problem.cranes}
        pref = vessel.productivity_preference
        
        # Build detailed crane string
        # Format per shift: "T0: 2(240)" -> 2 cranes, total 240 prod
        crane_details = []
        for t in range(vs.start_shift, vs.end_shift):
            c_list = vs.assigned_cranes.get(t, [])
            if not c_list:
                continue
                
            total_prod = 0
            for cid in c_list:
                if cid in crane_map:
                    c = crane_map[cid]
                    if pref == "MAX":
                        total_prod += c.max_productivity
                    elif pref == "MIN":
                        total_prod += c.min_productivity
                    else:
                        total_prod += (c.min_productivity + c.max_productivity) // 2
            
            # Compact format: "S{t}:{count}c" or just count
            # Given space constraints, maybe just list count and average prod?
            # Or just list of cranes per shift is too long.
            # Let's show: "S3:2(230)"
            crane_details.append(f"S{t}:{len(c_list)}({total_prod})")
        
        # Wrap crane details if too long
        crane_str = "\n".join(crane_details)
        
        label = f"{vs.vessel_name}\n{vessel.productivity_preference}\n{crane_str}"
        
        ax.text(
            x + width / 2, y + height / 2, label,
            ha="center", va="center", fontsize=6, fontweight="bold", color="white",
            clip_on=True
        )

    # Axis configuration
    # Calculate total cranes used per shift
    total_cranes_used_per_shift = {}
    for t in range(problem.num_shifts):
        used = 0
        for vs in solution.vessel_solutions:
            c_list = vs.assigned_cranes.get(t, [])
            used += len(c_list)
        total_cranes_used_per_shift[t] = used

    # X-axis configuration with crane usage labels
    ax.set_xlim(0, problem.num_shifts)
    ax.set_ylim(0, problem.berth.length)
    ax.set_xlabel("Shift\n(Used / Total Available)", fontsize=12)
    ax.set_ylabel("Berth Position (m)", fontsize=12)
    ax.set_title(
        f"BAP + QCAP Solution — Status: {solution.status} "
        f"(Obj: {solution.objective_value:.0f})",
        fontsize=14,
    )

    # Custom X-ticks labels showing shift index and crane usage
    ax.set_xticks(range(problem.num_shifts))
    xtick_labels = []
    for t in range(problem.num_shifts):
        used = total_cranes_used_per_shift[t]
        # Total available cranes for this shift
        available = len(problem.crane_availability_per_shift.get(t, []))
        
        # Get shift label
        shift_label = str(problem.shifts[t]) if t < len(problem.shifts) else str(t)
        
        xtick_labels.append(f"{shift_label}\n({used}/{available})")
    
    ax.set_xticklabels(xtick_labels, fontsize=7, rotation=45)
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)

    # Legend
    legend_patches = [
        mpatches.Patch(color=COLORS[i % len(COLORS)], label=vs.vessel_name)
        for i, vs in enumerate(solution.vessel_solutions)
    ]
    ax.legend(handles=legend_patches, loc="upper right", fontsize=8)

    # --- Depth Profile Subplot ---
    # Draw the berth depth profile on the right subplot
    positions = range(0, problem.berth.length + 1, 5) # Sample every 5m for smoothness
    depths = []
    max_finite_depth = 0
    
    # Pre-calculate max finite depth to handle infinity
    for p in positions:
        d = problem.berth.get_depth_at(p)
        if d != float('inf'):
            max_finite_depth = max(max_finite_depth, d)
            
    # Default if everything is infinity
    if max_finite_depth == 0:
        max_finite_depth = 20.0 

    for p in positions:
        d = problem.berth.get_depth_at(p)
        if d == float('inf'):
            depths.append(max_finite_depth * 1.2) # Show as slightly larger than max
        else:
            depths.append(d)

    ax_depth.plot(depths, positions, color='tab:blue', linewidth=2)
    ax_depth.fill_betweenx(positions, 0, depths, facecolor='tab:blue', alpha=0.3)
    
    ax_depth.set_xlabel("Depth (m)")
    ax_depth.set_title("Berth Depth")
    ax_depth.grid(True, linestyle='--', alpha=0.5)
    
    # Set x-limit for depth
    ax_depth.set_xlim(0, max_finite_depth * 1.25)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Gantt chart saved to {output_path}")
    plt.close()


def plot_crane_schedule(problem: Problem, solution: Solution, output_path: str = "gantt_cranes.png"):
    """Generate a Gantt chart showing crane usage per shift.
    
    Y-axis: Cranes
    X-axis: Shifts
    Cells: Colored by Vessel, Text = Productivity
    """
    if not solution.vessel_solutions:
        print("No solution to plot crane schedule.")
        return

    # Prepare data: Crane -> Shift -> List of (VesselName, Productivity)
    crane_schedule = {c.id: defaultdict(list) for c in problem.cranes} # Value is list now
    vessel_colors = {v.name: COLORS[i % len(COLORS)] for i, v in enumerate(problem.vessels)}
    
    crane_map = {c.id: c for c in problem.cranes}
    vessels_map = {v.name: v for v in problem.vessels}

    for vs in solution.vessel_solutions:
        vessel = vessels_map[vs.vessel_name]
        pref = vessel.productivity_preference
        
        for t, crane_ids in vs.assigned_cranes.items():
            for cid in crane_ids:
                if cid in crane_schedule:
                    # Calculate productivity for this specific assignment
                    # Note: If shifting gang (multiple per shift), productivity is applied fractionally in reality
                    # But for visual, we show nominal rate or maybe "Shared".
                    c = crane_map[cid]
                    prod = 0
                    if pref == "MAX":
                        prod = c.max_productivity
                    elif pref == "MIN":
                        prod = c.min_productivity
                    else:
                        prod = (c.min_productivity + c.max_productivity) // 2
                        
                    crane_schedule[cid][t].append((vs.vessel_name, prod))

    # Plotting
    fig, ax = plt.subplots(figsize=(14, len(problem.cranes) * 0.6 + 2))
    
    cranes_sorted = sorted(problem.cranes, key=lambda c: c.id)
    y_labels = [c.id for c in cranes_sorted]
    
    for i, crane in enumerate(cranes_sorted):
        cid = crane.id
        schedule = crane_schedule.get(cid, {})
        
        # Scan all shifts
        for t in range(problem.num_shifts):
            # Maintenance check
            available_list = problem.crane_availability_per_shift.get(t, [])
            if cid not in available_list:
                 rect = mpatches.Rectangle(
                    (t, i), 1, 1,
                    facecolor='gray', alpha=0.3, hatch='///', edgecolor='black'
                )
                 ax.add_patch(rect)
                 ax.text(t + 0.5, i + 0.5, "Maint", 
                        ha="center", va="center", fontsize=6, color='black', alpha=0.7)
                 continue

            assignments = schedule.get(t, [])
            if assignments:
                # Handle Shifting Gang (Multiple assignments in one shift)
                num_assigns = len(assignments)
                width = 1.0 / num_assigns
                
                for idx, (v_name, prod) in enumerate(assignments):
                    color = vessel_colors.get(v_name, "blue")
                    
                    # Offset x position
                    x_pos = t + (idx * width)
                    
                    rect = mpatches.Rectangle(
                        (x_pos, i), width, 1,
                        facecolor=color, alpha=0.8, edgecolor='black'
                    )
                    ax.add_patch(rect)
                    
                    # Label
                    label_text = f"{v_name}\n({prod})"
                    if num_assigns > 1:
                        # Compact label for split cells
                         label_text = f"{v_name}"
                    
                    ax.text(x_pos + width/2, i + 0.5, label_text, 
                            ha="center", va="center", fontsize=7 if num_assigns==1 else 6, 
                            fontweight='bold', color='white', rotation=90 if num_assigns>1 else 0)
            else:
                # Idle
                rect = mpatches.Rectangle(
                    (t, i), 1, 1,
                    facecolor='white', alpha=0.1, edgecolor='lightgray'
                )
                ax.add_patch(rect)

    ax.set_yticks([i + 0.5 for i in range(len(cranes_sorted))])
    ax.set_yticklabels(y_labels)
    
    ax.set_xlim(0, problem.num_shifts)
    
    # Update X-ticks to show Shift Dates
    ax.set_xticks([t + 0.5 for t in range(problem.num_shifts)])
    x_labels_cranes = []
    for t in range(problem.num_shifts):
        shift_label = str(problem.shifts[t]) if t < len(problem.shifts) else str(t)
        x_labels_cranes.append(shift_label)
    ax.set_xticklabels(x_labels_cranes, rotation=45, fontsize=8)

    ax.set_ylim(0, len(cranes_sorted))
    
    ax.set_xlabel("Shift")
    ax.set_ylabel("Crane")
    ax.set_title("Crane Schedule & Productivity Assignment")
    
    ax.grid(True, axis='x', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Crane schedule saved to {output_path}")
    plt.close()


def print_solution(problem: Problem, solution: Solution):
    """Print a text summary of the solution."""
    print("=" * 70)
    print(f"Solution Status: {solution.status}")
    print(f"Objective Value: {solution.objective_value:.2f}")
    print("=" * 70)

    if not solution.vessel_solutions:
        print("No feasible solution found.")
        return

    vessels_by_name = {v.name: v for v in problem.vessels}
    crane_map = {c.id: c for c in problem.cranes}

    for vs in solution.vessel_solutions:
        vessel = vessels_by_name[vs.vessel_name]
        
        # Calculate delivered capacity based on vessel preference
        total_moves = 0
        pref = vessel.productivity_preference
        
        for t, crane_ids in vs.assigned_cranes.items():
            for cid in crane_ids:
                if cid in crane_map:
                    c = crane_map[cid]
                    prod = 0
                    if pref == "MAX":
                        prod = c.max_productivity
                    elif pref == "MIN":
                        prod = c.min_productivity
                    else:
                        prod = (c.min_productivity + c.max_productivity) // 2
                    total_moves += prod
        
        print(f"\n--- {vs.vessel_name} ---")
        print(f"  Berth position: {vs.berth_position}m - "
              f"{vs.berth_position + vessel.loa}m")
        print(f"  Time: shift {vs.start_shift} -> {vs.end_shift} "
              f"(duration: {vs.end_shift - vs.start_shift} shifts)")
        deadline = vessel.departure_deadline if vessel.departure_deadline else "Not Set (Auto)"
        
        # Calculate approximate completion time
        completion_dt = "Unknown"
        if vs.end_shift > 0 and vs.end_shift <= len(problem.shifts):
            # Completion is end of the last active shift (end_shift - 1)
            completion_dt = problem.shifts[vs.end_shift - 1].end_time
        elif vs.end_shift > len(problem.shifts):
            # Extrapolated
            extra_shifts = vs.end_shift - len(problem.shifts)
            completion_dt = f"{problem.shifts[-1].end_time} (+{extra_shifts} shifts)"

        print(f"  Arrival: {vessel.arrival_time}, Deadline: {deadline}")
        print(f"  Calculated ETC: {completion_dt}")
        print(f"  Internal: Shift {vessel.arrival_shift_index} (Fraction: {vessel.arrival_fraction:.2f})")
        print(f"  Productivity Mode: {pref}")
        print(f"  Workload: {vessel.workload} moves, "
              f"Capacity delivered: {total_moves} moves")
        print(f"  Crane assignment per shift:")
        for t in range(vs.start_shift, vs.end_shift):
            crane_ids = vs.assigned_cranes.get(t, [])
            
            # Calculate moves for this shift
            moves_this_shift = 0
            for cid in crane_ids:
                if cid in crane_map:
                    c = crane_map[cid]
                    if pref == "MAX":
                        moves_this_shift += c.max_productivity
                    elif pref == "MIN":
                        moves_this_shift += c.min_productivity
                    else:
                        moves_this_shift += (c.min_productivity + c.max_productivity) // 2
            
            print(f"    Shift {t}: {len(crane_ids)} cranes {crane_ids} "
                  f"({moves_this_shift} moves)")

    # Global crane usage summary
    print("\n" + "=" * 70)
    print("Global Crane Usage per Shift:")
    for t in range(problem.num_shifts):
        used_count = 0
        for vs in solution.vessel_solutions:
            used_count += len(vs.assigned_cranes.get(t, []))
            
        available_count = len(problem.crane_availability_per_shift.get(t, []))
        
        # Simple text bar
        bar_len = min(20, used_count)
        # Scale to max capacity?
        # Just use raw count for now
        bar = "#" * bar_len
        print(f"  Shift {t}: {used_count}/{available_count} [{bar}]")


def plot_vessel_execution_gantt(problem: Problem, solution: Solution, output_path: str = "vessel_execution.png"):
    """
    Generate a Gantt chart focused on Vessel execution details.
    
    Y-axis: Vessels
    X-axis: Time (Shifts)
    Bar Content: Moves performed in that shift by which cranes.
    Annotations: Remaining workload after shift.
    Final Marker: Completion time (ETC).
    """
    if not solution.vessel_solutions:
        print("No solution to plot.")
        return

    # Sort vessels by arrival time (or start shift) for cleaner Gantt
    sorted_solutions = sorted(solution.vessel_solutions, key=lambda x: x.start_shift)
    vessels = [v for v in problem.vessels]
    v_map = {v.name: v for v in vessels}
    c_map = {c.id: c for c in problem.cranes}

    fig, ax = plt.subplots(figsize=(16, len(sorted_solutions) * 1.5 + 2))
    
    # Define colors
    import matplotlib.cm as cm
    colors = cm.get_cmap('tab20', len(sorted_solutions))
    
    y_labels = []
    y_ticks = []
    
    # Track max shift for axis
    max_active_shift = 0

    for idx, sol in enumerate(sorted_solutions):
        v = v_map[sol.vessel_name]
        y_pos = idx
        y_labels.append(f"{v.name}\n(Tot: {v.workload})")
        y_ticks.append(y_pos)
        
        cumulative_moves = 0
        executed_shifts = sorted(sol.assigned_cranes.keys())
        
        if not executed_shifts:
            continue
            
        final_shift = sol.end_shift - 1 # inclusive index of last active shift
        # Actually end_shift is exclusive in solution usually? 
        # VesselSolution def says: start_shift, end_shift (presumably exclusive based on range usage)
        # But let's check solver output logic. 
        # range(vs.start_shift, vs.end_shift) is used in plot_solution.
        # So last active shift is indeed end_shift - 1.
        
        max_active_shift = max(max_active_shift, sol.end_shift)

        # Draw arrival marker
        ax.plot(v.arrival_shift_index + v.arrival_fraction, y_pos, 'g>', markersize=10, label='Arrival' if idx==0 else "")

        for seq_idx, t in enumerate(executed_shifts):
            cranes = sol.assigned_cranes[t]
            if not cranes: continue
            
            shift_moves = 0
            crane_details = []
            
            for c_id in cranes:
                if c_id not in c_map: continue
                c = c_map[c_id]
                
                # Determine limit
                limit = c.max_productivity
                if v.productivity_preference.name == "MIN": limit = c.min_productivity
                elif v.productivity_preference.name == "INTERMEDIATE": limit = (c.min_productivity + c.max_productivity) // 2
                
                # Arrival fraction impact
                if t == v.arrival_shift_index:
                    limit = int(limit * v.arrival_fraction)
                
                # Logic for Moves:
                # If t < final_shift: Full Capacity used
                # If t == final_shift: Remainder used (shared among cranes)
                
                moves_val = 0
                if t < sol.end_shift - 1:
                    moves_val = limit
                else:
                    # Last shift logic: We don't have per-crane moves from Solver output yet (only lists).
                    # We approximate: Total remaining / num_cranes? 
                    # Or just: Sum of full capacities is upper bound.
                    # We will calculate "Shift Total Moves" separately.
                    moves_val = limit # Provisional
                    
                shift_moves += moves_val
            
            # Correction for Final Shift to exactly match workload
            if t == sol.end_shift - 1:
                remaining_needed = max(0, v.workload - cumulative_moves)
                shift_moves = remaining_needed
            
            cumulative_moves += shift_moves
            remain = max(0, v.workload - cumulative_moves)
            
            # Plot Bar for this shift
            # Width = 1 shift (or fraction if arrival/departure?)
            # Simplified: Width 1.
            bar_start = t
            bar_width = 1.0
            
            # If arrival shift, start later?
            if t == v.arrival_shift_index:
                bar_start = t + (1 - v.arrival_fraction)
                bar_width = v.arrival_fraction
            
            # If final shift, maybe end earlier?
            # We don't know exact finish time within shift without better solver output.
            # Assuming full shift used for visualization unless very small moves.
            
            ax.barh(
                y_pos, width=bar_width, left=bar_start, height=0.6,
                color=colors(idx), edgecolor='black', alpha=0.8
            )
            
            # Annotate Moves (Center)
            ax.text(
                bar_start + bar_width/2, y_pos, 
                f"{int(shift_moves)}", 
                ha='center', va='center', fontsize=9, color='white', fontweight='bold'
            )
            
            # Annotate Remain (Bottom Right)
            ax.text(
                bar_start + bar_width, y_pos - 0.35, 
                f"Rem:{int(remain)}", 
                ha='right', va='top', fontsize=8, color='black', fontweight='bold'
            )
            
            # Annotate Cranes (Top)
            # Shorten names? C1, C2...
            c_str = ",".join([cid.split('-')[-1] for cid in cranes])
            ax.text(
                 bar_start + bar_width/2, y_pos + 0.32, 
                 f"[{c_str}]", 
                 ha='center', va='bottom', fontsize=7, color='blue'
            )

        # Mark ETC / Completion
        completion_time = sol.end_shift 
        # Draw finish line
        ax.plot([completion_time, completion_time], [y_pos-0.4, y_pos+0.4], 'r-', linewidth=2)
        ax.text(completion_time + 0.1, y_pos, f"Done (S{completion_time})", va='center', color='red', fontsize=9, fontweight='bold')

    # Formatting
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_labels)
    ax.set_ylabel("Vessels")
    ax.set_xlabel("Shifts (Time)")
    ax.set_title("Vessel Execution Summary: Moves per Shift & Burndown")
    ax.grid(True, axis='x', linestyle='--', alpha=0.5)
    
    # Set X ticks
    ax.set_xticks(range(int(max_active_shift) + 3))
    
    # Add legend manually?
    # Legend for bar colors is vessel - redundant names are on Y axis.
    # Arrival/Departure markers legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='>', color='w', markerfacecolor='g', label='Arrival', markersize=10),
        Line2D([0], [0], color='r', lw=2, label='Completion'),
        mpatches.Patch(edgecolor='black', facecolor='gray', alpha=0.5, label='Active Work (Bar)')
    ]
    ax.legend(handles=legend_elements, loc='upper right')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Vessel Execution Gantt saved to {output_path}")
    plt.close()
