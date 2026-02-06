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

    fig, ax = plt.subplots(figsize=(14, 8))

    vessels_by_name = {v.name: v for v in problem.vessels}

    for idx, vs in enumerate(solution.vessel_solutions):
        vessel = vessels_by_name[vs.vessel_name]
        color = COLORS[idx % len(COLORS)]

        x = vs.start_shift
        y = vs.berth_position
        width = vs.end_shift - vs.start_shift
        height = vessel.loa

        rect = mpatches.FancyBboxPatch(
            (x, y), width, height,
            boxstyle="round,pad=0.05",
            facecolor=color, edgecolor="black", linewidth=1.2, alpha=0.85,
        )
        ax.add_patch(rect)

        # Label with vessel name and crane assignment per shift
        crane_str = ",".join(
            str(vs.cranes_per_shift.get(t, 0))
            for t in range(vs.start_shift, vs.end_shift)
        )
        label = f"{vs.vessel_name}\nQ:[{crane_str}]"
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
