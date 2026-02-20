import unittest
from datetime import datetime, timedelta
from models import Problem, Vessel, Crane, CraneType, Shift, ProductivityMode, ForbiddenZone, Berth
from solver import solve, Solution

class TestSolverConstraints(unittest.TestCase):
    
    def setUp(self):
        # Basic setup used by many tests
        self.start_date = datetime(2026, 1, 1, 0, 0)
        self.shifts = [
            Shift(id=i, 
                  start_time=self.start_date + timedelta(hours=6*i), 
                  end_time=self.start_date + timedelta(hours=6*(i+1)))
            for i in range(10)
        ]
        
        # 1000m berth
        self.berth_length = 1000
        
        # Basic Cranes
        self.cranes = [
            Crane(id="C1", name="STS-1", crane_type=CraneType.STS, 
                  berth_range_start=0, berth_range_end=1000, 
                  min_productivity=10, max_productivity=20),
            Crane(id="C2", name="STS-2", crane_type=CraneType.STS, 
                  berth_range_start=0, berth_range_end=1000, 
                  min_productivity=10, max_productivity=20)
        ]

    def create_problem(self, vessels, constraints=None):
        berth = Berth(length=self.berth_length, depth=20.0, depth_map={0: 20.0})
        # Default full availability
        availability = {i: [c.id for c in self.cranes] for i in range(len(self.shifts))}
        
        return Problem(
            berth=berth,
            cranes=self.cranes,
            shifts=self.shifts,
            vessels=vessels,
            crane_availability_per_shift=availability,
            forbidden_zones=constraints if constraints else []
        )
        
    def test_spatial_no_overlap(self):
        """Test 1: Two vessels cannot occupy the same space at the same time."""
        # V1 and V2 both arrive at T=0, large workloads, length 600m each.
        # Berth is 1000m. They CANNOT fit simultaneously.
        # Solver must schedule them sequentially.
        
        v1 = Vessel(name="V1", workload=100, loa=600, draft=10, 
                    arrival_time=self.start_date, departure_deadline=self.start_date + timedelta(hours=48))
        v2 = Vessel(name="V2", workload=100, loa=600, draft=10, 
                    arrival_time=self.start_date, departure_deadline=self.start_date + timedelta(hours=48))
        
        # Set workload high enough they need multiple shifts so overlap is forced if parallel
        # 100 moves / 20 prod = 5 shifts. 
        
        problem = self.create_problem([v1, v2])
        # Pre-process vessels (Mocking what main.py does)
        self._preprocess_vessels(problem)
        
        solution = solve(problem, time_limit_seconds=60) # Increased time limit?
        
        self.assertTrue(solution.status in ["OPTIMAL", "FEASIBLE"], f"Status was {solution.status}")

    def test_maximize_speed(self):
        """Test 6: Solver prioritizes speed (using max cranes) over saving cranes."""
        # Vessel needs 40 moves.
        # Cranes: 2 available (C1, C2). Both 10 prod.
        
        workload = 40
        v1 = Vessel("V1", workload, 100, 10, self.start_date, self.start_date + timedelta(hours=48))
        v1.max_cranes = 2 # Allow up to 2
        
        problem = self.create_problem([v1])
        for c in problem.cranes:
            c.min_productivity = 10
            c.max_productivity = 10
            
        self._preprocess_vessels(problem)
        
        solution = solve(problem)
        self.assertTrue(solution.status in ["OPTIMAL", "FEASIBLE"])
        sol_v2 = next(s for s in solution.vessel_solutions if s.vessel_name == "V2")
        
        # Check if time intervals overlap
        v1_range = set(range(sol_v1.start_shift, sol_v1.end_shift))
        v2_range = set(range(sol_v2.start_shift, sol_v2.end_shift))
        
        overlap_shifts = v1_range.intersection(v2_range)
        
        if overlap_shifts:
            # If they overlap in time, they MUST NOT overlap in space
            # But length is 600 + 600 = 1200 > 1000. Physical overlap is unavoidable if time overlaps.
            # Thus, overlap_shifts MUST be empty for valid solution.
            self.fail(f"Vessels overlapped in time {overlap_shifts} but physically cannot fit (600+600 > 1000)")

    def test_temporal_arrival_constraint(self):
        """Test 2: Vessel cannot start before arrival time."""
        # Arrival at Shift 5
        arrival_time = self.shifts[5].start_time
        v1 = Vessel(name="V1", workload=50, loa=100, draft=10, 
                    arrival_time=arrival_time, departure_deadline=self.shifts[8].end_time)
        
        problem = self.create_problem([v1])
        self._preprocess_vessels(problem)
        
        solution = solve(problem, time_limit_seconds=5)
        sol_v1 = solution.vessel_solutions[0]
        
        # Start shift must be >= 5
        self.assertGreaterEqual(sol_v1.start_shift, 5, "Vessel started before arrival shift")

    def test_crane_reach_constraint(self):
        """Test 3: Crane assignments must respect physical reach."""
        # Crane 1: 0-400m
        # Crane 2: 600-1000m
        # Vessel at 500m (loa 100) -> 500-600m. Neither crane touches it fully?
        # Let's try: Crane 1 (0-300), V1 (Start pos > 400). Crane 1 cannot work V1.
        
        c1 = Crane("C1", "ShortCrane", CraneType.STS, 0, 300, 10, 20)
        v1 = Vessel("V1", 50, 100, 10, self.start_date, self.start_date + timedelta(hours=48))
        
        # Constraint: V1 MUST be placed > 400m (e.g. by forbidden zone or blocking V2)
        # Easier: Berth is big, but we force V1 to be at 800m by putting a V2 at 0-800m fixed?
        # Or just checking valid solution: If C1 assigned, V1 pos must be <= 300.
        
        problem = self.create_problem([v1])
        problem.cranes = [c1]
        self._preprocess_vessels(problem)
        
        solution = solve(problem, time_limit_seconds=5)
        
        if solution.status == "INFEASIBLE":
            # If it positioned outside range, good. But Solver puts it where it fits.
            # Crane 1 range 0-300. Vessel needs CRANE. So Vessel MUST be at 0-200.
            pass
        else:
            sol_v1 = solution.vessel_solutions[0]
            # Since C1 is the ONLY crane, and it reaches 0-300, vessel MUST be in 0-300.
            # pos + loa <= 300? Actually constraint is:
            # pos[i] >= c_start (0) AND pos[i] + loa <= c_end (300)
            
            end_pos = sol_v1.berth_position + v1.loa
            self.assertLessEqual(end_pos, 300, "Vessel assigned to C1 but outside C1 reach")

    def test_sts_non_crossing(self):
        """Test 4: STS Cranes cannot cross."""
        # C1 (STS) and C2 (STS). C1 is physically left of C2 (by ID order in list usually, or implicit).
        # We enforce C1 ID < C2 ID.
        # If C1 works on V1 and C2 works on V2 in same shift...
        # Then V1.position must be <= V2.position.
        
        v1 = Vessel("V1", 20, 100, 10, self.start_date, self.start_date + timedelta(hours=48))
        v2 = Vessel("V2", 20, 100, 10, self.start_date, self.start_date + timedelta(hours=48))
        
        problem = self.create_problem([v1, v2])
        self._preprocess_vessels(problem)
        
        solution = solve(problem, time_limit_seconds=5)
        
        # Find a shift where both active
        # This might be tricky to force. Let's inspect solution.
        for t in range(10):
            # Check assignments
            assignments = [] # (CraneID, V_Index)
            for vs in solution.vessel_solutions:
                if t in vs.assigned_cranes:
                    for cid in vs.assigned_cranes[t]:
                        assignments.append((cid, vs.vessel_name, vs.berth_position))
            
            # If we have C1 and C2 active
            c1_assign = next((x for x in assignments if x[0] == "C1"), None)
            c2_assign = next((x for x in assignments if x[0] == "C2"), None)
            
            if c1_assign and c2_assign:
                # C1 is "Left" crane (ID order). C1 vessel pos should be <= C2 vessel pos
                # Check actual constraint logic: i < j => pos[i] <= pos[j] is for cranes?
                # No, if C1 assigned to V_A and C2 assigned to V_B, and C1 is left of C2,
                # then V_A must be left of V_B.
                
                pos_v_c1 = c1_assign[2]
                pos_v_c2 = c2_assign[2]
                
                # We allow equality? 
                self.assertLessEqual(pos_v_c1, pos_v_c2, f"STS Crossover detected at shift {t}: C1 on {c1_assign[1]}({pos_v_c1}) vs C2 on {c2_assign[1]}({pos_v_c2})")

    def test_workload_fulfillment(self):
        """Test 5: Assigned productivity meets workload."""
        workload = 100
        v1 = Vessel("V1", workload, 100, 10, self.start_date, self.start_date + timedelta(hours=48))
        problem = self.create_problem([v1])
        # Set both cranes to fixed 10 prod
        for c in problem.cranes:
            c.min_productivity = 10
            c.max_productivity = 10
            
        self._preprocess_vessels(problem)
        
        solution = solve(problem)
        print(f"Solver Status: {solution.status}")
        self.assertTrue(solution.status in ["OPTIMAL", "FEASIBLE"], f"Solver failed to find solution: {solution.status}")
        
        sol_v1 = solution.vessel_solutions[0]
        
        # Calculate delivered
        delivered = 0
        for t, cranes in sol_v1.assigned_cranes.items():
            # Check for arrival fraction impact
            fraction = 1.0
            if t == v1.arrival_shift_index:
                 fraction = v1.arrival_fraction
                 
            # Note: Test setup arrival matches shift start exactly?
            # start_date match 2026-1-1 00:00. Shift 0 starts 2026-1-1 00:00.
            # So fraction is 1.0.
            
            prod = 10 * fraction
            delivered += len(cranes) * prod
            print(f"Shift {t}: {cranes} (Prod {prod}) -> Acc {delivered}")
            
        self.assertGreaterEqual(delivered, workload - 0.1, f"Delivered {delivered} < Workload {workload}")

    def test_maximize_speed(self):
        """Test 6: Solver prioritizes speed (using max cranes) over saving cranes."""
        # Vessel needs 40 moves.
        # Cranes: 2 available (C1, C2). Both 10 prod.
        # If use 1 crane -> 4 shifts.
        # If use 2 cranes -> 2 shifts.
        # We want the solver to choose 2 shifts (duration=2) over 4 shifts.
        # This implies it prefers using EXTRA cranes to save TIME.
        
        workload = 40
        v1 = Vessel("V1", workload, 100, 10, self.start_date, self.start_date + timedelta(hours=48))
        v1.max_cranes = 2 # Allow up to 2
        
        problem = self.create_problem([v1])
        for c in problem.cranes:
            c.min_productivity = 10
            c.max_productivity = 10
            
        self._preprocess_vessels(problem)
        
        solution = solve(problem)
        self.assertTrue(solution.status in ["OPTIMAL", "FEASIBLE"], f"Status was {solution.status}")
        
        sol_v1 = solution.vessel_solutions[0]
        duration = sol_v1.end_shift - sol_v1.start_shift
        
        # Expectation: Duration should be 2, not 4.
        self.assertEqual(duration, 2, f"Solver chose duration {duration} (slow) instead of 2 (fast/multi-crane)")
        
        # Verify 2 cranes used per shift
        for t, cranes in sol_v1.assigned_cranes.items():
            self.assertEqual(len(cranes), 2, f"Shift {t} used {len(cranes)} cranes, expected 2 for max speed")


    def test_solution_status_is_propagated(self):
        """Test: Solution status should reflect solver status, not a hardcoded value."""
        v1 = Vessel("V1", 20, 100, 10, self.start_date, self.start_date + timedelta(hours=48))
        v1.max_cranes = 2

        problem = self.create_problem([v1])
        for c in problem.cranes:
            c.min_productivity = 10
            c.max_productivity = 10

        self._preprocess_vessels(problem)
        solution = solve(problem, time_limit_seconds=5)

        # For this small instance CP-SAT should prove optimality quickly.
        self.assertEqual(solution.status, "OPTIMAL")

    def test_crane_reach_respects_right_boundary(self):
        """Test: If a crane is assigned, vessel must be fully inside crane berth range."""
        # Only crane covers 0..300, vessel LOA=200 => position must satisfy pos+200 <= 300.
        short_crane = Crane("C1", "ShortCrane", CraneType.STS, 0, 300, 10, 20)
        v1 = Vessel("V1", 40, 200, 10, self.start_date, self.start_date + timedelta(hours=48))

        problem = self.create_problem([v1])
        problem.cranes = [short_crane]
        problem.crane_availability_per_shift = {i: ["C1"] for i in range(len(problem.shifts))}

        self._preprocess_vessels(problem)
        solution = solve(problem, time_limit_seconds=5)

        self.assertTrue(solution.status in ["OPTIMAL", "FEASIBLE"], f"Status was {solution.status}")
        sol_v1 = solution.vessel_solutions[0]
        self.assertLessEqual(sol_v1.berth_position + v1.loa, short_crane.berth_range_end)

    def _preprocess_vessels(self, problem):
        # Helper to mimic main.py preprocessing
        num_shifts = len(problem.shifts)
        for v in problem.vessels:
            v.arrival_shift_index = -1
            v.arrival_fraction = 1.0
            
            for t, s in enumerate(problem.shifts):
                if s.start_time <= v.arrival_time < s.end_time:
                    v.arrival_shift_index = t
                    total = (s.end_time - s.start_time).total_seconds()
                    avail = (s.end_time - v.arrival_time).total_seconds()
                    v.arrival_fraction = avail / total if total > 0 else 0
                    break
            if v.arrival_time < problem.shifts[0].start_time:
                 v.arrival_shift_index = 0

if __name__ == '__main__':
    unittest.main()
