package com.port.solver.engine;

import com.google.ortools.Loader;
import com.google.ortools.sat.*;
import com.port.solver.model.*;
import com.port.solver.model.Berth;
import com.port.solver.model.Solution;

import java.util.*;
import java.util.stream.Collectors;

/**
 * BAP + QCAP solver using Google OR-Tools CP-SAT.
 * Direct port of solver.py - maintains identical mathematical formulation.
 */
public class CpSatSolver {

    private static boolean nativeLoaded = false;

    private static synchronized void ensureNativeLoaded() {
        if (!nativeLoaded) {
            Loader.loadNativeLibraries();
            nativeLoaded = true;
        }
    }

    // Key class for triple-key maps: (craneId, vesselIndex, shiftIndex)
    private record CraneVesselShift(String craneId, int vesselIdx, int shiftIdx) {
    }

    /**
     * Solve the integrated BAP + QCAP problem.
     *
     * @param problem          The problem instance to solve.
     * @param timeLimitSeconds Maximum solver time.
     * @return A Solution object with berth positions, schedules, and crane
     *         assignments.
     */
    public Solution solve(Problem problem, int timeLimitSeconds) {
        ensureNativeLoaded();

        CpModel model = new CpModel();
        Berth berth = problem.getBerth();
        List<Vessel> vessels = problem.getVessels();
        List<Crane> cranes = problem.getCranes();
        int T = problem.getNumShifts();
        int n = vessels.size();

        // Map crane id to object for easy lookup
        Map<String, Crane> craneMap = new HashMap<>();
        for (Crane c : cranes) {
            craneMap.put(c.getId(), c);
        }

        // =============================================
        // CONSTANTS
        // =============================================
        final int GAP = 40;

        // --- Spatial discretization for depth constraints ---
        Map<Integer, List<Integer>> validPositions = new HashMap<>();
        for (int i = 0; i < n; i++) {
            Vessel v = vessels.get(i);
            List<Integer> positions = new ArrayList<>();
            int startP = GAP;
            int endP = berth.getLength() - v.getLoa() - GAP;

            if (startP <= endP) {
                for (int p = startP; p <= endP; p++) {
                    double minDepth = Double.MAX_VALUE;
                    for (int m = 0; m < v.getLoa(); m++) {
                        minDepth = Math.min(minDepth, berth.getDepthAt(p + m));
                    }
                    if (minDepth >= v.getDraft()) {
                        positions.add(p);
                    }
                }
            }

            if (positions.isEmpty()) {
                System.out.printf("WARNING: No valid berth position for vessel %s "
                        + "(draft=%.1f, loa=%d) with %dm margins%n",
                        v.getName(), v.getDraft(), v.getLoa(), GAP);
                return new Solution(Collections.emptyList(), 0, "INFEASIBLE");
            }
            validPositions.put(i, positions);
        }

        // =============================================
        // DECISION VARIABLES
        // =============================================

        // 1. Berth position p_i
        Map<Integer, IntVar> pos = new HashMap<>();
        for (int i = 0; i < n; i++) {
            Vessel v = vessels.get(i);
            List<Integer> vp = validPositions.get(i);
            int minPos = vp.stream().mapToInt(Integer::intValue).min().orElse(0);
            int maxPos = vp.stream().mapToInt(Integer::intValue).max().orElse(berth.getLength());

            pos.put(i, model.newIntVar(minPos, maxPos, "pos_" + v.getName()));

            // Restrict to valid positions (depth constraint)
            if (vp.size() < (maxPos - minPos + 1)) {
                long[][] tuples = new long[vp.size()][1];
                for (int j = 0; j < vp.size(); j++) {
                    tuples[j][0] = vp.get(j);
                }
                model.addAllowedAssignments(new IntVar[] { pos.get(i) }).addTuples(tuples);
            }
        }

        // 2. Start/End shifts
        Map<Integer, IntVar> start = new HashMap<>();
        Map<Integer, IntVar> end = new HashMap<>();
        Map<Integer, IntVar> duration = new HashMap<>();

        // Active indicator
        Map<Long, BoolVar> active = new HashMap<>(); // key = i * T + t

        // Reification helpers
        Map<Long, BoolVar> isAfterStartDict = new HashMap<>();
        Map<Long, BoolVar> isBeforeEndDict = new HashMap<>();

        for (int i = 0; i < n; i++) {
            Vessel v = vessels.get(i);

            int minStart = v.getArrivalShiftIndex() >= 0 ? v.getArrivalShiftIndex() : 0;
            if (minStart >= T)
                minStart = T - 1;

            start.put(i, model.newIntVar(minStart, T - 1, "start_" + v.getName()));
            end.put(i, model.newIntVar(minStart + 1, T, "end_" + v.getName()));
            duration.put(i, model.newIntVar(1, T, "dur_" + v.getName()));

            // Start >= arrival
            model.addGreaterOrEqual(start.get(i), minStart);

            // end == start + duration
            model.addEquality(end.get(i), LinearExpr.sum(new LinearArgument[] { start.get(i), duration.get(i) }));

            // Create active booleans for each shift
            for (int t = 0; t < T; t++) {
                long key = (long) i * T + t;
                BoolVar activeVar = model.newBoolVar("active_" + v.getName() + "_" + t);
                active.put(key, activeVar);

                // Reification: active <=> start <= t < end
                BoolVar isAfterStart = model.newBoolVar(v.getName() + "_after_start_" + t);
                BoolVar isBeforeEnd = model.newBoolVar(v.getName() + "_before_end_" + t);

                isAfterStartDict.put(key, isAfterStart);
                isBeforeEndDict.put(key, isBeforeEnd);

                // start <= t <=> isAfterStart
                model.addLessOrEqual(start.get(i), t).onlyEnforceIf(isAfterStart);
                model.addGreaterOrEqual(start.get(i), t + 1).onlyEnforceIf(isAfterStart.not());

                // end > t <=> isBeforeEnd (i.e. end >= t+1)
                model.addGreaterOrEqual(end.get(i), t + 1).onlyEnforceIf(isBeforeEnd);
                model.addLessOrEqual(end.get(i), t).onlyEnforceIf(isBeforeEnd.not());

                // active <=> (isAfterStart AND isBeforeEnd)
                model.addBoolAnd(new Literal[] { isAfterStart, isBeforeEnd }).onlyEnforceIf(activeVar);
                model.addBoolOr(new Literal[] { isAfterStart.not(), isBeforeEnd.not() }).onlyEnforceIf(activeVar.not());
            }
        }

        // 3. Crane Moves
        // moves[craneId, vesselIdx, shiftIdx] = Number of moves
        Map<CraneVesselShift, IntVar> moves = new HashMap<>();

        for (int t = 0; t < T; t++) {
            List<String> availableCraneIds = problem.getCraneAvailabilityPerShift().getOrDefault(t,
                    Collections.emptyList());

            for (Crane c : cranes) {
                if (!availableCraneIds.contains(c.getId()))
                    continue;

                for (int i = 0; i < n; i++) {
                    Vessel v = vessels.get(i);

                    // Skip if shift is before arrival
                    int arrIdx = v.getArrivalShiftIndex() >= 0 ? v.getArrivalShiftIndex() : 0;
                    if (t < arrIdx)
                        continue;

                    // Max prod limit logic
                    int limit = c.getMaxProductivity();
                    if (v.getProductivityPreference() == ProductivityMode.MIN) {
                        limit = c.getMinProductivity();
                    } else if (v.getProductivityPreference() == ProductivityMode.INTERMEDIATE) {
                        limit = (c.getMinProductivity() + c.getMaxProductivity()) / 2;
                    }

                    // Arrival fraction
                    if (t == v.getArrivalShiftIndex()) {
                        limit = (int) (limit * v.getArrivalFraction());
                    }

                    if (limit > 0) {
                        CraneVesselShift cvs = new CraneVesselShift(c.getId(), i, t);
                        IntVar mv = model.newIntVar(0, limit, "moves_" + c.getId() + "_" + i + "_" + t);
                        moves.put(cvs, mv);

                        long key = (long) i * T + t;
                        // active=0 => moves=0
                        model.addEquality(mv, 0).onlyEnforceIf(active.get(key).not());

                        // If shift is before vessel start, moves MUST be 0
                        if (isAfterStartDict.containsKey(key)) {
                            model.addEquality(mv, 0).onlyEnforceIf(isAfterStartDict.get(key).not());
                        }
                    }
                }
            }
        }

        // =============================================
        // CONSTRAINTS
        // =============================================

        // --- Spatial constraints ---
        for (int i = 0; i < n; i++) {
            Vessel v = vessels.get(i);
            model.addGreaterOrEqual(pos.get(i), GAP);
            model.addLessOrEqual(
                    LinearExpr.sum(new LinearArgument[] { pos.get(i), LinearExpr.constant(v.getLoa()) }),
                    berth.getLength() - GAP);
        }

        // --- Non-overlap: spatial + temporal ---
        IntervalVar[] xIntervals = new IntervalVar[n];
        IntervalVar[] yIntervals = new IntervalVar[n];

        for (int i = 0; i < n; i++) {
            Vessel v = vessels.get(i);
            int xSize = v.getLoa() + GAP;
            xIntervals[i] = model.newFixedSizeIntervalVar(pos.get(i), xSize, "x_int_" + v.getName());
            yIntervals[i] = model.newIntervalVar(start.get(i), duration.get(i), end.get(i), "y_int_" + v.getName());
        }
        // model.addNoOverlap2D(Arrays.asList(xIntervals), Arrays.asList(yIntervals));
        NoOverlap2dConstraint noOverlap = model.addNoOverlap2D();
        for (int i = 0; i < n; i++) {
            noOverlap.addRectangle(xIntervals[i], yIntervals[i]);
        }

        // --- Forbidden Zones ---
        if (problem.getSolverRule("enable_forbidden_zones", true)) {
            for (int i = 0; i < n; i++) {
                Vessel v = vessels.get(i);
                for (int zIdx = 0; zIdx < problem.getForbiddenZones().size(); zIdx++) {
                    ForbiddenZone z = problem.getForbiddenZones().get(zIdx);
                    // Use constant IntVars for fixed forbidden zone positions
                    IntVar zXStart = model.newConstant(z.getStartBerthPosition());
                    IntervalVar zXInterval = model.newFixedSizeIntervalVar(
                            zXStart,
                            z.getEndBerthPosition() - z.getStartBerthPosition(),
                            "z_x_" + zIdx + "_" + i);
                    IntVar zYStart = model.newConstant(z.getStartShift());
                    IntervalVar zYInterval = model.newFixedSizeIntervalVar(
                            zYStart,
                            z.getEndShift() - z.getStartShift(),
                            "z_y_" + zIdx + "_" + i);
                    NoOverlap2dConstraint fzOverlap = model.addNoOverlap2D();
                    fzOverlap.addRectangle(xIntervals[i], yIntervals[i]);
                    fzOverlap.addRectangle(zXInterval, zYInterval);
                }
            }
        }

        // --- Workload Fulfillment ---
        for (int i = 0; i < n; i++) {
            Vessel v = vessels.get(i);
            List<IntVar> vMoves = new ArrayList<>();
            for (int t = 0; t < T; t++) {
                for (Crane c : cranes) {
                    CraneVesselShift cvs = new CraneVesselShift(c.getId(), i, t);
                    if (moves.containsKey(cvs)) {
                        vMoves.add(moves.get(cvs));
                    }
                }
            }
            if (!vMoves.isEmpty()) {
                model.addGreaterOrEqual(
                        LinearExpr.sum(vMoves.toArray(new IntVar[0])),
                        v.getWorkload());
            }
        }

        // --- Crane Capacity ---
        if (problem.getSolverRule("enable_crane_capacity", true)) {
            for (int t = 0; t < T; t++) {
                for (Crane c : cranes) {
                    List<IntVar> cMovesInShift = new ArrayList<>();
                    for (int i = 0; i < n; i++) {
                        CraneVesselShift cvs = new CraneVesselShift(c.getId(), i, t);
                        if (moves.containsKey(cvs)) {
                            cMovesInShift.add(moves.get(cvs));
                        }
                    }
                    if (!cMovesInShift.isEmpty()) {
                        model.addLessOrEqual(
                                LinearExpr.sum(cMovesInShift.toArray(new IntVar[0])),
                                c.getMaxProductivity());
                    }
                }
            }
        }

        // --- Max Cranes per Vessel + Crane Active Indicators ---
        Map<CraneVesselShift, BoolVar> craneActiveIndicators = new HashMap<>();
        for (Map.Entry<CraneVesselShift, IntVar> entry : moves.entrySet()) {
            CraneVesselShift cvs = entry.getKey();
            IntVar mVar = entry.getValue();
            BoolVar bAct = model.newBoolVar("ind_" + cvs.craneId() + "_" + cvs.vesselIdx() + "_" + cvs.shiftIdx());
            model.addGreaterOrEqual(mVar, 1).onlyEnforceIf(bAct);
            model.addEquality(mVar, 0).onlyEnforceIf(bAct.not());
            craneActiveIndicators.put(cvs, bAct);
        }

        if (problem.getSolverRule("enable_max_cranes", true)) {
            for (int i = 0; i < n; i++) {
                Vessel v = vessels.get(i);
                for (int t = 0; t < T; t++) {
                    List<BoolVar> activeVars = new ArrayList<>();
                    for (Crane c : cranes) {
                        CraneVesselShift cvs = new CraneVesselShift(c.getId(), i, t);
                        if (craneActiveIndicators.containsKey(cvs)) {
                            activeVars.add(craneActiveIndicators.get(cvs));
                        }
                    }

                    // Max cranes constraint
                    if (!activeVars.isEmpty()) {
                        model.addLessOrEqual(
                                LinearExpr.sum(activeVars.toArray(new IntVar[0])),
                                v.getMaxCranes());
                    }

                    // Minimum work if active
                    if (problem.getSolverRule("enable_min_cranes_on_arrival", true)) {
                        List<IntVar> movesVars = new ArrayList<>();
                        for (Crane c : cranes) {
                            CraneVesselShift cvs = new CraneVesselShift(c.getId(), i, t);
                            if (moves.containsKey(cvs)) {
                                movesVars.add(moves.get(cvs));
                            }
                        }
                        if (!movesVars.isEmpty()) {
                            long key = (long) i * T + t;
                            model.addGreaterOrEqual(
                                    LinearExpr.sum(movesVars.toArray(new IntVar[0])),
                                    1).onlyEnforceIf(active.get(key));
                        }
                    }
                }
            }
        }

        // --- Crane Reach Constraints ---
        if (problem.getSolverRule("enable_crane_reach", true)) {
            for (Map.Entry<CraneVesselShift, BoolVar> entry : craneActiveIndicators.entrySet()) {
                CraneVesselShift cvs = entry.getKey();
                BoolVar bAct = entry.getValue();
                Crane c = craneMap.get(cvs.craneId());
                if (c != null) {
                    model.addGreaterOrEqual(pos.get(cvs.vesselIdx()), c.getBerthRangeStart()).onlyEnforceIf(bAct);
                }
            }
        }

        // --- STS Non-Crossing ---
        if (problem.getSolverRule("enable_sts_non_crossing", true)) {
            List<Crane> stsCranes = new ArrayList<>();
            for (Crane c : cranes) {
                if (c.getCraneType() == CraneType.STS) {
                    stsCranes.add(c);
                }
            }

            for (int idx1 = 0; idx1 < stsCranes.size(); idx1++) {
                for (int idx2 = idx1 + 1; idx2 < stsCranes.size(); idx2++) {
                    Crane c1 = stsCranes.get(idx1);
                    Crane c2 = stsCranes.get(idx2);

                    for (int t = 0; t < T; t++) {
                        for (int iA = 0; iA < n; iA++) {
                            for (int iB = 0; iB < n; iB++) {
                                if (iA == iB)
                                    continue;

                                CraneVesselShift k1 = new CraneVesselShift(c1.getId(), iA, t);
                                CraneVesselShift k2 = new CraneVesselShift(c2.getId(), iB, t);

                                if (craneActiveIndicators.containsKey(k1) && craneActiveIndicators.containsKey(k2)) {
                                    BoolVar bothActive = model.newBoolVar(
                                            "cross_" + t + "_" + c1.getId() + "_" + c2.getId() + "_" + iA + "_" + iB);
                                    model.addBoolAnd(new Literal[] {
                                            craneActiveIndicators.get(k1),
                                            craneActiveIndicators.get(k2) }).onlyEnforceIf(bothActive);
                                    model.addLessOrEqual(pos.get(iA), pos.get(iB)).onlyEnforceIf(bothActive);
                                }
                            }
                        }
                    }
                }
            }
        }

        // --- Shifting Gang Constraint ---
        if (problem.getSolverRule("enable_shifting_gang", true)) {
            for (int t = 0; t < T; t++) {
                List<String> availableCraneIds = problem.getCraneAvailabilityPerShift().getOrDefault(t,
                        Collections.emptyList());

                for (Crane c : cranes) {
                    if (!availableCraneIds.contains(c.getId()))
                        continue;

                    for (int i = 0; i < n; i++) {
                        Vessel v = vessels.get(i);
                        CraneVesselShift cvs = new CraneVesselShift(c.getId(), i, t);
                        if (!moves.containsKey(cvs))
                            continue;

                        IntVar mv = moves.get(cvs);

                        // Re-calculate limit
                        int limit = c.getMaxProductivity();
                        if (v.getProductivityPreference() == ProductivityMode.MIN) {
                            limit = c.getMinProductivity();
                        } else if (v.getProductivityPreference() == ProductivityMode.INTERMEDIATE) {
                            limit = (c.getMinProductivity() + c.getMaxProductivity()) / 2;
                        }

                        if (t == v.getArrivalShiftIndex()) {
                            limit = (int) (limit * v.getArrivalFraction());
                        }

                        // is_intermediate <=> t <= end[i] - 2
                        BoolVar isIntermediate = model.newBoolVar(
                                "is_intermediate_" + c.getId() + "_" + v.getName() + "_" + t);

                        // t <= end[i] - 2 => end[i] >= t + 2
                        model.addGreaterOrEqual(end.get(i), t + 2).onlyEnforceIf(isIntermediate);
                        model.addLessOrEqual(end.get(i), t + 1).onlyEnforceIf(isIntermediate.not());

                        if (craneActiveIndicators.containsKey(cvs)) {
                            BoolVar bAct = craneActiveIndicators.get(cvs);
                            // If (active AND intermediate) => moves == limit
                            model.addEquality(mv, limit).onlyEnforceIf(new Literal[] { bAct, isIntermediate });
                        }
                    }
                }
            }
        }

        // =============================================
        // OBJECTIVE FUNCTION
        // =============================================
        IntVar makespan = model.newIntVar(0, T, "makespan");
        for (int i = 0; i < n; i++) {
            model.addGreaterOrEqual(makespan, end.get(i));
        }

        IntVar totalTurnaround = model.newIntVar(0, T * n * 2, "total_turnaround");
        List<IntVar> turnaroundTerms = new ArrayList<>();

        for (int i = 0; i < n; i++) {
            Vessel v = vessels.get(i);
            int refStart = v.getArrivalShiftIndex() >= 0 ? v.getArrivalShiftIndex() : 0;

            IntVar tI = model.newIntVar(-T, T, "turnaround_" + v.getName());
            model.addEquality(tI,
                    LinearExpr.newBuilder().addTerm(end.get(i), 1).add(-refStart).build());
            turnaroundTerms.add(tI);
        }
        model.addEquality(totalTurnaround, LinearExpr.sum(turnaroundTerms.toArray(new IntVar[0])));

        // Total crane usage
        List<BoolVar> craneActiveVars = new ArrayList<>();
        for (Map.Entry<CraneVesselShift, IntVar> entry : moves.entrySet()) {
            CraneVesselShift cvs = entry.getKey();
            IntVar mVar = entry.getValue();
            BoolVar bVar = model
                    .newBoolVar("obj_active_" + cvs.craneId() + "_" + cvs.vesselIdx() + "_" + cvs.shiftIdx());
            model.addGreaterThan(mVar, 0).onlyEnforceIf(bVar);
            model.addEquality(mVar, 0).onlyEnforceIf(bVar.not());
            craneActiveVars.add(bVar);
        }

        IntVar totalCranesUsed = model.newIntVar(0, craneActiveVars.size() + 1, "total_cranes");
        if (!craneActiveVars.isEmpty()) {
            model.addEquality(totalCranesUsed, LinearExpr.sum(craneActiveVars.toArray(new IntVar[0])));
        } else {
            model.addEquality(totalCranesUsed, 0);
        }

        // --- Yard Zone Alignment ---
        IntVar totalYardDistance = model.newIntVar(0, (long) berth.getLength() * n, "total_yard_distance");
        List<IntVar> yardDistTerms = new ArrayList<>();

        if (problem.getSolverRule("enable_yard_preferences", true)) {
            Map<Integer, YardQuayZone> yardZoneMap = new HashMap<>();
            for (YardQuayZone z : problem.getYardQuayZones()) {
                yardZoneMap.put(z.getId(), z);
            }

            for (int i = 0; i < n; i++) {
                Vessel v = vessels.get(i);
                if (v.getTargetZones() != null && !v.getTargetZones().isEmpty()) {
                    // Find best zone by volume
                    YardQuayZonePreference bestPref = v.getTargetZones().stream()
                            .max(Comparator.comparingDouble(YardQuayZonePreference::getVolume))
                            .orElse(null);

                    if (bestPref != null && yardZoneMap.containsKey(bestPref.getYardQuayZoneId())) {
                        YardQuayZone zone = yardZoneMap.get(bestPref.getYardQuayZoneId());
                        int zoneCenter = (zone.getStartDist() + zone.getEndDist()) / 2;

                        IntVar distVar = model.newIntVar(0, berth.getLength(), "yard_dist_" + v.getName());

                        // vCenter = pos[i] + loa/2
                        // dist >= vCenter - zoneCenter
                        // dist >= zoneCenter - vCenter
                        LinearExpr vCenter = LinearExpr.newBuilder().addTerm(pos.get(i), 1).add(v.getLoa() / 2)
                                .build();
                        model.addGreaterOrEqual(distVar,
                                LinearExpr.newBuilder().addTerm(pos.get(i), 1).add(v.getLoa() / 2 - zoneCenter)
                                        .build());
                        model.addGreaterOrEqual(distVar,
                                LinearExpr.newBuilder().addTerm(pos.get(i), -1).add(zoneCenter - v.getLoa() / 2)
                                        .build());

                        yardDistTerms.add(distVar);
                    }
                }
            }
        }

        if (!yardDistTerms.isEmpty()) {
            model.addEquality(totalYardDistance, LinearExpr.sum(yardDistTerms.toArray(new IntVar[0])));
        } else {
            model.addEquality(totalYardDistance, 0);
        }

        // --- WEIGHTS ---
        long W_START_DELAY = 5000;
        long W_TURNAROUND = 500;
        long W_MAKESPAN = 100;
        long W_CRANES = -100;
        long W_YARD_DIST = 1;

        // Calculate Start Delay
        IntVar totalStartDelay = model.newIntVar(0, (long) T * n, "total_start_delay");
        List<IntVar> startDelayTerms = new ArrayList<>();

        for (int i = 0; i < n; i++) {
            Vessel v = vessels.get(i);
            int refStart = v.getArrivalShiftIndex() >= 0 ? v.getArrivalShiftIndex() : 0;
            IntVar delay = model.newIntVar(0, T, "start_delay_" + v.getName());
            model.addEquality(delay, LinearExpr.newBuilder().addTerm(start.get(i), 1).add(-refStart).build());
            startDelayTerms.add(delay);
        }
        model.addEquality(totalStartDelay, LinearExpr.sum(startDelayTerms.toArray(new IntVar[0])));

        // Minimize weighted sum
        model.minimize(LinearExpr.newBuilder().addWeightedSum(
                new LinearArgument[] { totalTurnaround, totalStartDelay, makespan, totalCranesUsed, totalYardDistance },
                new long[] { W_TURNAROUND, W_START_DELAY, W_MAKESPAN, W_CRANES, W_YARD_DIST }).build());

        // =============================================
        // SOLVE
        // =============================================
        CpSolver solver = new CpSolver();
        solver.getParameters().setMaxTimeInSeconds(timeLimitSeconds);
        solver.getParameters().setLogSearchProgress(true);
        solver.getParameters().setNumWorkers(8);

        CpSolverStatus status = solver.solve(model);
        String statusName = switch (status) {
            case OPTIMAL -> "OPTIMAL";
            case FEASIBLE -> "FEASIBLE";
            case INFEASIBLE -> "INFEASIBLE";
            case MODEL_INVALID -> "MODEL_INVALID";
            default -> "UNKNOWN";
        };

        if (status != CpSolverStatus.OPTIMAL && status != CpSolverStatus.FEASIBLE) {
            return new Solution(Collections.emptyList(), 0, statusName);
        }

        // =============================================
        // EXTRACT SOLUTION
        // =============================================
        return extractSolution(problem, solver, start, end, moves, pos, statusName);
    }

