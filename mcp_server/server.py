"""
Athlete Concierge MCP Server
-----------------------------
Exposes tools over the Model Context Protocol (MCP) so that any
MCP-compatible agent (in our case, an ADK agent) can read a student-athlete's
training program, calculate today's working weights from their real 1RMs,
check upcoming academic deadlines, and log recovery/soreness data -- with
weights automatically backing off when recent soreness is high.

Run standalone for a quick sanity check:
    python mcp_server/server.py

The ADK agent launches this file itself over stdio (see athlete_concierge/agent.py),
so you normally don't need to run it manually.

SECURITY NOTE:
This server only reads/writes local JSON files in ./data. It does not accept
arbitrary file paths from the caller (paths are hardcoded), and it performs no
network calls or credential handling itself -- the Gemini API key used by the
*agent* lives in a separate .env file that this server never touches.
"""

import json
import os
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file so it works regardless of cwd)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
WORKOUT_FILE = os.path.join(DATA_DIR, "workout_program.json")
ASSIGNMENTS_FILE = os.path.join(DATA_DIR, "assignments.json")
RECOVERY_LOG_FILE = os.path.join(DATA_DIR, "recovery_log.json")
ONE_RM_FILE = os.path.join(DATA_DIR, "one_rep_maxes.json")

# If a muscle group was logged at this soreness level or higher within the
# lookback window, working weight gets backed off automatically.
SORENESS_AUTO_ADJUST_THRESHOLD = 4
SORENESS_LOOKBACK_DAYS = 2
SORENESS_WEIGHT_REDUCTION_PERCENT = 10  # how much lighter to go when sore

mcp = FastMCP("athlete-concierge")


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r") as f:
        return json.load(f)


