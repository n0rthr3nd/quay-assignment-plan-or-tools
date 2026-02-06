"""Main entry point: defines example data and runs the BAP + QCAP solver."""

import os
from typing import List, Dict

from models import Berth, Problem, Vessel, ForbiddenZone, Crane, CraneType, ProductivityMode
from solver import solve
from visualization import plot_solution, print_solution

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")


def create_cranes(berth_length: int) -> List[Crane]:
    """Create a list of cranes with different types and coverage."""
    cranes = []
    
    # 6 STS cranes covering the deep water area (mostly)
    # Positions 0 to 1400m
    for i in range(1, 7):
        cranes.append(Crane(
            id=f"STS-{i:02d}",
            name=f"STS Crane {i}",
            crane_type=CraneType.STS,
            berth_range_start=0,
            berth_range_end=1400,
            min_productivity=100,
            max_productivity=130
        ))
        
    # 4 MHC cranes covering the shallower area
    # Positions 1000 to 2000m
    for i in range(1, 5):
        cranes.append(Crane(
            id=f"MHC-{i:02d}",
            name=f"MHC Crane {i}",
            crane_type=CraneType.MHC,
            berth_range_start=1000,
            berth_range_end=berth_length,
            min_productivity=60,
            max_productivity=90
        ))
        
    return cranes


def create_example_problem() -> Problem:
    """Create a realistic example problem instance."""

    berth = Berth(
        length=2000,
        depth_map={0: 16.0, 1200: 12.0},  # 0-1200m is deep (16m), 1200-2000m is shallow (12m)
    )

    vessels = [
        # --- Arrivals at shift 0 ---
        Vessel(name="V1-MSC", workload=800, loa=300, draft=14.0, etw=0, etc=6, max_cranes=4, productivity_preference=ProductivityMode.MAX),
        Vessel(name="V2-MAERSK", workload=600, loa=250, draft=13.0, etw=0, etc=5, max_cranes=3, productivity_preference=ProductivityMode.INTERMEDIATE),
        Vessel(name="V3-COSCO", workload=500, loa=280, draft=14.5, etw=0, etc=8, max_cranes=3, productivity_preference=ProductivityMode.MIN),
        # --- Arrivals at shift 1 ---
        Vessel(name="V4-CMA", workload=400, loa=200, draft=12.0, etw=1, etc=6, max_cranes=3), # Default INTERMEDIATE
        Vessel(name="V5-HAPAG", workload=350, loa=180, draft=11.0, etw=1, etc=8, max_cranes=2, productivity_preference=ProductivityMode.MAX),
        # --- Arrivals at shift 2 ---
        Vessel(name="V6-ONE", workload=700, loa=290, draft=13.5, etw=2, etc=7, max_cranes=3),
        Vessel(name="V7-EVERGREEN", workload=900, loa=330, draft=15.0, etw=2, etc=8, max_cranes=4, productivity_preference=ProductivityMode.MAX),
        # --- Arrivals at shift 3 ---
        Vessel(name="V8-HMM", workload=450, loa=220, draft=12.5, etw=3, etc=7, max_cranes=3),
        Vessel(name="V9-YANGMING", workload=550, loa=260, draft=13.8, etw=3, etc=9, max_cranes=3, productivity_preference=ProductivityMode.MIN),
        # --- Arrivals at shift 4-5 ---
        Vessel(name="V10-ZIM", workload=400, loa=210, draft=11.5, etw=4, etc=8, max_cranes=2),
        Vessel(name="V11-WANHAI", workload=300, loa=190, draft=10.5, etw=4, etc=9, max_cranes=2),
        Vessel(name="V12-PIL", workload=600, loa=270, draft=13.2, etw=5, etc=10, max_cranes=3),
    ]

    num_shifts = 12
    cranes = create_cranes(berth.length)
    
    # Define availability per shift
    # For now, all cranes available all shifts
    # But let's simulate maintenance: STS-01 unavailable in shift 0-2
    availability: Dict[int, List[str]] = {}
    all_crane_ids = [c.id for c in cranes]
    
    for t in range(num_shifts):
        # Default: all avail
        avail = list(all_crane_ids)
        
        # Example Maintenance on STS-01 for first 2 shifts
        if t < 2:
            if "STS-01" in avail:
                avail.remove("STS-01")
                
        availability[t] = avail

    return Problem(
        berth=berth,
        vessels=vessels,
        cranes=cranes,
        num_shifts=num_shifts,
        crane_availability_per_shift=availability,
    )


def create_forbidden_zone_example() -> Problem:
    """Example with forbidden zones (maintenance, etc)."""
    
    # Start with standard problem
    problem = create_example_problem()
    
    # Add restricted zones
    # 1. Maintenance at start of berth (0-400m) for first 3 shifts
    z1 = ForbiddenZone(
        start_berth_position=0,
        end_berth_position=400,
        start_shift=0,
        end_shift=3,
        description="Quay Maint A"
    )
    
    # 2. Dredging operations in middle (1000-1300m) for shifts 4-7
    z2 = ForbiddenZone(
        start_berth_position=1000,
        end_berth_position=1300,
        start_shift=4,
        end_shift=7,
        description="Dredging Ops"
    )
    
    problem.forbidden_zones = [z1, z2]
    return problem


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("  BAP + QCAP Port Terminal Optimization Solver")
    print("  Using Google OR-Tools CP-SAT")
    print("=" * 70)

    # --- Example 3: Forbidden Zones ---
    print("\n>>> Example 3: Forbidden Zones (Maintenance) & Specific Cranes")
    problem3 = create_forbidden_zone_example()
    
    # Print crane setup
    print(f"Loaded {len(problem3.cranes)} cranes.")
    for c in problem3.cranes:
        print(f"  - {c.name} ({c.crane_type.value}): range {c.berth_range_start}-{c.berth_range_end}m, prod={c.max_productivity}")

    solution3 = solve(problem3, time_limit_seconds=60)
    print_solution(problem3, solution3)
    plot_solution(problem3, solution3, os.path.join(OUTPUT_DIR, "gantt_forbidden_cranes.png"))
    
    # New Crane Schedule Plot
    from visualization import plot_crane_schedule
    plot_crane_schedule(problem3, solution3, os.path.join(OUTPUT_DIR, "cranes_schedule.png"))


if __name__ == "__main__":
    main()
