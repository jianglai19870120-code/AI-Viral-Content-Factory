#!/usr/bin/env python3
"""Run visible-Codex task creation in the signed-in Windows user session."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen

from codex_desktop_bridge import create_auxiliary_skill_repair, create_visible_task, find_codex_window, native_task_bridge_available, resume_visible_task


MUTEX_NAME = "Local\\AI-Viral-Content-Factory-Codex-Desktop-Bridge-Agent-v2"
WAIT_OBJECT_0 = 0
WAIT_ABANDONED = 0x80
SW_RESTORE = 9
SW_SHOWNORMAL = 1
UOI_NAME = 2
AGENT_ID = uuid.uuid4().hex
LAST_ERROR = ""
LAST_ERROR_LOCK = threading.Lock()
LAST_CODEX_WINDOW = 0

ctypes.windll.user32.GetProcessWindowStation.argtypes = ()
ctypes.windll.user32.GetProcessWindowStation.restype = wintypes.HANDLE
ctypes.windll.user32.GetThreadDesktop.argtypes = (wintypes.DWORD,)
ctypes.windll.user32.GetThreadDesktop.restype = wintypes.HANDLE
ctypes.windll.user32.IsWindowVisible.argtypes = (wintypes.HWND,)
ctypes.windll.user32.IsWindowVisible.restype = wintypes.BOOL
ctypes.windll.user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
ctypes.windll.user32.GetClassNameW.restype = ctypes.c_int
ctypes.windll.user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
ctypes.windll.user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
ctypes.windll.shell32.ShellExecuteW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int)
ctypes.windll.shell32.ShellExecuteW.restype = wintypes.HINSTANCE


def request_json(url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json; charset=utf-8"} if payload is not None else {},
        method="POST" if payload is not None else "GET",
    )
    with urlopen(request, timeout=5) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("工作台桥接响应格式不正确")
    if decoded.get("error"):
        raise RuntimeError(str(decoded["error"]))
    return decoded


def report_failure(port: int, session_id: str, message: str) -> None:
    try:
        request_json(
            f"http://127.0.0.1:{port}/api/desktop-bridge-event",
            {"sessionId": session_id, "stage": "failed", "message": message[:500]},
        )
    except (OSError, URLError, RuntimeError, json.JSONDecodeError):
        pass


def set_last_error(message: str = "") -> None:
    global LAST_ERROR
    with LAST_ERROR_LOCK:
        LAST_ERROR = message[:500]


def user_object_name(handle: int) -> str:
    needed = wintypes.DWORD()
    ctypes.windll.user32.GetUserObjectInformationW(handle, UOI_NAME, None, 0, ctypes.byref(needed))
    if not needed.value:
        return ""
    buffer = ctypes.create_unicode_buffer(max(1, needed.value // ctypes.sizeof(ctypes.c_wchar)))
    if not ctypes.windll.user32.GetUserObjectInformationW(handle, UOI_NAME, buffer, needed, ctypes.byref(needed)):
        return ""
    return buffer.value


def desktop_context() -> dict[str, object]:
    global LAST_CODEX_WINDOW
    session_id = current_windows_session_id()
    station = user_object_name(ctypes.windll.user32.GetProcessWindowStation())
    desktop = user_object_name(ctypes.windll.user32.GetThreadDesktop(ctypes.windll.kernel32.GetCurrentThreadId()))
    interactive = session_id > 0 and station.lower() == "winsta0" and desktop.lower() == "default"
    with LAST_ERROR_LOCK:
        last_error = LAST_ERROR
    codex_window = find_codex_window() if interactive else 0
    # A transient discovery miss must not discard the HWND confirmed by the
    # preceding heartbeat.  Desktop-window enumeration can briefly return an
    # empty set while the shell changes foreground windows.
    if codex_window:
        LAST_CODEX_WINDOW = int(codex_window)
    codex_detected = bool(codex_window or LAST_CODEX_WINDOW)
    return {
        "agentId": AGENT_ID,
        "pid": os.getpid(),
        "user": getpass.getuser(),
        "windowsSessionId": session_id,
        "windowStation": station,
        "desktop": desktop,
        "interactiveSession": interactive,
        "codexWindowDetected": codex_detected,
        "codexWindowHandle": int(codex_window or LAST_CODEX_WINDOW or 0),
        "nativeTaskCreateAvailable": bool(interactive and native_task_bridge_available()),
        "folderLaunchAvailable": interactive,
        "lastError": last_error,
    }


def send_heartbeat(port: int) -> dict[str, object]:
    context = desktop_context()
    request_json(f"http://127.0.0.1:{port}/api/desktop-bridge/heartbeat", context)
    # A previous server reload can briefly refuse a request.  Once the next
    # heartbeat succeeds, clear that stale failure instead of reporting the
    # bridge as broken indefinitely.
    if context.get("lastError"):
        set_last_error()
    return context


def run_job(job: dict[str, object], *, window_handle: int = 0) -> None:
    session_id = str(job.get("sessionId") or "")
    title = str(job.get("title") or "")
    prompt_file = str(job.get("promptFile") or "")
    project_root = str(job.get("projectRoot") or "")
    port = int(job.get("port") or 8766)
    if not all((session_id, title, prompt_file, project_root)):
        raise RuntimeError("桌面桥接任务缺少必要字段")
    # Keep UI automation in the already-verified interactive agent process.
    # A hidden child process can be attached to another window desktop even
    # when its parent is in the user's WinSta0\Default desktop.
    # Re-read the target at the exact moment before focus.  The heartbeat is a
    # capability snapshot and the server-side copy can be a fraction of a
    # second old; it must never be the sole source of the HWND used for a
    # visible task.
    live_window = int(find_codex_window() or 0)
    server_window = 0
    if not live_window:
        # The server persists the most recent heartbeat HWND.  Use it only as
        # a fallback for a transient local enumeration miss, never as proof a
        # task was delivered.
        try:
            health = request_json(f"http://127.0.0.1:{port}/api/health")
            navigation = health.get("desktopNavigation") if isinstance(health, dict) else None
            agent = navigation.get("agent") if isinstance(navigation, dict) else None
            if isinstance(agent, dict):
                server_window = int(agent.get("codexWindowHandle") or 0)
        except (OSError, URLError, RuntimeError, json.JSONDecodeError, ValueError, TypeError):
            server_window = 0
    chosen_window = live_window or server_window or int(window_handle or LAST_CODEX_WINDOW)
    try:
        request_json(
            f"http://127.0.0.1:{port}/api/desktop-bridge-event",
            {
                "sessionId": session_id,
                "stage": "focusing",
                "message": f"桥接句柄诊断：本机={live_window}，心跳={server_window}，缓存={LAST_CODEX_WINDOW}，采用={chosen_window}。",
            },
        )
    except (OSError, URLError, RuntimeError, json.JSONDecodeError):
        pass
    repair = job.get("repairTask") if isinstance(job.get("repairTask"), dict) else {}
    if str(job.get("jobKind") or "create") == "resume" and repair.get("required"):
        repair_task_id = create_auxiliary_skill_repair(title, str(job.get("repairPromptFile") or ""), project_root=project_root)
        state_path = Path(str(job.get("recoveryStatePath") or ""))
        if not state_path.is_absolute():
            state_path = Path(project_root) / state_path
        controller = Path(project_root) / "10_Skills武器库" / "IP视觉PPT生成Skill" / "scripts" / "render_recovery_loop.py"
        result = subprocess.run(
            [sys.executable, str(controller), "--workdir", str(state_path.parent), "mark-repair-dispatched", "--request-id", str(repair.get("request_id") or ""), "--task-id", repair_task_id],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "无法写入 Skill 修复任务派发状态")
        request_json(f"http://127.0.0.1:{port}/api/desktop-bridge-event", {"sessionId": session_id, "stage": "repair-task-created", "message": f"已自动创建独立 Skill 修复任务：{repair_task_id}"})
        completed = 0
    elif str(job.get("jobKind") or "create") == "resume":
        completed = resume_visible_task(
            session_id,
            str(job.get("codexThreadId") or ""),
            title,
            prompt_file,
            port,
            project_root=project_root,
        )
    else:
        completed = create_visible_task(
            session_id,
            title,
            prompt_file,
            port,
            project_root=project_root,
            window_handle=chosen_window,
        )
    if completed:
        report_failure(port, session_id, "当前登录用户的 Codex 桌面桥接未能完成任务创建。")
        set_last_error("Codex 桌面任务创建失败")
    else:
        set_last_error()


def explorer_windows() -> set[int]:
    windows: set[int] = set()
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True
        buffer = ctypes.create_unicode_buffer(128)
        ctypes.windll.user32.GetClassNameW(hwnd, buffer, len(buffer))
        if buffer.value in {"CabinetWClass", "ExploreWClass"}:
            windows.add(int(hwnd))
        return True

    ctypes.windll.user32.EnumWindows(callback, 0)
    return windows


def explorer_folder_paths() -> set[str]:
    """Return paths displayed by visible Explorer shell windows.

    A launched Explorer process is not enough evidence: Windows may reuse an
    existing window or leave it focused on a previous location.  Shell
    automation lets us verify the exact displayed folder before reporting the
    request as opened.
    """
    script = (
        "$OutputEncoding=[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
        "$shell=New-Object -ComObject Shell.Application;"
        "$paths=@($shell.Windows() | ForEach-Object { try { $_.Document.Folder.Self.Path } catch {} } | Where-Object { $_ });"
        "$paths | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return set()
        payload = json.loads(result.stdout)
        values = payload if isinstance(payload, list) else [payload]
        return {os.path.normcase(str(value)) for value in values if isinstance(value, str) and value}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return set()


def launch_explorer(path: Path, timeout: float = 8.0) -> None:
    before = explorer_windows()
    target = os.path.normcase(str(path.resolve()))
    parameters = f'/n,/e,"{path}"'
    result = ctypes.windll.shell32.ShellExecuteW(None, "open", "explorer.exe", parameters, None, SW_SHOWNORMAL)
    if int(result) <= 32:
        raise OSError(f"Windows Shell 启动资源管理器失败（错误码 {int(result)}）")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = explorer_windows()
        created = current - before
        if target in explorer_folder_paths():
            if created:
                window = next(iter(created))
                ctypes.windll.user32.ShowWindow(window, SW_RESTORE)
                ctypes.windll.user32.SetForegroundWindow(window)
            return
        if created:
            window = next(iter(created))
            ctypes.windll.user32.ShowWindow(window, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(window)
        time.sleep(0.2)
    raise RuntimeError("资源管理器未显示目标文件夹，未确认打开成功")


def run_folder_job(job: dict[str, object], port: int) -> None:
    request_id = str(job.get("requestId") or "")
    path = Path(str(job.get("path") or ""))
    if not request_id or not path.is_dir():
        raise RuntimeError("文件夹打开请求缺少有效目录")
    try:
        launch_explorer(path)
        request_json(f"http://127.0.0.1:{port}/api/desktop-bridge/folder-event", {"requestId": request_id, "status": "opened", "message": f"已确认打开：{path}"})
        set_last_error()
    except (OSError, RuntimeError) as exc:
        set_last_error(str(exc))
        try:
            request_json(f"http://127.0.0.1:{port}/api/desktop-bridge/folder-event", {"requestId": request_id, "status": "failed", "message": str(exc)})
        except (OSError, URLError, RuntimeError, json.JSONDecodeError):
            pass


def acquire_mutex() -> int:
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError()
    result = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
    if result not in (WAIT_OBJECT_0, WAIT_ABANDONED):
        ctypes.windll.kernel32.CloseHandle(handle)
        return 0
    return handle


def current_windows_session_id() -> int:
    """Return the Windows session hosting this process."""
    session_id = ctypes.c_ulong()
    if not ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session_id)):
        raise ctypes.WinError()
    return int(session_id.value)


def folder_worker(port: int, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            pending = request_json(f"http://127.0.0.1:{port}/api/desktop-bridge/folder-pending")
            job = pending.get("job")
            if isinstance(job, dict):
                claimed = request_json(
                    f"http://127.0.0.1:{port}/api/desktop-bridge/folder-claim",
                    {"requestId": str(job.get("requestId") or "")},
                )
                run_folder_job(claimed, port)
        except (OSError, URLError, RuntimeError, json.JSONDecodeError) as exc:
            set_last_error(str(exc))
        stop.wait(0.4)


def main() -> int:
    parser = argparse.ArgumentParser(description="AI爆款内容工厂当前用户 Codex 桌面桥接")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    # Session 0 belongs to services and cannot present Explorer or Codex UI to
    # the signed-in user. The login-started agent is the only valid claimant.
    if os.name == "nt" and current_windows_session_id() == 0:
        return 0

    mutex = acquire_mutex()
    if not mutex:
        return 0
    stop = threading.Event()
    try:
        workers = [threading.Thread(target=folder_worker, args=(args.port, stop), daemon=True, name="folder-launch-bridge")]
        for worker in workers:
            worker.start()
        while True:
            try:
                context = send_heartbeat(args.port)
                # Codex itself must be automated from this process's main
                # interactive thread. Worker threads can enumerate a different
                # desktop even when the process heartbeat is on WinSta0.
                pending = request_json(f"http://127.0.0.1:{args.port}/api/desktop-bridge/pending")
                job = pending.get("job")
                if isinstance(job, dict):
                    claimed = request_json(
                        f"http://127.0.0.1:{args.port}/api/desktop-bridge/claim",
                        {"sessionId": str(job.get("sessionId") or "")},
                    )
                    run_job(claimed, window_handle=int(claimed.get("windowHandle") or context.get("codexWindowHandle") or LAST_CODEX_WINDOW))
            except (OSError, URLError, RuntimeError, json.JSONDecodeError) as exc:
                set_last_error(str(exc))
            time.sleep(max(0.5, args.interval))
    finally:
        stop.set()
        ctypes.windll.kernel32.ReleaseMutex(mutex)
        ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
