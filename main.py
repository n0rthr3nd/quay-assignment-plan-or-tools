"""Main entry point: defines example data and runs the BAP + QCAP solver."""

import os
from typing import List, Dict

from models import Berth, Problem, Vessel, ForbiddenZone, Crane, CraneType, ProductivityMode, Shift
import datetime

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


def generate_shifts(start_date_str: str, num_total_shifts: int) -> List[Shift]:
    """Generate a list of consecutive shifts starting from a date."""
    # Assuming start_date is DDMMYYYY
    d = int(start_date_str[:2])
    m = int(start_date_str[2:4])
    y = int(start_date_str[4:])
    
    current_date = datetime.date(y, m, d)
    shifts = []
    
    idx = 0
    while len(shifts) < num_total_shifts:
        # 4 shifts per day: 00-06, 06-12, 12-18, 18-24 (next day start)
        shift_starts = [0, 6, 12, 18] # Hours
        
        for i, start_hour in enumerate(shift_starts):
            if len(shifts) >= num_total_shifts:
                break
            
            # Create 6h blocks starting at current_date + start_hour
            dt_base = datetime.datetime.combine(current_date, datetime.time(start_hour, 0))
            
            start_dt = dt_base
            end_dt = start_dt + datetime.timedelta(hours=6)
            
            shifts.append(Shift(id=len(shifts), start_time=start_dt, end_time=end_dt))
            
        current_date += datetime.timedelta(days=1)
        
    return shifts


