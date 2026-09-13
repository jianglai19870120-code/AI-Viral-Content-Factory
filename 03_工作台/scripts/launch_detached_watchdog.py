from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the workbench watchdog outside the parent job.")
    parser.add_argument("--watcher", required=True)
    parser.add_argument("--working-directory", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    watcher = Path(args.watcher).resolve()
    working_directory = Path(args.working_directory).resolve()
    runtime = Path(args.runtime).resolve()
    log = runtime / "detached-launch.log"
    child_log = runtime / "detached-watchdog.log"
    # SystemRoot is normally C:\Windows; use it instead of PATH from Codex or
    # Task Scheduler so the launcher has the same executable in every context.
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not watcher.is_file():
        raise FileNotFoundError(f"watchdog script is missing: {watcher}")
    if not powershell.is_file():
        raise FileNotFoundError(f"Windows PowerShell is missing: {powershell}")

    command = [
        str(powershell),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        str(watcher),
        "-RuntimePath",
        str(runtime),
        "-Port",
        str(args.port),
    ]
    # Breakaway is the persistence mechanism. DETACHED_PROCESS makes Windows
    # PowerShell exit before executing its script in this desktop environment.
    base_flags = subprocess.CREATE_NEW_PROCESS_GROUP
    breakaway_flag = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    with child_log.open("ab") as stream:
        try:
            process = subprocess.Popen(
                command,
                cwd=working_directory,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=stream,
                close_fds=True,
                creationflags=base_flags | breakaway_flag,
            )
            append_log(log, f"watchdog pid={process.pid} breakaway=true port={args.port}")
            time.sleep(1)
            if process.poll() is not None:
                append_log(log, f"watchdog pid={process.pid} exited immediately code={process.returncode}")
        except OSError as exc:
            # Some restricted Windows job objects disallow breakaway. Keep a
            # short-lived fallback for immediate availability and leave evidence
            # that an elevated task installation is required for permanence.
            append_log(log, f"breakaway denied: {exc}; starting attached fallback")
            process = subprocess.Popen(
                command,
                cwd=working_directory,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=stream,
                close_fds=True,
                creationflags=base_flags,
            )
            append_log(log, f"watchdog pid={process.pid} breakaway=false port={args.port}")
            time.sleep(1)
            if process.poll() is not None:
                append_log(log, f"watchdog pid={process.pid} exited immediately code={process.returncode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