def _save_json(path: str, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _round_to_nearest(weight: float, increment: float = 5) -> float:
    """Round a calculated weight to the nearest plate-friendly increment."""
    return round(weight / increment) * increment


def _recent_soreness_for(muscle_group: str) -> dict | None:
    """Return the most recent soreness log entry for a muscle group within
    the lookback window, if any, and if it meets the auto-adjust threshold."""
    log = _load_json(RECOVERY_LOG_FILE, [])
    cutoff = datetime.now() - timedelta(days=SORENESS_LOOKBACK_DAYS)
    matches = []
    for entry in log:
        if entry.get("muscle_group", "").lower() != muscle_group.lower():
            continue
        try:
            logged_at = datetime.fromisoformat(entry["logged_at"])
        except (KeyError, ValueError):
            continue
        if logged_at >= cutoff and entry.get("level", 0) >= SORENESS_AUTO_ADJUST_THRESHOLD:
            matches.append(entry)
    if not matches:
        return None
    return sorted(matches, key=lambda e: e["logged_at"], reverse=True)[0]


@mcp.tool()
def get_one_rep_maxes() -> dict:
    """Get the athlete's currently stored one-rep maxes for all tracked
    exercises.

    Returns:
        A dict mapping exercise name -> 1RM in pounds.
    """
    return {"status": "success", "one_rep_maxes": _load_json(ONE_RM_FILE, {})}


@mcp.tool()
def set_one_rep_max(exercise: str, weight_lb: float) -> dict:
    """Update the athlete's one-rep max for a specific exercise. Use this
    whenever the athlete reports a new tested or estimated 1RM.

    Args:
        exercise: Exercise name, e.g. "Back Squat". Should match an exercise
            name used in the training program for weights to calculate
            correctly.
        weight_lb: The new one-rep max, in pounds.

    Returns:
        Confirmation of the updated value.
    """
    one_rms = _load_json(ONE_RM_FILE, {})
    one_rms[exercise] = weight_lb
    _save_json(ONE_RM_FILE, one_rms)
    return {"status": "success", "exercise": exercise, "one_rep_max": weight_lb}


@mcp.tool()
def get_todays_workout(day: str, ignore_soreness_adjustment: bool = False) -> dict:
    """Get the prescribed workout for a given training day, with working
    weights calculated live from the athlete's stored 1RMs. Ask if the user wants to
    back off weight on any exercise whose primary muscle group was logged
    as sore (4 or 5 out of 5) in the last two days, unless told not to.

    Args:
        day: Which training day to look up, e.g. "Day 1" or "Day 2".
        ignore_soreness_adjustment: If True, skip the automatic soreness
            back-off and just return the plan at full prescribed percentages.

    Returns:
        A dict with the training phase, focus, and prescribed exercises,
        each with its calculated working weight and a note if it was
        adjusted for soreness.
    """
    program = _load_json(WORKOUT_FILE, {})
    one_rms = _load_json(ONE_RM_FILE, {})
    day_plan = program.get("days", {}).get(day)
    if day_plan is None:
        return {
            "status": "not_found",
            "message": f"No workout found for '{day}'. Available days: "
                       f"{list(program.get('days', {}).keys())}",
        }

    exercises_out = []
    for ex in day_plan.get("exercises", []):
        name = ex["name"]
        percent = ex["percent_1rm"]
        muscle_group = ex.get("primary_muscle_group", "")
        one_rm = one_rms.get(name)

        note = None
        effective_percent = percent
        if one_rm is None:
            exercises_out.append({
                "name": name,
                "sets": ex["sets"],
                "reps": ex["reps"],
                "percent_1rm": percent,
                "working_weight_lb": None,
                "note": f"No 1RM on file for '{name}'. Use set_one_rep_max to add one.",
            })
            continue

        if not ignore_soreness_adjustment:
            soreness = _recent_soreness_for(muscle_group)
            if soreness is not None:
                effective_percent = percent - SORENESS_WEIGHT_REDUCTION_PERCENT
                note = (
                    f"Reduced from {percent}% to {effective_percent}% because "
                    f"'{muscle_group}' was logged at soreness {soreness['level']}/5 "
                    f"on {soreness['logged_at'][:10]}."
                )

        working_weight = _round_to_nearest(one_rm * effective_percent / 100)
        exercises_out.append({
            "name": name,
            "sets": ex["sets"],
            "reps": ex["reps"],
            "percent_1rm": effective_percent,
            "working_weight_lb": working_weight,
            "note": note,
        })

    return {
        "status": "success",
        "phase": program.get("current_phase"),
        "week": program.get("week"),
        "day": day,
        "focus": day_plan.get("focus"),
        "exercises": exercises_out,
    }


@mcp.tool()
def adjust_todays_workout(day: str, percent_change: float) -> dict:
    """Recalculate a day's workout with an across-the-board weight
    adjustment, on top of any automatic soreness back-off. Use this when the
    athlete directly asks to go lighter (or heavier) by some amount, e.g.
    "decrease everything by 15%" or "bump it up 5%".

    Args:
        day: Which training day to recalculate, e.g. "Day 1".
        percent_change: Percentage points to shift each lift's %1RM by.
            Negative to decrease (e.g. -15 for 15% lighter), positive to
            increase.

    Returns:
        The recalculated workout with adjusted working weights.
    """
    program = _load_json(WORKOUT_FILE, {})
    one_rms = _load_json(ONE_RM_FILE, {})
    day_plan = program.get("days", {}).get(day)
    if day_plan is None:
        return {
            "status": "not_found",
            "message": f"No workout found for '{day}'. Available days: "
                       f"{list(program.get('days', {}).keys())}",
        }

    exercises_out = []
    for ex in day_plan.get("exercises", []):
        name = ex["name"]
        one_rm = one_rms.get(name)
        adjusted_percent = ex["percent_1rm"] + percent_change
        if one_rm is None:
            exercises_out.append({
                "name": name,
                "percent_1rm": adjusted_percent,
                "working_weight_lb": None,
                "note": f"No 1RM on file for '{name}'.",
            })
            continue
        working_weight = _round_to_nearest(one_rm * adjusted_percent / 100)
        exercises_out.append({
            "name": name,
            "percent_1rm": adjusted_percent,
            "working_weight_lb": working_weight,
        })

    return {
        "status": "success",
        "day": day,
        "percent_change_applied": percent_change,
        "exercises": exercises_out,
    }


@mcp.tool()
def get_upcoming_deadlines(days_ahead: int = 7) -> dict:
    """Get academic deadlines coming up within a given window.

    Args:
        days_ahead: How many days into the future to look (default 7).

    Returns:
        A dict with a list of upcoming assignments/exams, soonest first.
    """
    assignments = _load_json(ASSIGNMENTS_FILE, [])
    today = datetime.now().date()
    cutoff = today + timedelta(days=days_ahead)

    upcoming = []
    for a in assignments:
        try:
            due = datetime.strptime(a["due_date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if today <= due <= cutoff:
            upcoming.append({**a, "days_until_due": (due - today).days})

    upcoming.sort(key=lambda a: a["days_until_due"])
    return {"status": "success", "window_days": days_ahead, "deadlines": upcoming}


@mcp.tool()
def log_soreness(muscle_group: str, level: int) -> dict:
    """Log a soreness/recovery rating for a muscle group. Future calls to
    get_todays_workout will automatically back off weight for exercises
    targeting this muscle group if the level logged here is 4 or 5.

    Args:
        muscle_group: e.g. "legs", "back", "shoulders", "chest".
        level: Soreness rating from 1 (none) to 5 (very sore).

    Returns:
        Confirmation the entry was logged, with a timestamp.
    """
    level = max(1, min(5, int(level)))  # basic input validation/clamping
    log = _load_json(RECOVERY_LOG_FILE, [])
    entry = {
        "muscle_group": muscle_group,
        "level": level,
        "logged_at": datetime.now().isoformat(timespec="seconds"),
    }
    log.append(entry)
    _save_json(RECOVERY_LOG_FILE, log)
    return {"status": "success", "logged": entry}


if __name__ == "__main__":
    # Runs the server over stdio -- this is what the ADK agent connects to.
    mcp.run()
