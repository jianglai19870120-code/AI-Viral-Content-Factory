#!/usr/bin/env python3
"""Keep the local workbench alive outside the Codex process tree."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


MUTEX_NAME = "Local\\AI-Viral-Content-Factory-Workbench-Watchdog"
WAIT_OBJECT_0 = 0
WAIT_ABANDONED = 0x80
RELOAD_SOURCES = (
    "server.py",
    "frontend/app.js",
    "workflow/data_center.py",
    "workflow/input_inventory.py",
    "scripts/codex_desktop_bridge.py",
    "scripts/codex_desktop_bridge_agent.py",
)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{now()} {message}\n")


def write_state(path: Path, **value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def get_health(port: int) -> dict[str, object] | None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return None
    if payload.get("service") == "ai-viral-workbench" and payload.get("port") == port:
        return payload
    return None


def source_signature(root: Path) -> str:
    """Fingerprint executable workbench sources, never user assets or runtime."""
    digest = hashlib.sha256()
    for relative in RELOAD_SOURCES:
        path = (root.parent / relative).resolve() if relative.startswith("workflow/") else (root / relative).resolve()
        try:
            stat = path.stat()
        except OSError:
            digest.update(f"{relative}:missing".encode("utf-8"))
            continue
        digest.update(f"{relative}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8"))
    return digest.hexdigest()


def stop_server(process: subprocess.Popen[bytes] | None, runtime: Path) -> None:
    """Stop only the recorded workbench server before its source reload."""
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            process.kill()
            return
    try:
        payload = json.loads((runtime / "workbench-service.json").read_text(encoding="utf-8"))
        pid = int(payload.get("pid") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        return
    if pid and pid != os.getpid():
        subprocess.run(["taskkill.exe", "/PID", str(pid), "/F"], check=False, capture_output=True)


def start_server(root: Path, runtime: Path, python: Path, port: int) -> subprocess.Popen[bytes]:
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}"
    stdout_path = runtime / f"server-{port}-{run_id}.out.log"
    stderr_path = runtime / f"server-{port}-{run_id}.err.log"
    environment = os.environ.copy()
    environment["AI_VIRAL_WORKBENCH_RUNTIME"] = str(runtime)
    stdout = stdout_path.open("ab")
    stderr = stderr_path.open("ab")
    try:
        process = subprocess.Popen(
            [str(python), "-u", "server.py", "--port", str(port), "--no-browser"],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    finally:
        stdout.close()
        stderr.close()
    write_state(
        runtime / "workbench-service.json",
        pid=process.pid,
        port=port,
        pythonPath=str(python),
        startedAt=now(),
        status="starting",
        stdout=str(stdout_path),
        stderr=str(stderr_path),
    )
    return process


def write_service_healthy(runtime: Path, process: subprocess.Popen[bytes], port: int, health: dict[str, object]) -> None:
    """Replace the provisional launch state after the authenticated health check."""
    current = runtime / "workbench-service.json"
    try:
        saved = json.loads(current.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        saved = {}
    write_state(
        current,
        pid=process.pid,
        port=port,
        pythonPath=saved.get("pythonPath", ""),
        startedAt=saved.get("startedAt", now()),
        status="healthy",
        instanceId=health.get("instanceId", ""),
        stdout=saved.get("stdout", ""),
        stderr=saved.get("stderr", ""),
    )


def acquire_mutex() -> int:
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError()
    result = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
    if result not in (WAIT_OBJECT_0, WAIT_ABANDONED):
        ctypes.windll.kernel32.CloseHandle(handle)
        return 0
    return handle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--interval", type=int, default=10)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    runtime = Path(args.runtime).resolve()
    python = Path(args.python).resolve()
    log = runtime / "python-watchdog.log"
    state = runtime / "watchdog-state.json"
    runtime.mkdir(parents=True, exist_ok=True)
    if not root.joinpath("server.py").is_file() or not python.is_file():
        append_log(log, "watchdog configuration is invalid")
        return 1

    mutex = acquire_mutex()
    if not mutex:
        append_log(log, "watchdog exited because another watchdog owns the mutex")
        return 0

    append_log(log, f"watchdog started pid={os.getpid()} port={args.port}")
    signature = source_signature(root)
    process: subprocess.Popen[bytes] | None = None
    try:
        while True:
            health = get_health(args.port)
            if health:
                current_signature = source_signature(root)
                if current_signature != signature:
                    append_log(log, "workbench source changed; restarting service")
                    stop_server(process, runtime)
                    process = None
                    signature = current_signature
                    time.sleep(0.5)
                    continue
                write_state(
                    state,
                    pid=os.getpid(),
                    port=args.port,
                    checkedAt=now(),
                    status="healthy",
                    message="",
                    instanceId=health.get("instanceId", ""),
                    serviceStartedAt=health.get("startedAt", ""),
                )
            else:
                write_state(
                    state,
                    pid=os.getpid(),
                    port=args.port,
                    checkedAt=now(),
                    status="starting",
                    message="Health endpoint is unavailable; starting workbench.",
                    instanceId="",
                    serviceStartedAt="",
                )
                process = start_server(root, runtime, python, args.port)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    time.sleep(0.4)
                    health = get_health(args.port)
                    if health:
                        break
                    if process.poll() is not None:
                        raise RuntimeError(f"Workbench process exited with code {process.returncode}")
                if not health:
                    raise RuntimeError("Workbench did not pass its health check within 20 seconds")
                write_service_healthy(runtime, process, args.port, health)
                signature = source_signature(root)
            time.sleep(args.interval)
    except Exception as exc:
        append_log(log, f"watchdog failed: {exc}")
        write_state(
            state,
            pid=os.getpid(),
            port=args.port,
            checkedAt=now(),
            status="failed",
            message=str(exc),
            instanceId="",
            serviceStartedAt="",
        )
        return 1
    finally:
        ctypes.windll.kernel32.ReleaseMutex(mutex)
        ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    sys.exit(main())
