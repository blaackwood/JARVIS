"""background_tasks — hand long work to an agent while the conversation goes on.

The tool is thin on purpose: everything that makes a task survive a restart,
respect a budget, wait out a quota or stay away from the user's computer lives
in core/tasks. This file turns what the model asked for into a call on the
engine and turns the answer back into facts (core/outcome.py) for the model to
say in the user's language.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta


def _when(at: str) -> float:
    """'YYYY-MM-DD HH:MM', or 'HH:MM' meaning the next time the clock reads it."""
    text = str(at or "").strip()
    now = datetime.now()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            pass
    try:
        hm = datetime.strptime(text, "%H:%M")
    except ValueError:
        raise ValueError("'at' must be 'YYYY-MM-DD HH:MM' or 'HH:MM'") from None
    when = now.replace(hour=hm.hour, minute=hm.minute, second=0, microsecond=0)
    if when <= now:
        when += timedelta(days=1)
    return when.timestamp()


def _minutes(task: dict) -> str:
    return f"{task['used']['seconds'] / 60:.1f}/{task['budget']['minutes']} min"


def _row(t: dict) -> str:
    return f"{t['id']} [{t['status']}] {t['agent']} · {t['title']} · {_minutes(t)}"


def background_tasks(parameters: dict, player=None) -> str:
    from core import outcome
    from core.tasks import ACTIVE
    from core.tasks import desktop

    eng = desktop.ensure(player)
    a = dict(parameters or {})
    action = str(a.get("action") or "list").strip().lower()

    if action == "start":
        task = str(a.get("task") or "").strip()
        if not task:
            return outcome.failed("background_tasks", "start needs the whole task, in the user's words")
        not_before = 0.0
        if a.get("at"):
            try:
                not_before = _when(a["at"])
            except ValueError as e:
                return outcome.failed("background_tasks", str(e))
        files = [a["file_path"]] if a.get("file_path") else None
        try:
            t = eng.start(task, agent=a.get("agent") or "general", minutes=a.get("minutes"),
                          deliver=a.get("deliver") or "voice", not_before=not_before, files=files)
        except ValueError as e:
            return outcome.failed("background_tasks", str(e))
        starts = time.strftime("%Y-%m-%d %H:%M", time.localtime(not_before)) if not_before else "now"
        return outcome.started("background_tasks", task_id=t["id"], agent=t["agent"],
                               minutes=t["budget"]["minutes"], starts=starts,
                               note="the result is announced when it is done; the conversation "
                                    "carries on meanwhile")

    if action == "agents":
        return "\n".join(f"{p.name}: {p.description} (default {p.minutes} min)"
                         for p in eng.agents(reload=True).values())

    if action == "routine_add":
        from core import authorization, confirm
        action_class, decision = authorization.authorize("background_tasks", a)
        if decision == "deny":
            return outcome.failed("background_tasks", "policy denied recurring automation")
        try:
            def _create_routine():
                routine = eng.add_routine(
                    task=str(a.get("task") or ""),
                    frequency=str(a.get("frequency") or ""),
                    at=str(a.get("at") or ""),
                    agent=str(a.get("agent") or "general"),
                    minutes=int(a.get("minutes") or 10),
                    weekday=a.get("weekday"),
                )
                authorization.record("routine_created", action_class, "allow",
                                      "automatic_policy", routine["id"])
                return (f"Routine created: {routine['id']} at {routine['at']}; "
                        f"next run {time.strftime('%Y-%m-%d %H:%M', time.localtime(routine['next_run']))}.")
            if decision == "confirm":
                if confirm.pending_title():
                    return outcome.ask("background_tasks", "another confirmation is already pending")
                return confirm.request(
                    key="routine_add", title="Create recurring Jarvis routine",
                    detail=(f"Task: {str(a.get('task') or '')[:180]} | "
                            f"Frequency: {a.get('frequency')} | Local time: {a.get('at')}. "
                            "This will keep running automatically while Jarvis is open."),
                    run=_create_routine,
                )
            return outcome.done("background_tasks", result=_create_routine())
        except (TypeError, ValueError) as e:
            return outcome.failed("background_tasks", str(e))

    if action == "routine_list":
        routines = eng.list_routines()
        if not routines:
            return "No recurring routines configured."
        return "\n".join(
            f"{r['id']} [{r['frequency']}] {r['at']} · {r['task']} · next "
            f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(r['next_run']))}"
            for r in routines if r.get("enabled")
        ) or "No enabled recurring routines."

    if action == "routine_remove":
        from core import authorization, confirm
        routine_id = str(a.get("routine_id") or "").strip()
        if not routine_id:
            return outcome.failed("background_tasks", "routine_remove requires routine_id")
        action_class, decision = authorization.authorize("background_tasks", a)
        if decision == "deny":
            return outcome.failed("background_tasks", "policy denied recurring automation changes")
        def _remove_routine():
            removed = eng.remove_routine(routine_id)
            if removed:
                authorization.record("routine_removed", action_class, "allow",
                                     "automatic_policy", routine_id)
                return f"Routine {routine_id} removed."
            return f"No recurring routine with ID {routine_id}."
        if decision == "confirm":
            if confirm.pending_title():
                return outcome.ask("background_tasks", "another confirmation is already pending")
            return confirm.request(
                key="routine_remove", title="Remove recurring Jarvis routine",
                detail=f"Remove routine ID {routine_id}? It will no longer run automatically.",
                run=_remove_routine,
            )
        return outcome.done("background_tasks", result=_remove_routine())

    if action == "list":
        rows = [_row(t) for t in eng.list(10)]
        return "\n".join(rows) if rows else "No background tasks yet."

    tid = str(a.get("task_id") or "").strip()
    tasks = eng.list(50)
    if tid:
        task = eng.get(tid)
    else:
        # No id: the task this most plausibly means — the latest still running,
        # or for a result, the latest at all.
        if action == "result":
            pool = tasks
        elif action == "resume":
            pool = [t for t in tasks if t["status"] in ("paused", "pausing")]
        elif action == "status":
            pool = tasks
        else:
            pool = [t for t in tasks if t["status"] in ACTIVE or
                    (action in ("pause", "cancel", "finish", "steer") and t["status"] == "paused")]
        task = pool[0] if pool else None
    if task is None:
        return outcome.failed("background_tasks", "no such task" if tid else "there is no task to act on")

    if action == "status":
        # Re-read immediately before answering; the initial selection may have
        # happened just before a worker committed its pause/resume checkpoint.
        task = eng.get(task["id"]) or task
        recent = [e["text"] for e in task.get("events") or [] if e["kind"] in ("progress", "tool", "state")][-6:]
        state_note = None
        if task["status"] == "pausing" and task.get("resume_pending"):
            state_note = "resume is already queued and will start immediately after the current checkpoint is committed; do not ask the user to resume again"
        elif task["status"] == "pausing":
            state_note = "pause requested; the current round is still saving its checkpoint"
        elif task["status"] == "queued":
            state_note = "resumed and waiting for a worker slot"
        return outcome.done("background_tasks", task_id=task["id"], status=task["status"],
                            resume_pending=bool(task.get("resume_pending")),
                            state_note=state_note, agent=task["agent"], title=task["title"],
                            time=_minutes(task), rounds=f"{task['used']['rounds']}/{task['budget']['rounds']}",
                            recent=" | ".join(recent) or None, error=task.get("error") or None)
    if action == "result":
        if task["status"] != "done":
            return outcome.done("background_tasks", task_id=task["id"], status=task["status"],
                                note="not finished yet")
        return (outcome.done("background_tasks", task_id=task["id"], report=task.get("report") or None)
                + "\n" + outcome.untrusted("task-result", (task.get("result") or "")[:12_000]))
    if action == "pause":
        ok = eng.pause(task["id"])
        current_status = (eng.get(task["id"]) or {}).get("status")
        return (outcome.done("background_tasks", task_id=task["id"], status=current_status,
                             note=("the current round will finish and save its checkpoint"
                                   if current_status == "pausing" else "the task is paused"))
                if ok else outcome.failed("background_tasks", "that task cannot be paused"))
    if action == "resume":
        was_pausing = task.get("status") == "pausing"
        ok = eng.resume(task["id"])
        current = eng.get(task["id"]) or task
        return (outcome.done("background_tasks", task_id=task["id"], status=current["status"],
                             resume_pending=bool(current.get("resume_pending")),
                             resume_requested=was_pausing, resumed=not was_pausing,
                             note=("resume is queued; it will continue as soon as the current checkpoint is committed"
                                   if was_pausing else "task queued to resume"))
                if ok else outcome.failed("background_tasks", "that task is not paused or pausing"))
    if action == "finish":
        ok = eng.cancel(task["id"], finish=True)
        return (outcome.started("background_tasks", task_id=task["id"],
                                note="stopping and writing up what was found")
                if ok else outcome.failed("background_tasks", "that task is not running"))
    if action == "cancel":
        ok = eng.cancel(task["id"])
        return (outcome.done("background_tasks", task_id=task["id"], cancelled=True)
                if ok else outcome.failed("background_tasks", "that task is not running"))
    if action == "steer":
        ok = eng.steer(task["id"], a.get("note") or "")
        return (outcome.done("background_tasks", task_id=task["id"], note_added=True)
                if ok else outcome.failed("background_tasks", "needs a running task and a note"))
    return outcome.failed("background_tasks", f"unknown action '{action}'")


TOOL = {
    "name": "background_tasks",
    "description": (
        "Long work that runs in the background on this computer while the conversation carries on: "
        "real research, reading and comparing many sources, writing a report, working through a "
        "list. For a quick answer the user is waiting for, use web_search instead. "
        "start = hand the task to an agent — choose 'researcher' for web research with checked citations; "
        "'document_analyst' for attached PDFs, documents and spreadsheets; 'study_coach' for learning "
        "materials, questions and revision plans; 'quality_reviewer' for an independent audit of a supplied "
        "deliverable; or 'general' for other work. Specialist agents only receive their declared tools; "
        "background agents cannot control the desktop or send messages. task = the whole request, self-contained, "
        "in the user's words; "
        "minutes = the time budget when the user gives one ('research this for 10 minutes' -> 10); "
        "without one, 10 for research, more (20-40) when the user asks for something thorough or "
        "in depth; at = start later, "
        "'YYYY-MM-DD HH:MM' or 'HH:MM' local time ('tonight at 2' -> '02:00'); file_path = a file to "
        "work from. After start, say in one short sentence that it is under way — the result is "
        "announced by itself when done. "
        "list = the tasks and their state; status = how one is going; result = a finished task's "
        "result; pause = request a safe stop after the current round and keep its checkpoint. If "
        "the returned status is pausing, say the pause was requested, NOT completed; only say paused "
        "when status is paused. resume = continue a paused task from that checkpoint. A resume requested "
        "while status is pausing is persisted as resume_pending=true and automatically continues after the "
        "checkpoint; do NOT tell the user to wait until fully paused and issue resume again. status returns "
        "the latest persisted status and state_note; follow state_note exactly. If status=pausing and "
        "resume_pending=true, tell the user resume is already queued. If status=queued, the task has resumed "
        "and is waiting for a worker slot. Never describe a task as paused or pausing when returned status "
        "says queued or running. finish = stop now and write up what was found; "
        "cancel = stop without a result; routine_add = create a persistent daily or weekly task (task, frequency, at; weekly also needs weekday); "
        "routine_list = list routines; routine_remove = remove one by routine_id; steer = add an instruction to a task (note); agents = available agents. "
        "Weekly weekday is 0 Monday through 6 Sunday. " 
        "task_id may be left empty to mean the latest task."),
    "brief": "Background tasks and recurring daily/weekly routines: start, list, status, result, pause, resume, finish, cancel, steer, routine_add, routine_list, routine_remove.",
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "enum": ["start", "list", "status", "result", "pause", "resume",
                                "finish", "cancel", "steer", "agents", "routine_add", "routine_list", "routine_remove"]},
            "task": {"type": "STRING", "description": "for start: the whole task, self-contained"},
            "agent": {"type": "STRING", "description": "for start: researcher | document_analyst | study_coach | quality_reviewer | general"},
            "minutes": {"type": "INTEGER", "description": "for start: time budget in minutes"},
            "at": {"type": "STRING", "description": "for start: when to begin, local time"},
            "deliver": {"type": "STRING", "enum": ["voice", "panel", "silent"],
                        "description": "for start: how to announce the result (default voice)"},
            "file_path": {"type": "STRING", "description": "for start: a file to work from"},
            "task_id": {"type": "STRING"},
            "note": {"type": "STRING", "description": "for steer: the new instruction"},
            "frequency": {"type": "STRING", "enum": ["daily", "weekly"], "description": "for routine_add"},
            "weekday": {"type": "INTEGER", "description": "for weekly routine_add: 0 Monday through 6 Sunday"},
            "routine_id": {"type": "STRING", "description": "for routine_remove: exact ID from routine_list"},
        },
        "required": ["action"],
    },
    "handler": background_tasks,
}
