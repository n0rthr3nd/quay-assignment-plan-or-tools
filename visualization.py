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

        # Label with vessel name, crane assignment per shift, and draft
        crane_str = ",".join(
            str(vs.cranes_per_shift.get(t, 0))
            for t in range(vs.start_shift, vs.end_shift)
        )
        label = f"{vs.vessel_name}\nQ:[{crane_str}]\nD:{vessel.draft}m"
        ax.text(
            x + width / 2, y + height / 2, label,
            ha="center", va="center", fontsize=7, fontweight="bold", color="white",
        )

    # Axis configuration
    # Calculate total cranes used per shift
    total_cranes_per_shift = {}
    for t in range(problem.num_shifts):
        used = sum(
            vs.cranes_per_shift.get(t, 0) for vs in solution.vessel_solutions
        )
        total_cranes_per_shift[t] = used

    # X-axis configuration with crane usage labels
    ax.set_xlim(0, problem.num_shifts)
    ax.set_ylim(0, problem.berth.length)
    ax.set_xlabel("Shift\n(Used / Total Gangs)", fontsize=12)
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
        used = total_cranes_per_shift[t]
        cap = problem.total_cranes_per_shift[t]
        xtick_labels.append(f"{t}\n({used}/{cap})")
    
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
    
    # Hide y-ticks on the depth plot as it shares with the main plot
    # But keeping them visible on the right might be nice? 
    # With sharey=True, they are usually hidden on the left of the second plot.
    # Let's keep it clean.

    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Gantt chart saved to {output_path}")
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

    for vs in solution.vessel_solutions:
        vessel = vessels_by_name[vs.vessel_name]
        total_moves = sum(
            cranes * vessel.productivity
            for cranes in vs.cranes_per_shift.values()
        )
        print(f"\n--- {vs.vessel_name} ---")
        print(f"  Berth position: {vs.berth_position}m - "
              f"{vs.berth_position + vessel.loa}m")
        print(f"  Time: shift {vs.start_shift} -> {vs.end_shift} "
              f"(duration: {vs.end_shift - vs.start_shift} shifts)")
        print(f"  ETW: {vessel.etw}, ETC: {vessel.etc}")
        print(f"  Workload: {vessel.workload} moves, "
              f"Capacity delivered: {total_moves} moves")
        print(f"  Crane assignment per shift:")
        for t in range(vs.start_shift, vs.end_shift):
            cranes = vs.cranes_per_shift.get(t, 0)
            print(f"    Shift {t}: {cranes} cranes "
                  f"({cranes * vessel.productivity} moves)")

    # Global crane usage summary
    print("\n" + "=" * 70)
    print("Global Crane Usage per Shift:")
    for t in range(problem.num_shifts):
        total = sum(
            vs.cranes_per_shift.get(t, 0) for vs in solution.vessel_solutions
        )
        cap = problem.total_cranes_per_shift[t]
        bar = "#" * total + "." * (cap - total)
        print(f"  Shift {t}: {total}/{cap} [{bar}]")