    private Solution extractSolution(
            Problem problem,
            CpSolver solver,
            Map<Integer, IntVar> start,
            Map<Integer, IntVar> end,
            Map<CraneVesselShift, IntVar> moves,
            Map<Integer, IntVar> pos,
            String statusName) {

        List<Vessel> vessels = problem.getVessels();
        int n = vessels.size();

        // Build assignments: vesselIdx -> shiftIdx -> list of craneIds
        Map<Integer, Map<Integer, List<String>>> assignments = new HashMap<>();
        for (int i = 0; i < n; i++) {
            assignments.put(i, new HashMap<>());
        }

        for (Map.Entry<CraneVesselShift, IntVar> entry : moves.entrySet()) {
            CraneVesselShift cvs = entry.getKey();
            long val = solver.value(entry.getValue());
            if (val > 0) {
                assignments.get(cvs.vesselIdx())
                        .computeIfAbsent(cvs.shiftIdx(), k -> new ArrayList<>())
                        .add(cvs.craneId());
            }
        }

        List<VesselSolution> vesselSolutions = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            Vessel v = vessels.get(i);
            int sVal = (int) solver.value(start.get(i));
            int eVal = (int) solver.value(end.get(i));
            int pVal = (int) solver.value(pos.get(i));

            Map<Integer, List<String>> relevantAssignments = new HashMap<>();
            for (int t = sVal; t < eVal; t++) {
                if (assignments.get(i).containsKey(t)) {
                    relevantAssignments.put(t, assignments.get(i).get(t));
                }
            }

            vesselSolutions.add(new VesselSolution(v.getName(), pVal, sVal, eVal, relevantAssignments));
        }

        return new Solution(vesselSolutions, solver.objectiveValue(), statusName);
    }
}
