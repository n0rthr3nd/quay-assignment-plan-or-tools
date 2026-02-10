package com.port.solver.controller;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.port.solver.config.ExampleProblemFactory;
import com.port.solver.engine.CpSatSolver;
import com.port.solver.engine.SolutionPrinter;
import com.port.solver.model.*;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;

import java.io.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.*;
import java.util.Collections;
import java.util.stream.Collectors;

/**
 * REST API controller equivalent to Flask app.py.
 */
@Controller
public class SolverController {

        private final ObjectMapper mapper = new ObjectMapper();

        @Value("${solver.output-dir:output}")
        private String outputDir;

        @Value("${solver.config-file:problem_config.json}")
        private String configFile;

        // Global solver state (equivalent to Flask's solver_state dict)
        // Use synchronizedMap wrapping HashMap to allow null values (which
        // ConcurrentHashMap forbids)
        private final Map<String, Object> solverState = Collections.synchronizedMap(new HashMap<>());

        {
                solverState.put("running", false);
                solverState.put("status", "idle");
                solverState.put("message", "");
                solverState.put("solution_text", "");
                // ConcurrentHashMap does not allow null values. We simply don't put these keys
                // or use a placeholder if needed.
                // solverState.put("solution", null);
                // solverState.put("problem", null);
        }

        // ─── Page Routes ──────────────────────────────────────────────────

        @GetMapping("/")
        public String editor() {
                return "editor";
        }

        @GetMapping("/results")
        public String results() {
                return "results";
        }

        // ─── API Routes ───────────────────────────────────────────────────

        @GetMapping("/api/problem")
        @ResponseBody
        public Map<String, Object> getProblem() {
                return loadConfig();
        }

        @PostMapping("/api/problem")
        @ResponseBody
        public Map<String, Object> saveProblem(@RequestBody Map<String, Object> config) {
                saveConfig(config);
                return Map.of("ok", true);
        }

        @PostMapping("/api/solve")
        @ResponseBody
        public ResponseEntity<Map<String, Object>> startSolve() {
                if (Boolean.TRUE.equals(solverState.get("running"))) {
                        return ResponseEntity.status(409)
                                        .body(Map.of("ok", false, "message", "Solver already running"));
                }

                Map<String, Object> config = loadConfig();
                Thread thread = new Thread(() -> runSolverThread(config), "solver-thread");
                thread.setDaemon(true);
                thread.start();

                return ResponseEntity.ok(Map.of("ok", true, "message", "Solver started"));
        }

        @GetMapping("/api/status")
        @ResponseBody
        public Map<String, Object> getStatus() {
                return new HashMap<>(solverState);
        }

