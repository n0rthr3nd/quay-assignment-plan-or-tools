"""Main entry point: defines example data and runs the BAP + QCAP solver."""

import os

from models import Berth, Problem, Vessel
from solver import solve
from visualization import plot_solution, print_solution

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")


def create_example_problem() -> Problem:
    """Create a realistic example problem instance."""

    berth = Berth(
        length=2000,
        depth_map={0: 16.0, 1200: 12.0},  # 0-1200m is deep (16m), 1200-2000m is shallow (12m)
    )

    vessels = [
        # --- Arrivals at shift 0 ---
        Vessel("V1-MSC", 800, 300, 14.0, 120, 0, 6, 4),
        Vessel("V2-MAERSK", 600, 250, 13.0, 120, 0, 5, 3),
        Vessel("V3-COSCO", 500, 280, 14.5, 110, 0, 8, 3),
        # --- Arrivals at shift 1 ---
        Vessel("V4-CMA", 400, 200, 12.0, 100, 1, 6, 3),
        Vessel("V5-HAPAG", 350, 180, 11.0, 100, 1, 8, 2),
        # --- Arrivals at shift 2 ---
        Vessel("V6-ONE", 700, 290, 13.5, 115, 2, 7, 3),
        Vessel("V7-EVERGREEN", 900, 330, 15.0, 130, 2, 8, 4),
        # --- Arrivals at shift 3 ---
        Vessel("V8-HMM", 450, 220, 12.5, 105, 3, 7, 3),
        Vessel("V9-YANGMING", 550, 260, 13.8, 110, 3, 9, 3),
        # --- Arrivals at shift 4-5 ---
        Vessel("V10-ZIM", 400, 210, 11.5, 100, 4, 8, 2),
        Vessel("V11-WANHAI", 300, 190, 10.5, 90, 4, 9, 2),
        Vessel("V12-PIL", 600, 270, 13.2, 120, 5, 10, 3),
    ]

    num_shifts = 12  # Increased shifts to accommodate more vessels
    total_cranes = [12] * num_shifts  # More cranes available

    return Problem(
        berth=berth,
        vessels=vessels,
        num_shifts=num_shifts,
        total_cranes_per_shift=total_cranes,
    )


def create_depth_constraint_example() -> Problem:
    """Example with variable depth along the berth."""

    # Depth varies: first 1200m is deep (16m), last 800m to 2000m is shallower (12m)
    berth = Berth(
        length=2000,
        depth_map={0: 16.0, 1200: 12.0},
    )

    vessels = [
        # --- DEEP DRAFT (Require 0-1200m) ---
        Vessel("V1-Deep-0", 700, 280, 15.0, 120, 0, 6, 4),
        Vessel("V2-Deep-1", 800, 300, 14.5, 130, 1, 7, 4),
        Vessel("V3-Deep-2", 650, 290, 14.0, 115, 2, 8, 3),
        Vessel("V4-Deep-3", 750, 310, 15.5, 125, 3, 9, 4),
        Vessel("V5-Deep-4", 600, 270, 13.5, 110, 4, 8, 3),
        
        # --- SHALLOW DRAFT (Can fit in 1200-2000m or 0-1200m) ---
        Vessel("V6-Shallow-0", 400, 200, 11.0, 100, 0, 5, 2),
        Vessel("V7-Shallow-0b", 350, 180, 10.5, 90, 0, 5, 2),
        Vessel("V8-Shallow-1", 450, 220, 11.5, 105, 1, 6, 3),
        Vessel("V9-Shallow-2", 500, 240, 11.8, 110, 2, 7, 3),
        Vessel("V10-Shallow-3", 300, 160, 9.0, 80, 3, 8, 2),
        
        # --- MIXED/MEDIUM (Arrivals later) ---
        Vessel("V11-Med-4", 550, 250, 12.0, 110, 4, 10, 3),  # Max depth for shallow section
        Vessel("V12-Deep-5", 850, 320, 14.8, 140, 5, 12, 4), # Late huge ship (deep)
    ]

    return Problem(
        berth=berth,
        vessels=vessels,
        num_shifts=14,
        total_cranes_per_shift=[10] * 14,
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
