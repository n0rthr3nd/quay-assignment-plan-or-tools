"""Flask web application for the BAP + QCAP Port Terminal Optimization Solver."""

import os
import json
import threading
import io
import sys
import datetime as dt

import matplotlib
matplotlib.use('Agg')

from flask import Flask, render_template, request, jsonify, send_from_directory

from models import (Berth, Problem, Vessel, ForbiddenZone, Crane,
                    CraneType, ProductivityMode, Shift)
from solver import solve
from visualization import (plot_solution, print_solution,
                           plot_crane_schedule, plot_vessel_execution_gantt)
from main import generate_shifts

app = Flask(__name__)

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
CONFIG_FILE = os.path.join(os.path.dirname(OUTPUT_DIR), "problem_config.json") if os.environ.get("OUTPUT_DIR") else "problem_config.json"

# Global solver state
solver_state = {
    "running": False,
    "status": "idle",
    "message": "",
    "solution_text": "",
}


def get_default_config():
    """Generate default config matching the example problem in main.py."""
    return {
        "berth": {
            "length": 2000,
            "depth_map": [
                {"position": 0, "depth": 16.0},
                {"position": 1200, "depth": 12.0}
            ]
        },
        "shifts": {
            "start_date": "31122025",
            "num_shifts": 12
        },
        "vessels": [
            {"name": "V1-MSC", "workload": 800, "loa": 300, "draft": 14.0,
             "arrival_shift": 0, "arrival_hour_offset": 0,
             "max_cranes": 4, "productivity_preference": "MAX"},
            {"name": "V2-MAERSK", "workload": 600, "loa": 250, "draft": 13.0,
             "arrival_shift": 0, "arrival_hour_offset": 2,
             "max_cranes": 3, "productivity_preference": "INTERMEDIATE"},
            {"name": "V3-COSCO", "workload": 500, "loa": 280, "draft": 14.5,
             "arrival_shift": 0, "arrival_hour_offset": 0,
             "max_cranes": 3, "productivity_preference": "MIN"},
            {"name": "V4-CMA", "workload": 400, "loa": 200, "draft": 12.0,
             "arrival_shift": 1, "arrival_hour_offset": 0,
             "max_cranes": 3, "productivity_preference": "INTERMEDIATE"},
            {"name": "V5-HAPAG", "workload": 350, "loa": 180, "draft": 11.0,
             "arrival_shift": 1, "arrival_hour_offset": 0,
             "max_cranes": 2, "productivity_preference": "MAX"},
            {"name": "V6-ONE", "workload": 700, "loa": 290, "draft": 13.5,
             "arrival_shift": 2, "arrival_hour_offset": 0,
             "max_cranes": 3, "productivity_preference": "INTERMEDIATE"},
            {"name": "V7-EVERGREEN", "workload": 900, "loa": 330, "draft": 15.0,
             "arrival_shift": 2, "arrival_hour_offset": 0,
             "max_cranes": 4, "productivity_preference": "MAX"},
            {"name": "V8-HMM", "workload": 450, "loa": 220, "draft": 12.5,
             "arrival_shift": 3, "arrival_hour_offset": 0,
             "max_cranes": 3, "productivity_preference": "INTERMEDIATE"},
            {"name": "V9-YANGMING", "workload": 550, "loa": 260, "draft": 13.8,
             "arrival_shift": 3, "arrival_hour_offset": 0,
             "max_cranes": 3, "productivity_preference": "MIN"},
            {"name": "V10-ZIM", "workload": 400, "loa": 210, "draft": 11.5,
             "arrival_shift": 4, "arrival_hour_offset": 0,
             "max_cranes": 2, "productivity_preference": "INTERMEDIATE"},
            {"name": "V11-WANHAI", "workload": 300, "loa": 190, "draft": 10.5,
             "arrival_shift": 4, "arrival_hour_offset": 0,
             "max_cranes": 2, "productivity_preference": "INTERMEDIATE"},
            {"name": "V12-PIL", "workload": 600, "loa": 270, "draft": 13.2,
             "arrival_shift": 5, "arrival_hour_offset": 0,
             "max_cranes": 3, "productivity_preference": "INTERMEDIATE"},
        ],
        "cranes": [
            {"id": "STS-01", "name": "STS Crane 1", "crane_type": "STS",
             "berth_range_start": 0, "berth_range_end": 1400,
             "min_productivity": 100, "max_productivity": 130},
            {"id": "STS-02", "name": "STS Crane 2", "crane_type": "STS",
             "berth_range_start": 0, "berth_range_end": 1400,
             "min_productivity": 100, "max_productivity": 130},
            {"id": "STS-03", "name": "STS Crane 3", "crane_type": "STS",
             "berth_range_start": 0, "berth_range_end": 1400,
             "min_productivity": 100, "max_productivity": 130},
            {"id": "STS-04", "name": "STS Crane 4", "crane_type": "STS",
             "berth_range_start": 0, "berth_range_end": 1400,
             "min_productivity": 100, "max_productivity": 130},
            {"id": "STS-05", "name": "STS Crane 5", "crane_type": "STS",
             "berth_range_start": 0, "berth_range_end": 1400,
             "min_productivity": 100, "max_productivity": 130},
            {"id": "STS-06", "name": "STS Crane 6", "crane_type": "STS",
             "berth_range_start": 0, "berth_range_end": 1400,
             "min_productivity": 100, "max_productivity": 130},
            {"id": "MHC-01", "name": "MHC Crane 1", "crane_type": "MHC",
             "berth_range_start": 1000, "berth_range_end": 2000,
             "min_productivity": 60, "max_productivity": 90},
            {"id": "MHC-02", "name": "MHC Crane 2", "crane_type": "MHC",
             "berth_range_start": 1000, "berth_range_end": 2000,
             "min_productivity": 60, "max_productivity": 90},
            {"id": "MHC-03", "name": "MHC Crane 3", "crane_type": "MHC",
             "berth_range_start": 1000, "berth_range_end": 2000,
             "min_productivity": 60, "max_productivity": 90},
            {"id": "MHC-04", "name": "MHC Crane 4", "crane_type": "MHC",
             "berth_range_start": 1000, "berth_range_end": 2000,
             "min_productivity": 60, "max_productivity": 90},
        ],
        "crane_unavailability": [
            {"crane_id": "STS-01", "shifts": [0, 1]}
        ],
        "forbidden_zones": [
            {"start_berth_position": 400, "end_berth_position": 600,
             "start_shift": 2, "end_shift": 4,
             "description": "Quay Wall Maintenance A"},
            {"start_berth_position": 1500, "end_berth_position": 1600,
             "start_shift": 6, "end_shift": 8,
             "description": "Dredging Operations B"}
        ],
        "solver_settings": {
            "time_limit_seconds": 60
        }
    }