        /**
         * API endpoint to get the solution data as JSON for client-side visualization.
         */
        @GetMapping("/api/solution")
        @ResponseBody
        public ResponseEntity<Map<String, Object>> getSolutionData() {
                Object sol = solverState.get("solution");
                Object prob = solverState.get("problem");
                if (sol == null || prob == null) {
                        return ResponseEntity.ok(Map.of("available", false));
                }

                Solution solution = (Solution) sol;
                Problem problem = (Problem) prob;

                Map<String, Object> data = new HashMap<>();
                data.put("available", true);
                data.put("status", solution.getStatus());
                data.put("objectiveValue", solution.getObjectiveValue());

                // Vessel solutions for Gantt chart
                List<Map<String, Object>> vesselData = new ArrayList<>();
                Map<String, Vessel> vesselMap = new HashMap<>();
                for (Vessel v : problem.getVessels())
                        vesselMap.put(v.getName(), v);

                for (int idx = 0; idx < solution.getVesselSolutions().size(); idx++) {
                        VesselSolution vs = solution.getVesselSolutions().get(idx);
                        Vessel v = vesselMap.get(vs.getVesselName());
                        Map<String, Object> vd = new HashMap<>();
                        vd.put("name", vs.getVesselName());
                        vd.put("berthPosition", vs.getBerthPosition());
                        vd.put("loa", v.getLoa());
                        vd.put("startShift", vs.getStartShift());
                        vd.put("endShift", vs.getEndShift());
                        vd.put("arrivalShiftIndex", v.getArrivalShiftIndex());
                        vd.put("productivityPreference", v.getProductivityPreference().name());
                        vd.put("workload", v.getWorkload());
                        vd.put("assignedCranes", vs.getAssignedCranes());
                        vd.put("colorIndex", idx);
                        vesselData.add(vd);
                }
                data.put("vessels", vesselData);

                // Berth info
                Map<String, Object> berthData = new HashMap<>();
                berthData.put("length", problem.getBerth().getLength());
                data.put("berth", berthData);

                // Shifts
                data.put("numShifts", problem.getNumShifts());
                List<String> shiftLabels = problem.getShifts().stream()
                                .map(Shift::toString).collect(Collectors.toList());
                data.put("shiftLabels", shiftLabels);

                // Forbidden zones
                List<Map<String, Object>> fzData = new ArrayList<>();
                for (ForbiddenZone fz : problem.getForbiddenZones()) {
                        Map<String, Object> fzMap = new HashMap<>();
                        fzMap.put("startBerthPosition", fz.getStartBerthPosition());
                        fzMap.put("endBerthPosition", fz.getEndBerthPosition());
                        fzMap.put("startShift", fz.getStartShift());
                        fzMap.put("endShift", fz.getEndShift());
                        fzMap.put("description", fz.getDescription());
                        fzData.add(fzMap);
                }
                data.put("forbiddenZones", fzData);

                // Yard zones
                List<Map<String, Object>> yzData = new ArrayList<>();
                for (YardQuayZone yz : problem.getYardQuayZones()) {
                        Map<String, Object> yzMap = new HashMap<>();
                        yzMap.put("id", yz.getId());
                        yzMap.put("name", yz.getName());
                        yzMap.put("startDist", yz.getStartDist());
                        yzMap.put("endDist", yz.getEndDist());
                        yzData.add(yzMap);
                }
                data.put("yardQuayZones", yzData);

                // Crane availability
                data.put("craneAvailability", problem.getCraneAvailabilityPerShift());

                // Crane info
                List<Map<String, Object>> craneData = new ArrayList<>();
                for (Crane cr : problem.getCranes()) {
                        Map<String, Object> cd = new HashMap<>();
                        cd.put("id", cr.getId());
                        cd.put("name", cr.getName());
                        cd.put("craneType", cr.getCraneType().name());
                        cd.put("minProductivity", cr.getMinProductivity());
                        cd.put("maxProductivity", cr.getMaxProductivity());
                        craneData.add(cd);
                }
                data.put("cranes", craneData);

                return ResponseEntity.ok(data);
        }

        // ─── Internal Methods ─────────────────────────────────────────────

        private void runSolverThread(Map<String, Object> config) {
                solverState.put("running", true);
                solverState.put("status", "running");
                solverState.put("message", "Building model and solving...");
                solverState.put("solution_text", "");
                solverState.remove("solution");
                solverState.remove("problem");

                try {
                        new File(outputDir).mkdirs();

                        Problem problem = configToProblem(config);
                        int timeLimit = 60;
                        Object settings = config.get("solver_settings");
                        if (settings instanceof Map) {
                                Object tl = ((Map<?, ?>) settings).get("time_limit_seconds");
                                if (tl != null)
                                        timeLimit = ((Number) tl).intValue();
                        }

                        CpSatSolver solver = new CpSatSolver();
                        Solution solution = solver.solve(problem, timeLimit);

                        String solutionText = SolutionPrinter.printSolution(problem, solution);
                        solverState.put("solution_text", solutionText);
                        solverState.put("solution", solution);
                        solverState.put("problem", problem);
                        solverState.put("status", "completed");
                        solverState.put("message",
                                        String.format("Solver finished: %s (Objective: %.0f)",
                                                        solution.getStatus(), solution.getObjectiveValue()));

                } catch (Exception e) {
                        solverState.put("status", "error");
                        solverState.put("message", "Error: " + e.getMessage());
                        StringWriter sw = new StringWriter();
                        e.printStackTrace(new PrintWriter(sw));
                        solverState.put("solution_text", sw.toString());
                } finally {
                        solverState.put("running", false);
                }
        }