def create_example_problem() -> Problem:
    """Create a realistic example problem instance."""

    berth = Berth(
        length=2000,
        depth_map={0: 16.0, 1200: 12.0},  # 0-1200m is deep (16m), 1200-2000m is shallow (12m)
    )

    # Create Shifts
    num_shifts = 12
    shifts = generate_shifts("31122025", num_shifts)
    
    # Create Vessels with Arrival/Departure Times
    base_time = shifts[0].start_time
    
    # Helper to easier create datetimes relative to base
    def get_dt(shift_idx, hour_offset=0):
        # Base time + shift_idx days (approx) or shifts?
        # Let's map shift index to Start Time of that shift
        if shift_idx >= len(shifts):
             return shifts[-1].end_time + datetime.timedelta(hours=6 * (shift_idx - len(shifts) + 1))
        
        s = shifts[shift_idx]
        return s.start_time + datetime.timedelta(hours=hour_offset)

    # Note: Shift duration is approx 6h (4 shifts/day)
    vessels = [
        # V1: Arrives at start of Shift 0.
        Vessel(name="V1-MSC", workload=800, loa=300, draft=14.0, 
               arrival_time=get_dt(0, 0), 
               max_cranes=4, productivity_preference=ProductivityMode.MAX),
        
        # V2: Arrives 2 hours into Shift 0.
        Vessel(name="V2-MAERSK", workload=600, loa=250, draft=13.0, 
               arrival_time=get_dt(0, 2), 
               max_cranes=3, productivity_preference=ProductivityMode.INTERMEDIATE),
        
        Vessel(name="V3-COSCO", workload=500, loa=280, draft=14.5, 
               arrival_time=get_dt(0, 0), 
               max_cranes=3, productivity_preference=ProductivityMode.MIN),
               
        # Shift 1 arrivals
        Vessel(name="V4-CMA", workload=400, loa=200, draft=12.0, 
               arrival_time=get_dt(1, 0), 
               max_cranes=3), 
        
        Vessel(name="V5-HAPAG", workload=350, loa=180, draft=11.0, 
               arrival_time=get_dt(1, 0), 
               max_cranes=2, productivity_preference=ProductivityMode.MAX),
               
        # Shift 2 arrivals
        Vessel(name="V6-ONE", workload=700, loa=290, draft=13.5, 
               arrival_time=get_dt(2, 0), 
               max_cranes=3),
               
        Vessel(name="V7-EVERGREEN", workload=900, loa=330, draft=15.0, 
               arrival_time=get_dt(2, 0), 
               max_cranes=4, productivity_preference=ProductivityMode.MAX),
               
        # Shift 3
        Vessel(name="V8-HMM", workload=450, loa=220, draft=12.5, 
               arrival_time=get_dt(3, 0), 
               max_cranes=3),
               
        Vessel(name="V9-YANGMING", workload=550, loa=260, draft=13.8, 
               arrival_time=get_dt(3, 0), 
               max_cranes=3, productivity_preference=ProductivityMode.MIN),
               
        # Shift 4-5
        Vessel(name="V10-ZIM", workload=400, loa=210, draft=11.5, 
               arrival_time=get_dt(4, 0), 
               max_cranes=2),
               
        Vessel(name="V11-WANHAI", workload=300, loa=190, draft=10.5, 
               arrival_time=get_dt(4, 0), 
               max_cranes=2),
               
        Vessel(name="V12-PIL", workload=600, loa=270, draft=13.2, 
               arrival_time=get_dt(5, 0), 
               max_cranes=3),
    ]

    # Pre-process vessels to populate internal shift indices and fractions
    for v in vessels:
        # Find arrival shift
        v.arrival_shift_index = -1
        v.arrival_fraction = 1.0
        
        for t, s in enumerate(shifts):
            if s.start_time <= v.arrival_time < s.end_time:
                v.arrival_shift_index = t
                # Calculate fraction remaining
                # e.g. Start 8:00, arr 10:00, End 14:00 (6h)
                # avail = 14 - 10 = 4h. Fraction = 4/6 = 0.66
                total_dur = (s.end_time - s.start_time).total_seconds()
                avail_dur = (s.end_time - v.arrival_time).total_seconds()
                v.arrival_fraction = avail_dur / total_dur if total_dur > 0 else 0
                break
        
        # If arrival is before first shift, treat as index 0, full
        if v.arrival_time < shifts[0].start_time:
            v.arrival_shift_index = 0
            v.arrival_fraction = 1.0
            
        # If arrival is after last shift, it's out of scope (ignore or warn)
        if v.arrival_shift_index == -1 and v.arrival_time >= shifts[-1].end_time:
             # handle appropriately, maybe set to num_shifts
             v.arrival_shift_index = num_shifts 
             
        # Determine available shifts list (from Arr to Dep-1) or similar
        # For simplicity, we assume ETC is a hard cut-off for now, or just guidance?
        # User said: "ETC vendra dada de inicio, pero será reajustada"
        # So we should allow solver to go beyond departure_deadline if needed?
        # For now, let's map departure_deadline to a shift index for ETC
        v.departure_shift_index = num_shifts
        if v.departure_deadline:
            for t, s in enumerate(shifts):
                if s.start_time <= v.departure_deadline <= s.end_time: # Approximate
                    v.departure_shift_index = t
                    break
        
        # Determine integer shift range for "etw" and "etc" equivalence
        # available_shifts could be [arrival_shift_index .... num_shifts - 1]
        start_idx = v.arrival_shift_index
        if start_idx < num_shifts:
             v.available_shifts = list(range(start_idx, num_shifts))
        else:
             v.available_shifts = []

    
    cranes = create_cranes(berth.length)
    
    # Availability logic...
    availability: Dict[int, List[str]] = {}
    all_crane_ids = [c.id for c in cranes]
    
    for t in range(num_shifts):
        avail = list(all_crane_ids)
        if t < 2:
            if "STS-01" in avail:
                avail.remove("STS-01")
        availability[t] = avail

    # Create a Forbidden Zone (e.g., Quay Maintenance)
    # Block 200m section (start=400, end=600) for Shifts 2 and 3 (start=2, end=4)
    forbidden_zones = [
        ForbiddenZone(
            start_berth_position=400, 
            end_berth_position=600, 
            start_shift=2, 
            end_shift=4, 
            description="Quay Wall Maintenance A"
        ),
        ForbiddenZone(
            start_berth_position=1500, 
            end_berth_position=1600, 
            start_shift=6, 
            end_shift=8, 
            description="Dredging Operations B"
        )
    ]

    return Problem(
        berth=berth,
        vessels=vessels,
        cranes=cranes,
        shifts=shifts,
        crane_availability_per_shift=availability,
        forbidden_zones=forbidden_zones
    )


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 70)
    print("  BAP + QCAP Port Terminal Optimization Solver")
    print("  Using Google OR-Tools CP-SAT")
    print("=" * 70)

    # --- Example 3: Forbidden Zones ---
    print("\n>>> Example 3: Forbidden Zones (Maintenance) & Specific Cranes")
    problem3 = create_example_problem()
    
    # Print crane setup
    print(f"Loaded {len(problem3.cranes)} cranes.")
    for c in problem3.cranes:
        print(f"  - {c.name} ({c.crane_type.value}): range {c.berth_range_start}-{c.berth_range_end}m, prod={c.max_productivity}")

    solution3 = solve(problem3, time_limit_seconds=60)
    print_solution(problem3, solution3)
    plot_solution(problem3, solution3, os.path.join(OUTPUT_DIR, "gantt_forbidden_cranes.png"))
    
    # New Crane Schedule Plot
    from visualization import plot_crane_schedule, plot_vessel_execution_gantt
    plot_crane_schedule(problem3, solution3, os.path.join(OUTPUT_DIR, "cranes_schedule.png"))
    plot_vessel_execution_gantt(problem3, solution3, os.path.join(OUTPUT_DIR, "vessel_execution_summary.png"))


if __name__ == "__main__":
    main()
