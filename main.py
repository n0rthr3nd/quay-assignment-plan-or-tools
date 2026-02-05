"""Main entry point: defines example data and runs the BAP + QCAP solver."""

import os

from models import Berth, Problem, Vessel
from solver import solve
from visualization import plot_solution, print_solution

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")


def create_example_problem() -> Problem:
    """Create a realistic example problem instance."""

    berth = Berth(
        length=600,  # 600-meter quay
        depth=16.0,  # Uniform 16m depth
    )

    vessels = [
        Vessel(
            name="V1-MSC",
            workload=800,
            loa=300,
            draft=14.0,
            productivity=120,
            etw=0,
            etc=6,
            max_cranes=4,
        ),
        Vessel(
            name="V2-MSC",
            workload=800,
            loa=320,
            draft=14.0,
            productivity=120,
            etw=0,
            etc=6,
            max_cranes=4,
        ),
        Vessel(
            name="V3-MSC",
            workload=800,
            loa=320,
            draft=14.0,
            productivity=120,
            etw=0,
            etc=6,
            max_cranes=4,
        ),
        Vessel(
            name="V4-MSC",
            workload=800,
            loa=320,
            draft=14.0,
            productivity=120,
            etw=0,
            etc=6,
            max_cranes=4,
        ),
        Vessel(
            name="V2-MAERSK",
            workload=600,
            loa=250,
            draft=13.0,
            productivity=120,
            etw=0,
            etc=5,
            max_cranes=3,
        ),
        Vessel(
            name="V3-CMA",
            workload=400,
            loa=200,
            draft=12.0,
            productivity=100,
            etw=1,
            etc=6,
            max_cranes=3,
        ),
        Vessel(
            name="V4-COSCO",
            workload=500,
            loa=280,
            draft=14.5,
            productivity=110,
            etw=2,
            etc=8,
            max_cranes=3,
        ),
        Vessel(
            name="V5-HAPAG",
            workload=300,
            loa=180,
            draft=11.0,
            productivity=100,
            etw=3,
            etc=8,
            max_cranes=2,
        ),
    ]

    num_shifts = 10  # 10 shifts = 60 hours (2.5 days)
    total_cranes = [8] * num_shifts  # 8 cranes available each shift

    return Problem(
        berth=berth,
        vessels=vessels,
        num_shifts=num_shifts,
        total_cranes_per_shift=total_cranes,
    )


def create_depth_constraint_example() -> Problem:
    """Example with variable depth along the berth."""

    # Depth varies: first 300m is deep (16m), last 300m is shallower (12m)
    berth = Berth(
        length=600,
        depth_map={0: 16.0, 300: 12.0},
    )

    vessels = [
        Vessel(
            name="V1-DEEP",
            workload=600,
            loa=250,
            draft=15.0,  # Needs deep water
            productivity=120,
            etw=0,
            etc=5,
            max_cranes=3,
        ),
        Vessel(
            name="V2-SHALLOW",
            workload=400,
            loa=200,
            draft=11.0,  # Can go anywhere
            productivity=100,
            etw=0,
            etc=5,
            max_cranes=3,
        ),
        Vessel(
            name="V3-MID",
            workload=350,
            loa=180,
            draft=13.0,  # Needs the deep section
            productivity=110,
            etw=1,
            etc=6,
            max_cranes=2,
        ),
    ]

    return Problem(
        berth=berth,
        vessels=vessels,
        num_shifts=8,
        total_cranes_per_shift=[6] * 8,
    )


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("  BAP + QCAP Port Terminal Optimization Solver")
    print("  Using Google OR-Tools CP-SAT")
    print("=" * 70)

    # --- Example 1: Standard problem ---
    print("\n>>> Example 1: Standard Problem (uniform depth)")
    problem1 = create_example_problem()
    solution1 = solve(problem1, time_limit_seconds=30)
    print_solution(problem1, solution1)
    plot_solution(problem1, solution1, os.path.join(OUTPUT_DIR, "gantt_example1.png"))

    # --- Example 2: Variable depth ---
    print("\n\n>>> Example 2: Variable Depth Problem")
    problem2 = create_depth_constraint_example()
    solution2 = solve(problem2, time_limit_seconds=30)
    print_solution(problem2, solution2)
    plot_solution(problem2, solution2, os.path.join(OUTPUT_DIR, "gantt_example2.png"))


if __name__ == "__main__":
    main()