def load_config():
    """Load config from file, or return default."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return get_default_config()


def save_config(config):
    """Save config to file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def config_to_problem(config):
    """Convert JSON config to a Problem object."""
    # Berth
    berth_cfg = config["berth"]
    depth_map = {}
    for entry in berth_cfg.get("depth_map", []):
        depth_map[int(entry["position"])] = float(entry["depth"])
    berth = Berth(length=int(berth_cfg["length"]), depth_map=depth_map if depth_map else None)

    # Shifts
    shifts_cfg = config["shifts"]
    num_shifts = int(shifts_cfg["num_shifts"])
    shifts = generate_shifts(shifts_cfg["start_date"], num_shifts)

    # Helper to compute datetime from shift index + hour offset
    def get_dt(shift_idx, hour_offset=0):
        if shift_idx >= len(shifts):
            return shifts[-1].end_time + dt.timedelta(hours=6 * (shift_idx - len(shifts) + 1))
        s = shifts[shift_idx]
        return s.start_time + dt.timedelta(hours=hour_offset)

    # Vessels
    vessels = []
    for vc in config["vessels"]:
        v = Vessel(
            name=vc["name"],
            workload=int(vc["workload"]),
            loa=int(vc["loa"]),
            draft=float(vc["draft"]),
            arrival_time=get_dt(int(vc["arrival_shift"]), int(vc.get("arrival_hour_offset", 0))),
            max_cranes=int(vc["max_cranes"]),
            productivity_preference=ProductivityMode(vc["productivity_preference"]),
        )
        vessels.append(v)

    # Pre-process vessels (same logic as main.py)
    for v in vessels:
        v.arrival_shift_index = -1
        v.arrival_fraction = 1.0

        for t, s in enumerate(shifts):
            if s.start_time <= v.arrival_time < s.end_time:
                v.arrival_shift_index = t
                total_dur = (s.end_time - s.start_time).total_seconds()
                avail_dur = (s.end_time - v.arrival_time).total_seconds()
                v.arrival_fraction = avail_dur / total_dur if total_dur > 0 else 0
                break

        if v.arrival_time < shifts[0].start_time:
            v.arrival_shift_index = 0
            v.arrival_fraction = 1.0

        if v.arrival_shift_index == -1 and v.arrival_time >= shifts[-1].end_time:
            v.arrival_shift_index = num_shifts

        v.departure_shift_index = num_shifts
        if v.departure_deadline:
            for t, s in enumerate(shifts):
                if s.start_time <= v.departure_deadline <= s.end_time:
                    v.departure_shift_index = t
                    break

        start_idx = v.arrival_shift_index
        if start_idx < num_shifts:
            v.available_shifts = list(range(start_idx, num_shifts))
        else:
            v.available_shifts = []

    # Cranes
    cranes = []
    for cc in config["cranes"]:
        cranes.append(Crane(
            id=cc["id"],
            name=cc["name"],
            crane_type=CraneType(cc["crane_type"]),
            berth_range_start=int(cc["berth_range_start"]),
            berth_range_end=int(cc["berth_range_end"]),
            min_productivity=int(cc["min_productivity"]),
            max_productivity=int(cc["max_productivity"]),
        ))

    # Crane availability
    all_crane_ids = [c.id for c in cranes]
    unavail_map = {}
    for entry in config.get("crane_unavailability", []):
        crane_id = entry["crane_id"]
        for s in entry.get("shifts", []):
            unavail_map.setdefault(int(s), set()).add(crane_id)

    availability = {}
    for t in range(num_shifts):
        unavail = unavail_map.get(t, set())
        availability[t] = [cid for cid in all_crane_ids if cid not in unavail]

    # Forbidden zones
    forbidden_zones = []
    for zc in config.get("forbidden_zones", []):
        forbidden_zones.append(ForbiddenZone(
            start_berth_position=int(zc["start_berth_position"]),
            end_berth_position=int(zc["end_berth_position"]),
            start_shift=int(zc["start_shift"]),
            end_shift=int(zc["end_shift"]),
            description=zc.get("description", "Maintenance"),
        ))

    return Problem(
        berth=berth,
        vessels=vessels,
        cranes=cranes,
        shifts=shifts,
        crane_availability_per_shift=availability,
        forbidden_zones=forbidden_zones,
    )