        @SuppressWarnings("unchecked")
        private Problem configToProblem(Map<String, Object> config) {
                // Berth
                Map<String, Object> berthCfg = (Map<String, Object>) config.get("berth");
                Map<Integer, Double> depthMap = new TreeMap<>();
                List<Map<String, Object>> depthEntries = (List<Map<String, Object>>) berthCfg.get("depth_map");
                if (depthEntries != null) {
                        for (Map<String, Object> entry : depthEntries) {
                                depthMap.put(((Number) entry.get("position")).intValue(),
                                                ((Number) entry.get("depth")).doubleValue());
                        }
                }
                Berth berth = new Berth(((Number) berthCfg.get("length")).intValue(),
                                null, depthMap.isEmpty() ? null : depthMap);

                // Shifts
                Map<String, Object> shiftsCfg = (Map<String, Object>) config.get("shifts");
                int numShifts = ((Number) shiftsCfg.get("num_shifts")).intValue();
                List<Shift> shifts = ExampleProblemFactory.generateShifts(
                                (String) shiftsCfg.get("start_date"), numShifts);

                // Yard zones
                List<YardQuayZone> yardZones = new ArrayList<>();
                List<Map<String, Object>> yzConfigs = (List<Map<String, Object>>) config.getOrDefault("yard_quay_zones",
                                List.of());
                for (Map<String, Object> zc : yzConfigs) {
                        yardZones.add(new YardQuayZone(
                                        ((Number) zc.get("id")).intValue(),
                                        (String) zc.get("name"),
                                        ((Number) zc.get("start_dist")).intValue(),
                                        ((Number) zc.get("end_dist")).intValue()));
                }

                // Vessels
                List<Vessel> vessels = new ArrayList<>();
                List<Map<String, Object>> vesselConfigs = (List<Map<String, Object>>) config.get("vessels");
                for (Map<String, Object> vc : vesselConfigs) {
                        List<YardQuayZonePreference> targetZones = new ArrayList<>();
                        List<Map<String, Object>> tzConfigs = (List<Map<String, Object>>) vc
                                        .getOrDefault("target_zones", List.of());
                        for (Map<String, Object> tzc : tzConfigs) {
                                targetZones.add(new YardQuayZonePreference(
                                                ((Number) tzc.get("yard_quay_zone_id")).intValue(),
                                                ((Number) tzc.get("volume")).doubleValue()));
                        }

                        int arrShift = ((Number) vc.get("arrival_shift")).intValue();
                        int arrHourOffset = vc.containsKey("arrival_hour_offset")
                                        ? ((Number) vc.get("arrival_hour_offset")).intValue()
                                        : 0;

                        LocalDateTime arrivalTime;
                        if (arrShift >= shifts.size()) {
                                arrivalTime = shifts.get(shifts.size() - 1).getEndTime()
                                                .plusHours(6L * (arrShift - shifts.size() + 1));
                        } else {
                                arrivalTime = shifts.get(arrShift).getStartTime().plusHours(arrHourOffset);
                        }

                        Vessel v = new Vessel(
                                        (String) vc.get("name"),
                                        ((Number) vc.get("workload")).intValue(),
                                        ((Number) vc.get("loa")).intValue(),
                                        ((Number) vc.get("draft")).doubleValue(),
                                        arrivalTime, null,
                                        ((Number) vc.get("max_cranes")).intValue(),
                                        ProductivityMode.valueOf((String) vc.get("productivity_preference")),
                                        targetZones);
                        vessels.add(v);
                }

                ExampleProblemFactory.preprocessVessels(vessels, shifts, numShifts);

                // Cranes
                List<Crane> cranes = new ArrayList<>();
                List<Map<String, Object>> craneConfigs = (List<Map<String, Object>>) config.get("cranes");
                for (Map<String, Object> cc : craneConfigs) {
                        cranes.add(new Crane(
                                        (String) cc.get("id"),
                                        (String) cc.get("name"),
                                        CraneType.valueOf((String) cc.get("crane_type")),
                                        ((Number) cc.get("berth_range_start")).intValue(),
                                        ((Number) cc.get("berth_range_end")).intValue(),
                                        ((Number) cc.get("min_productivity")).intValue(),
                                        ((Number) cc.get("max_productivity")).intValue()));
                }

                // Crane availability
                List<String> allCraneIds = cranes.stream().map(Crane::getId).collect(Collectors.toList());
                Map<Integer, Set<String>> unavailMap = new HashMap<>();
                List<Map<String, Object>> unavailConfigs = (List<Map<String, Object>>) config
                                .getOrDefault("crane_unavailability", List.of());
                for (Map<String, Object> entry : unavailConfigs) {
                        String craneId = (String) entry.get("crane_id");
                        List<Number> unavailShifts = (List<Number>) entry.getOrDefault("shifts", List.of());
                        for (Number s : unavailShifts) {
                                unavailMap.computeIfAbsent(s.intValue(), k -> new HashSet<>()).add(craneId);
                        }
                }

                Map<Integer, List<String>> availability = new HashMap<>();
                for (int t = 0; t < numShifts; t++) {
                        Set<String> unavail = unavailMap.getOrDefault(t, Set.of());
                        availability.put(t, allCraneIds.stream()
                                        .filter(cid -> !unavail.contains(cid))
                                        .collect(Collectors.toList()));
                }

                // Forbidden zones
                List<ForbiddenZone> forbiddenZones = new ArrayList<>();
                List<Map<String, Object>> fzConfigs = (List<Map<String, Object>>) config.getOrDefault("forbidden_zones",
                                List.of());
                for (Map<String, Object> zc : fzConfigs) {
                        forbiddenZones.add(new ForbiddenZone(
                                        ((Number) zc.get("start_berth_position")).intValue(),
                                        ((Number) zc.get("end_berth_position")).intValue(),
                                        ((Number) zc.get("start_shift")).intValue(),
                                        ((Number) zc.get("end_shift")).intValue(),
                                        (String) zc.getOrDefault("description", "Maintenance")));
                }

                // Solver rules
                Map<String, Boolean> solverRules = new HashMap<>();
                Map<String, Object> rulesConfig = (Map<String, Object>) config.getOrDefault("solver_rules", Map.of());
                for (Map.Entry<String, Object> e : rulesConfig.entrySet()) {
                        if (e.getValue() instanceof Boolean) {
                                solverRules.put(e.getKey(), (Boolean) e.getValue());
                        }
                }

                return new Problem(berth, vessels, cranes, shifts, availability,
                                forbiddenZones, yardZones, solverRules);
        }

