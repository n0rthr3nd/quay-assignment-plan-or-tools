"""Visualization for BAP + QCAP solutions: Space-Time Gantt chart."""

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

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
        xtick_labels.append(f"{t}\n({used}/{available})")
    
    ax.set_xticklabels(xtick_labels, fontsize=9)
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

    # Prepare data: Crane -> Shift -> (VesselName, Productivity)
    crane_schedule = {c.id: {} for c in problem.cranes}
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
                    c = crane_map[cid]
                    prod = 0
                    if pref == "MAX":
                        prod = c.max_productivity
                    elif pref == "MIN":
                        prod = c.min_productivity
                    else:
                        prod = (c.min_productivity + c.max_productivity) // 2
                        
                    crane_schedule[cid][t] = (vs.vessel_name, prod)

    # Plotting
    fig, ax = plt.subplots(figsize=(14, len(problem.cranes) * 0.5 + 2))
    
    cranes_sorted = sorted(problem.cranes, key=lambda c: c.id)
    y_labels = [c.id for c in cranes_sorted]
    
    for i, crane in enumerate(cranes_sorted):
        cid = crane.id
        schedule = crane_schedule.get(cid, {})
        
        # Check availability constraints to mark unavailable slots (e.g. maintenance)
        # Scan all shifts
        for t in range(problem.num_shifts):
            # If crane NOT in availability list for this shift, mark as Maintenance
            available_list = problem.crane_availability_per_shift.get(t, [])
            if cid not in available_list:
                # Draw gray box for maintenance
                 rect = mpatches.Rectangle(
                    (t, i), 1, 1,
                    facecolor='gray', alpha=0.3, hatch='///', edgecolor='black'
                )
                 ax.add_patch(rect)
                 ax.text(t + 0.5, i + 0.5, "Maint", 
                        ha="center", va="center", fontsize=6, color='black', alpha=0.7)
                 continue

            if t in schedule:
                v_name, prod = schedule[t]
                color = vessel_colors.get(v_name, "blue")
                
                rect = mpatches.Rectangle(
                    (t, i), 1, 1,
                    facecolor=color, alpha=0.8, edgecolor='black'
                )
                ax.add_patch(rect)
                
                # Label: Vessel\nProd
                ax.text(t + 0.5, i + 0.5, f"{v_name}\n{prod}", 
                        ha="center", va="center", fontsize=7, fontweight='bold', color='white')
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
        print(f"  ETW: {vessel.etw}, ETC: {vessel.etc}")
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