def run_solver_thread(config):
    """Run the solver in a background thread."""
    global solver_state
    solver_state["running"] = True
    solver_state["status"] = "running"
    solver_state["message"] = "Building model and solving..."
    solver_state["solution_text"] = ""

    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        problem = config_to_problem(config)
        time_limit = int(config.get("solver_settings", {}).get("time_limit_seconds", 60))

        solution = solve(problem, time_limit_seconds=time_limit)

        # Capture print_solution output
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()
        print_solution(problem, solution)
        sys.stdout = old_stdout
        solver_state["solution_text"] = buffer.getvalue()

        # Generate plots
        plot_solution(problem, solution, os.path.join(OUTPUT_DIR, "gantt_forbidden_cranes.png"))
        plot_crane_schedule(problem, solution, os.path.join(OUTPUT_DIR, "cranes_schedule.png"))
        plot_vessel_execution_gantt(problem, solution, os.path.join(OUTPUT_DIR, "vessel_execution_summary.png"))

        solver_state["status"] = "completed"
        solver_state["message"] = f"Solver finished: {solution.status} (Objective: {solution.objective_value:.0f})"

    except Exception as e:
        solver_state["status"] = "error"
        solver_state["message"] = f"Error: {str(e)}"
        import traceback
        solver_state["solution_text"] = traceback.format_exc()
    finally:
        solver_state["running"] = False


# ─── Routes ──────────────────────────────────────────────────────────

@app.route("/")
def editor():
    return render_template("editor.html")


@app.route("/results")
def results():
    return render_template("results.html")


@app.route("/api/problem", methods=["GET"])
def get_problem():
    config = load_config()
    return jsonify(config)


@app.route("/api/problem", methods=["POST"])
def save_problem():
    config = request.get_json()
    save_config(config)
    return jsonify({"ok": True})


@app.route("/api/solve", methods=["POST"])
def start_solve():
    if solver_state["running"]:
        return jsonify({"ok": False, "message": "Solver already running"}), 409

    config = load_config()
    thread = threading.Thread(target=run_solver_thread, args=(config,), daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": "Solver started"})


@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify(solver_state)


@app.route("/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(OUTPUT_DIR, filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