        @SuppressWarnings("unchecked")
        private Map<String, Object> loadConfig() {
                Map<String, Object> config = getDefaultConfig();
                Path path = Path.of(configFile);
                if (Files.exists(path)) {
                        try {
                                Map<String, Object> userConfig = mapper.readValue(path.toFile(),
                                                new TypeReference<Map<String, Object>>() {
                                                });
                                config.putAll(userConfig);
                        } catch (Exception e) {
                                System.err.println("Error loading config: " + e.getMessage());
                        }
                }
                return config;
        }

        private void saveConfig(Map<String, Object> config) {
                try {
                        mapper.writerWithDefaultPrettyPrinter().writeValue(new File(configFile), config);
                } catch (Exception e) {
                        System.err.println("Error saving config: " + e.getMessage());
                }
        }

        /**
         * Default configuration matching main.py's example problem.
         */
        @SuppressWarnings("unchecked")
        private Map<String, Object> getDefaultConfig() {
                // This mirrors get_default_config() from app.py exactly
                Map<String, Object> config = new LinkedHashMap<>();

                config.put("berth", Map.of(
                                "length", 2000,
                                "depth_map", List.of(
                                                Map.of("position", 0, "depth", 16.0),
                                                Map.of("position", 1200, "depth", 12.0))));

                config.put("shifts", Map.of("start_date", "31122025", "num_shifts", 12));

                config.put("vessels", List.of(
                                Map.of("name", "V1-MSC", "workload", 800, "loa", 300, "draft", 14.0,
                                                "arrival_shift", 0, "arrival_hour_offset", 0, "max_cranes", 4,
                                                "productivity_preference", "MAX",
                                                "target_zones", List.of(
                                                                Map.of("yard_quay_zone_id", 2, "volume", 600),
                                                                Map.of("yard_quay_zone_id", 1, "volume", 200))),
                                Map.of("name", "V2-MAERSK", "workload", 600, "loa", 250, "draft", 13.0,
                                                "arrival_shift", 0, "arrival_hour_offset", 2, "max_cranes", 3,
                                                "productivity_preference", "INTERMEDIATE",
                                                "target_zones", List.of(
                                                                Map.of("yard_quay_zone_id", 1, "volume", 500),
                                                                Map.of("yard_quay_zone_id", 2, "volume", 100))),
                                Map.of("name", "V3-COSCO", "workload", 500, "loa", 280, "draft", 14.5,
                                                "arrival_shift", 0, "arrival_hour_offset", 0, "max_cranes", 3,
                                                "productivity_preference", "MIN",
                                                "target_zones", List.of(Map.of("yard_quay_zone_id", 3, "volume", 500))),
                                Map.of("name", "V4-CMA", "workload", 400, "loa", 200, "draft", 12.0,
                                                "arrival_shift", 1, "arrival_hour_offset", 0, "max_cranes", 3,
                                                "productivity_preference", "INTERMEDIATE",
                                                "target_zones", List.of(Map.of("yard_quay_zone_id", 4, "volume", 400))),
                                Map.of("name", "V5-HAPAG", "workload", 350, "loa", 180, "draft", 11.0,
                                                "arrival_shift", 1, "arrival_hour_offset", 0, "max_cranes", 2,
                                                "productivity_preference", "MAX",
                                                "target_zones", List.of(Map.of("yard_quay_zone_id", 2, "volume", 350))),
                                Map.of("name", "V6-ONE", "workload", 700, "loa", 290, "draft", 13.5,
                                                "arrival_shift", 2, "arrival_hour_offset", 0, "max_cranes", 3,
                                                "productivity_preference", "INTERMEDIATE"),
                                Map.of("name", "V7-EVERGREEN", "workload", 900, "loa", 330, "draft", 15.0,
                                                "arrival_shift", 2, "arrival_hour_offset", 0, "max_cranes", 4,
                                                "productivity_preference", "MAX",
                                                "target_zones", List.of(Map.of("yard_quay_zone_id", 3, "volume", 900))),
                                Map.of("name", "V8-HMM", "workload", 450, "loa", 220, "draft", 12.5,
                                                "arrival_shift", 3, "arrival_hour_offset", 0, "max_cranes", 3,
                                                "productivity_preference", "INTERMEDIATE"),
                                Map.of("name", "V9-YANGMING", "workload", 550, "loa", 260, "draft", 13.8,
                                                "arrival_shift", 3, "arrival_hour_offset", 0, "max_cranes", 3,
                                                "productivity_preference", "MIN"),
                                Map.of("name", "V10-ZIM", "workload", 400, "loa", 210, "draft", 11.5,
                                                "arrival_shift", 4, "arrival_hour_offset", 0, "max_cranes", 2,
                                                "productivity_preference", "INTERMEDIATE"),
                                Map.of("name", "V11-WANHAI", "workload", 300, "loa", 190, "draft", 10.5,
                                                "arrival_shift", 4, "arrival_hour_offset", 0, "max_cranes", 2,
                                                "productivity_preference", "INTERMEDIATE"),
                                Map.of("name", "V12-PIL", "workload", 600, "loa", 270, "draft", 13.2,
                                                "arrival_shift", 5, "arrival_hour_offset", 0, "max_cranes", 3,
                                                "productivity_preference", "INTERMEDIATE")));

                config.put("cranes", List.of(
                                Map.of("id", "STS-01", "name", "STS Crane 1", "crane_type", "STS",
                                                "berth_range_start", 0, "berth_range_end", 1400,
                                                "min_productivity", 100, "max_productivity", 130),
                                Map.of("id", "STS-02", "name", "STS Crane 2", "crane_type", "STS",
                                                "berth_range_start", 0, "berth_range_end", 1400,
                                                "min_productivity", 100, "max_productivity", 130),
                                Map.of("id", "STS-03", "name", "STS Crane 3", "crane_type", "STS",
                                                "berth_range_start", 0, "berth_range_end", 1400,
                                                "min_productivity", 100, "max_productivity", 130),
                                Map.of("id", "STS-04", "name", "STS Crane 4", "crane_type", "STS",
                                                "berth_range_start", 0, "berth_range_end", 1400,
                                                "min_productivity", 100, "max_productivity", 130),
                                Map.of("id", "STS-05", "name", "STS Crane 5", "crane_type", "STS",
                                                "berth_range_start", 0, "berth_range_end", 1400,
                                                "min_productivity", 100, "max_productivity", 130),
                                Map.of("id", "STS-06", "name", "STS Crane 6", "crane_type", "STS",
                                                "berth_range_start", 0, "berth_range_end", 1400,
                                                "min_productivity", 100, "max_productivity", 130),
                                Map.of("id", "MHC-01", "name", "MHC Crane 1", "crane_type", "MHC",
                                                "berth_range_start", 1000, "berth_range_end", 2000,
                                                "min_productivity", 60, "max_productivity", 90),
                                Map.of("id", "MHC-02", "name", "MHC Crane 2", "crane_type", "MHC",
                                                "berth_range_start", 1000, "berth_range_end", 2000,
                                                "min_productivity", 60, "max_productivity", 90),
                                Map.of("id", "MHC-03", "name", "MHC Crane 3", "crane_type", "MHC",
                                                "berth_range_start", 1000, "berth_range_end", 2000,
                                                "min_productivity", 60, "max_productivity", 90),
                                Map.of("id", "MHC-04", "name", "MHC Crane 4", "crane_type", "MHC",
                                                "berth_range_start", 1000, "berth_range_end", 2000,
                                                "min_productivity", 60, "max_productivity", 90)));

                config.put("crane_unavailability", List.of(
                                Map.of("crane_id", "STS-01", "shifts", List.of(0, 1))));

                config.put("forbidden_zones", List.of(
                                Map.of("start_berth_position", 400, "end_berth_position", 600,
                                                "start_shift", 2, "end_shift", 4, "description",
                                                "Quay Wall Maintenance A"),
                                Map.of("start_berth_position", 1500, "end_berth_position", 1600,
                                                "start_shift", 6, "end_shift", 8, "description",
                                                "Dredging Operations B")));

                config.put("yard_quay_zones", List.of(
                                Map.of("id", 1, "name", "Zone A", "start_dist", 0, "end_dist", 500),
                                Map.of("id", 2, "name", "Zone B", "start_dist", 500, "end_dist", 1000),
                                Map.of("id", 3, "name", "Zone C", "start_dist", 1000, "end_dist", 1500),
                                Map.of("id", 4, "name", "Zone D", "start_dist", 1500, "end_dist", 2000)));

                config.put("solver_settings", Map.of("time_limit_seconds", 60));

                config.put("solver_rules", Map.of(
                                "enable_forbidden_zones", true,
                                "enable_crane_capacity", true,
                                "enable_max_cranes", true,
                                "enable_crane_reach", true,
                                "enable_sts_non_crossing", true,
                                "enable_shifting_gang", true,
                                "enable_min_cranes_on_arrival", true,
                                "enable_yard_preferences", true));

                return config;
        }
}
