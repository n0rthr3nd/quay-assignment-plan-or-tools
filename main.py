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
        Vessel(name="V1-MSC", workload=800, loa=300, draft=14.0, productivity=120, etw=0, etc=6, max_cranes=4),
        Vessel(name="V2-MAERSK", workload=600, loa=250, draft=13.0, productivity=120, etw=0, etc=5, max_cranes=3),
        Vessel(name="V3-COSCO", workload=500, loa=280, draft=14.5, productivity=110, etw=0, etc=8, max_cranes=3),
        # --- Arrivals at shift 1 ---
        Vessel(name="V4-CMA", workload=400, loa=200, draft=12.0, productivity=100, etw=1, etc=6, max_cranes=3),
        Vessel(name="V5-HAPAG", workload=350, loa=180, draft=11.0, productivity=100, etw=1, etc=8, max_cranes=2),
        # --- Arrivals at shift 2 ---
        Vessel(name="V6-ONE", workload=700, loa=290, draft=13.5, productivity=115, etw=2, etc=7, max_cranes=3),
        Vessel(name="V7-EVERGREEN", workload=900, loa=330, draft=15.0, productivity=130, etw=2, etc=8, max_cranes=4),
        # --- Arrivals at shift 3 ---
        Vessel(name="V8-HMM", workload=450, loa=220, draft=12.5, productivity=105, etw=3, etc=7, max_cranes=3),
        Vessel(name="V9-YANGMING", workload=550, loa=260, draft=13.8, productivity=110, etw=3, etc=9, max_cranes=3),
        # --- Arrivals at shift 4-5 ---
        Vessel(name="V10-ZIM", workload=400, loa=210, draft=11.5, productivity=100, etw=4, etc=8, max_cranes=2),
        Vessel(name="V11-WANHAI", workload=300, loa=190, draft=10.5, productivity=90, etw=4, etc=9, max_cranes=2),
        Vessel(name="V12-PIL", workload=600, loa=270, draft=13.2, productivity=120, etw=5, etc=10, max_cranes=3),
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
        Vessel(name="V1-Deep-0", workload=1700, loa=280, draft=15.0, productivity=120, etw=0, etc=6, max_cranes=8),
        Vessel(name="V2-Deep-1", workload=800, loa=300, draft=14.5, productivity=130, etw=1, etc=7, max_cranes=4),
        Vessel(name="V3-Deep-2", workload=650, loa=290, draft=14.0, productivity=115, etw=2, etc=8, max_cranes=3),
        Vessel(name="V4-Deep-3", workload=750, loa=310, draft=15.5, productivity=125, etw=3, etc=9, max_cranes=4),
        Vessel(name="V5-Deep-4", workload=600, loa=270, draft=13.5, productivity=110, etw=4, etc=8, max_cranes=3),
        
        # --- SHALLOW DRAFT (Can fit in 1200-2000m or 0-1200m) ---
        Vessel(name="V6-Shallow-0", workload=400, loa=200, draft=11.0, productivity=100, etw=0, etc=5, max_cranes=2),
        Vessel(name="V7-Shallow-0b", workload=350, loa=180, draft=10.5, productivity=90, etw=0, etc=5, max_cranes=2),
        Vessel(name="V8-Shallow-1", workload=450, loa=220, draft=11.5, productivity=105, etw=1, etc=6, max_cranes=3),
        Vessel(name="V9-Shallow-2", workload=500, loa=240, draft=11.8, productivity=110, etw=2, etc=7, max_cranes=3),
        Vessel(name="V10-Shallow-3", workload=300, loa=160, draft=9.0, productivity=80, etw=3, etc=8, max_cranes=2),
        
        # --- MIXED/MEDIUM (Arrivals later) ---
        Vessel(name="V11-Med-4", workload=550, loa=250, draft=12.0, productivity=110, etw=4, etc=10, max_cranes=3),
        Vessel(name="V12-Deep-5", workload=850, loa=320, draft=14.8, productivity=140, etw=5, etc=12, max_cranes=4),
    ]

    return Problem(
        berth=berth,
        vessels=vessels,
        num_shifts=14,
        total_cranes_per_shift=[14] * 14,
    )


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("  BAP + QCAP Port Terminal Optimization Solver")
    print("  Using Google OR-Tools CP-SAT")
    print("=" * 70)

    # --- Example 2: Variable depth ---
    print("\n>>> Example 2: Variable Depth Problem")
    problem2 = create_depth_constraint_example()
    solution2 = solve(problem2, time_limit_seconds=30)
    print_solution(problem2, solution2)
    plot_solution(problem2, solution2, os.path.join(OUTPUT_DIR, "gantt_result.png"))


if __name__ == "__main__":
    main()
