"""
Stopping the bot: process-lock detection, whole-tree kills, the manual-Stop
pause, and the dashboard Start/Stop/watchdog wiring.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import textwrap
import time

import pytest

from utils import process_control as pc
from utils import process_lock as pl

ROOT = str(pl.ROOT)


def _spawn_lock_holder(lock_name: str, *, via_child: bool = False) -> subprocess.Popen:
    """Start a python process that holds `lock_name` (optionally from a grandchild)."""
    holder = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {ROOT!r})
        from utils.process_lock import acquire_process_lock
        assert acquire_process_lock({lock_name!r})
        time.sleep(60)
    """)
    if via_child:
        code = textwrap.dedent(f"""
            import subprocess, sys, time
            subprocess.Popen([sys.executable, "-c", {holder!r}])
            time.sleep(60)
        """)
    else:
        code = holder
    return subprocess.Popen([sys.executable, "-c", code])


def _wait_held(lock_name: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not pl.is_lock_held(lock_name):
        assert time.monotonic() < deadline, f"{lock_name} lock never acquired"
        time.sleep(0.1)


@pytest.fixture()
def lock_name(request):
    name = f"pytest_{request.node.name[:20]}"
    yield name
    pl.lock_path(name).unlink(missing_ok=True)


# ── process lock ─────────────────────────────────────────────────────────────

def test_lock_held_and_pid_readable_from_another_process(lock_name):
    proc = _spawn_lock_holder(lock_name)
    try:
        _wait_held(lock_name)
        # The PID stays readable while the lock is held (lock sits past the text).
        # With a venv python.exe the holder is the launcher's child, not proc.pid.
        holder = pl.lock_holder_pid(lock_name)
        assert holder is not None and holder != os.getpid()
    finally:
        pc.kill_tree(proc.pid)
        proc.wait(timeout=10)
    assert pc.wait_until_released(lock_name)
    assert pl.lock_holder_pid(lock_name) is None


def test_stale_lock_file_is_not_held(lock_name):
    pl.lock_path(lock_name).write_text("99999\n")
    assert not pl.is_lock_held(lock_name)
    assert pl.lock_holder_pid(lock_name) is None


# ── kill_tree ────────────────────────────────────────────────────────────────

def test_kill_tree_kills_grandchild_too(lock_name):
    """The venv python.exe runs the real interpreter as a child — kill both."""
    parent = _spawn_lock_holder(lock_name, via_child=True)
    try:
        _wait_held(lock_name)
        assert pl.lock_holder_pid(lock_name) != parent.pid   # held by the grandchild
        assert pc.kill_tree(parent.pid)
        assert pc.wait_until_released(lock_name, timeout=10)
    finally:
        pc.kill_tree(parent.pid)


def test_kill_tree_refuses_own_pid():

    assert pc.kill_tree(os.getpid()) is False


# ── pause flag ───────────────────────────────────────────────────────────────

@pytest.fixture()
def pause_file(tmp_path, monkeypatch):
    f = tmp_path / ".bot_paused"
    monkeypatch.setattr(pc, "PAUSE_FILE", f)
    return f


def test_pause_and_resume(pause_file):
    assert not pc.is_paused()
    pc.pause_bot("test")
    assert pc.is_paused() and pause_file.exists()
    pc.resume_bot()
    assert not pc.is_paused()
    pc.resume_bot()   # idempotent


def test_stop_all_pauses_and_reports(pause_file, monkeypatch):
    monkeypatch.setattr(pc, "lock_holder_pid", lambda name: None)
    monkeypatch.setattr(pc, "is_lock_held", lambda name: False)
    result = pc.stop_all()
    assert result == {"dashboard": "not running", "launcher": "not running", "bot": "not running"}
    assert pc.is_paused()


# ── dashboard wiring ─────────────────────────────────────────────────────────

@pytest.fixture()
def dash(pause_file, monkeypatch):
    ui_app = importlib.import_module("ui.app")
    monkeypatch.setattr(ui_app, "is_paused", pc.is_paused)
    monkeypatch.setattr(ui_app, "pause_bot", pc.pause_bot)
    monkeypatch.setattr(ui_app, "resume_bot", pc.resume_bot)
    ui_app.app.config["TESTING"] = True
    return ui_app, ui_app.app.test_client(), {"X-Dashboard-Token": ui_app.DASHBOARD_TOKEN}


def test_watchdog_not_started_under_pytest(dash):
    ui_app, _, _ = dash
    assert not hasattr(ui_app, "_wd")


def test_auto_start_skipped_while_paused(dash, monkeypatch):
    ui_app, _, _ = dash
    popen = []
    monkeypatch.setattr(ui_app.subprocess, "Popen", lambda *a, **k: popen.append(a))
    monkeypatch.setattr(ui_app, "_is_bot_running", lambda: False)
    pc.pause_bot()
    assert ui_app._start_bot_proc(auto=True) is False
    assert popen == []


def test_stop_endpoint_pauses_and_start_endpoint_resumes(dash, monkeypatch):
    ui_app, client, headers = dash
    running = {"v": True}
    monkeypatch.setattr(ui_app, "_is_bot_running", lambda: running["v"])

    def fake_stop():
        running["v"] = False
        return True
    monkeypatch.setattr(ui_app, "_stop_bot", fake_stop)

    r = client.post("/api/bot/stop", headers=headers)
    assert r.get_json() == {"ok": True, "paused": True, "still_running": False}
    assert pc.is_paused()

    started = []
    monkeypatch.setattr(ui_app, "_start_bot_proc", lambda auto=False: started.append(auto) or True)
    monkeypatch.setattr(ui_app, "_read_pid", lambda: 1234)
    r = client.post("/api/bot/start", headers=headers)
    assert r.get_json()["ok"] is True
    assert not pc.is_paused()
    assert started == [False]   # explicit start, not an auto-start


def test_stop_endpoint_pauses_even_when_not_running(dash, monkeypatch):
    ui_app, client, headers = dash
    monkeypatch.setattr(ui_app, "_is_bot_running", lambda: False)
    r = client.post("/api/bot/stop", headers=headers)
    assert r.status_code == 400
    assert pc.is_paused()


def test_stop_bot_kills_whole_tree(dash, monkeypatch):
    ui_app, _, _ = dash
    killed = []
    monkeypatch.setattr(ui_app, "kill_tree", lambda pid: killed.append(pid) or True)
    monkeypatch.setattr(ui_app, "stop_bot_processes", lambda: False)
    monkeypatch.setattr(ui_app, "wait_until_released", lambda name: True)
    monkeypatch.setattr(ui_app, "_read_pid", lambda: 4321)
    monkeypatch.setattr(ui_app, "_pid_is_alive", lambda pid: True)
    monkeypatch.setattr(ui_app, "_clear_pid", lambda: None)
    assert ui_app._stop_bot() is True
    assert killed == [4321]
