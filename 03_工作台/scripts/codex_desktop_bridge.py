#!/usr/bin/env python3
"""Create a visible Codex Desktop task from the local workbench.

This helper intentionally uses the Desktop UI rather than ``codex app-server``:
the latter creates an invisible background thread. It reports only lifecycle
milestones back to the workbench; content production remains inside Codex.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
SW_RESTORE = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
VK_CONTROL = 0x11
VK_N = 0x4E
VK_V = 0x56
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
KEYEVENTF_KEYUP = 0x0002
# Codex Desktop is hosted by the ChatGPT desktop shell on this machine, whose
# visible main window title is "ChatGPT" rather than "Codex".
WINDOW_TITLES = ("codex", "chatgpt")

user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = ()
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = ()
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HANDLE
kernel32.GlobalLock.argtypes = (wintypes.HANDLE,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (wintypes.HANDLE,)
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = (wintypes.HANDLE,)
kernel32.GlobalFree.restype = wintypes.HANDLE
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.IsWindow.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.ShowWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = (wintypes.HWND,)
user32.BringWindowToTop.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
user32.AttachThreadInput.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p))


class INPUT_UNION(ctypes.Union):
    _fields_ = (("ki", KEYBDINPUT),)


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = (("type", wintypes.DWORD), ("union", INPUT_UNION))


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostMessageW.restype = wintypes.BOOL
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT

ACTIVE_CODEX_WINDOW = 0
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
PIPE_WAIT_MILLISECONDS = 5000
NATIVE_BRIDGE_CACHE_SECONDS = 3.0
_NATIVE_BRIDGE_CACHE: tuple[float, bool] = (0.0, False)

kernel32.CreateFileW.argtypes = (
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
)
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.ReadFile.argtypes = (
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
)
kernel32.ReadFile.restype = wintypes.BOOL
kernel32.WriteFile.argtypes = (
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
)
kernel32.WriteFile.restype = wintypes.BOOL
kernel32.WaitNamedPipeW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD)
kernel32.WaitNamedPipeW.restype = wintypes.BOOL


def report(port: int, session_id: str, stage: str, message: str) -> None:
    payload = json.dumps(
        {"sessionId": session_id, "stage": stage, "message": message}, ensure_ascii=False
    ).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{port}/api/desktop-bridge-event",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5):
            pass
    except (URLError, OSError):
        # The workbench may be restarting. Do not crash while a visible task
        # has already been created; the user can still see it in Codex.
        pass


def _process_image(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def find_codex_window() -> int:
    # On this machine Codex Desktop is hosted in the ChatGPT shell. FindWindow
    # remains available even when EnumWindows is filtered by a background
    # helper's window-enumeration context.
    for title in ("ChatGPT", "Codex"):
        direct = user32.FindWindowW(None, title)
        if direct:
            return int(direct)
    process_matches: list[int] = []
    title_matches: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip().lower()
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        image = _process_image(int(pid.value)).lower()
        # Current Codex Desktop is packaged as OpenAI.Codex but its executable
        # and main-window title are both ChatGPT. Process identity is stable
        # across localized or task-specific window titles.
        if image.endswith("\\chatgpt.exe") and ("openai.codex_" in image or "\\openai.codex\\" in image):
            process_matches.append(int(hwnd))
        elif any(name in title for name in WINDOW_TITLES):
            title_matches.append(int(hwnd))
        return True

    user32.EnumWindows(callback, 0)
    return (process_matches or title_matches or [0])[-1]


def wait_for_codex_window(timeout: float = 5.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window = find_codex_window()
        if window:
            return window
        time.sleep(0.2)
    return 0


def heartbeat_codex_window(port: int) -> int:
    """Read the last interactive-agent HWND when local enumeration races.

    The bridge agent has already proved that the heartbeat originates from the
    signed-in WinSta0/Default desktop.  A short-lived enumeration miss must not
    throw away that verified handle, but the handle is still checked locally
    before it is used for focus/input.
    """
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        navigation = payload.get("desktopNavigation") if isinstance(payload, dict) else None
        agent = navigation.get("agent") if isinstance(navigation, dict) else None
        window = int(agent.get("codexWindowHandle") or 0) if isinstance(agent, dict) else 0
        if window and user32.IsWindow(window) and user32.IsWindowVisible(window):
            return window
    except (OSError, URLError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return 0


def _powershell() -> str:
    return shutil.which("powershell") or shutil.which("pwsh") or "powershell"


def _desktop_codex_homes() -> list[Path]:
    """Find the signed-in user's actual Codex history, not a service profile."""
    candidates: list[Path] = []
    for value in (os.environ.get("CODEX_HOME", ""), os.environ.get("USERPROFILE", "")):
        if value:
            base = Path(value)
            candidates.append(base if base.name.lower() == ".codex" else base / ".codex")
    candidates.append(Path.home() / ".codex")
    users_root = Path("C:/Users")
    if users_root.is_dir():
        candidates.extend(path / ".codex" for path in users_root.iterdir() if path.is_dir())
    usable: list[Path] = []
    for candidate in candidates:
        try:
            if (candidate / "sessions").is_dir() and candidate not in usable:
                usable.append(candidate)
        except OSError:
            continue
    return sorted(usable, key=lambda path: (path / "sessions").stat().st_mtime, reverse=True)


def _native_pipe_candidates() -> list[str]:
    """Return app-tool pipe paths published by the running Desktop app.

    The pipe name is intentionally discovered for every Desktop installation;
    it contains a per-process random suffix and must never be hard-coded.

    Older Desktop builds placed the value in the ``codex.exe`` command line.
    Current builds pass it only through the MCP process environment, so an
    interactive bridge started at login cannot inherit the variable.  Discover
    the same ephemeral path from the current environment when available, then
    from the live named-pipe directory as a compatibility fallback.  Every
    discovered candidate is still probed with ``tools/list`` before use.
    """
    paths: list[str] = []

    def add(path: str) -> None:
        raw = path.strip().rstrip("\\")
        for value in (raw, raw.replace("\\\\", "\\").rstrip("\\")):
            if value.startswith("\\\\.\\pipe\\") and value not in paths:
                paths.append(value)

    add(os.environ.get("CODEX_APP_TOOLS_PIPE_PATH", ""))

    # The Desktop app uses random codex-browser-use / codex-computer-use pipe
    # names for its app-tool host.  ``dir`` is a read-only Windows pipe
    # enumeration and works from the login-started bridge even though that
    # process does not inherit the Desktop task's environment variable.
    try:
        pipe_listing = subprocess.run(
            ["cmd.exe", "/d", "/s", "/c", r"dir \\.\pipe" + "\\"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if pipe_listing.returncode == 0:
            for line in pipe_listing.stdout.splitlines():
                match = re.match(r"^\s*\d{4}[/-]\d{1,2}[/-]\d{1,2}\s+\d{1,2}:\d{2}\s+\d+\s+(.+?)\s*$", line)
                name = match.group(1) if match else ""
                if re.fullmatch(r"codex-(?:browser-use|computer-use)-[0-9a-f-]{8,}", name, flags=re.IGNORECASE):
                    add("\\\\.\\pipe\\" + name)
    except (OSError, subprocess.SubprocessError):
        pass

    command = (
        "Get-CimInstance Win32_Process -Filter \"Name = 'codex.exe'\" | "
        "Where-Object { $_.CommandLine -match 'CODEX_APP_TOOLS_PIPE_PATH' } | "
        "ForEach-Object { $_.CommandLine } | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            [_powershell(), "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return paths
        raw_commands = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return paths
    command_lines = raw_commands if isinstance(raw_commands, list) else [raw_commands]
    for command_line in command_lines:
        if not isinstance(command_line, str):
            continue
        # Electron serializes environment values inside a JSON-like command
        # argument: CODEX_APP_TOOLS_PIPE_PATH\"=\"\\\\.\\pipe\\...
        match = re.search(r'CODEX_APP_TOOLS_PIPE_PATH\\?"=\\?"([^",]+)', command_line)
        if not match:
            continue
        # The surrounding Electron command escapes its closing quote as
        # ``\"``; discard that delimiter escape after unescaping slashes.
        add(match.group(1))
    return paths


def _native_read_exact(handle: int, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        buffer = ctypes.create_string_buffer(remaining)
        received = wintypes.DWORD()
        if not kernel32.ReadFile(handle, buffer, remaining, ctypes.byref(received), None):
            raise OSError(ctypes.get_last_error(), "无法读取 Codex Desktop 原生桥接响应")
        if not received.value:
            raise RuntimeError("Codex Desktop 原生桥接意外关闭")
        chunks.append(buffer.raw[:received.value])
        remaining -= int(received.value)
    return b"".join(chunks)


def _native_write_all(handle: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        chunk = payload[offset:]
        buffer = ctypes.create_string_buffer(chunk)
        written = wintypes.DWORD()
        if not kernel32.WriteFile(handle, buffer, len(chunk), ctypes.byref(written), None):
            raise OSError(ctypes.get_last_error(), "无法发送 Codex Desktop 原生桥接请求")
        if not written.value:
            raise RuntimeError("Codex Desktop 原生桥接未接收请求")
        offset += int(written.value)


def _native_rpc(pipe_path: str, request: dict[str, object]) -> dict[str, object]:
    if not kernel32.WaitNamedPipeW(pipe_path, PIPE_WAIT_MILLISECONDS):
        raise OSError(ctypes.get_last_error(), "Codex Desktop 原生桥接管道不可用")
    handle = kernel32.CreateFileW(
        pipe_path,
        GENERIC_READ | GENERIC_WRITE,
        0,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        raise OSError(ctypes.get_last_error(), "无法连接 Codex Desktop 原生桥接")
    try:
        encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        _native_write_all(handle, struct.pack("<I", len(encoded)) + encoded)
        response_size = struct.unpack("<I", _native_read_exact(handle, 4))[0]
        if response_size < 2 or response_size > 16 * 1024 * 1024:
            raise RuntimeError("Codex Desktop 原生桥接返回了无效响应长度")
        decoded = json.loads(_native_read_exact(handle, response_size).decode("utf-8"))
        if not isinstance(decoded, dict):
            raise RuntimeError("Codex Desktop 原生桥接响应格式不正确")
        if decoded.get("error"):
            error = decoded["error"]
            raise RuntimeError(str(error.get("message") if isinstance(error, dict) else error))
        return decoded
    finally:
        kernel32.CloseHandle(handle)


def _native_tool_call(pipe_path: str, tool: str, parent_thread_id: str, arguments: dict[str, object]) -> dict[str, object]:
    request_id = uuid.uuid4().int & 0x7FFFFFFF
    call_id = f"workbench-desktop-{uuid.uuid4()}"
    response = _native_rpc(
        pipe_path,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "namespace": "codex_app",
                "tool": tool,
                "threadId": parent_thread_id,
                "turnId": f"desktop-bridge-{uuid.uuid4()}",
                "callId": call_id,
                "arguments": arguments,
            },
        },
    )
    result = response.get("result")
    if not isinstance(result, dict) or not result.get("success"):
        raise RuntimeError("Codex Desktop 未接受原生任务请求")
    items = result.get("contentItems")
    if not isinstance(items, list):
        raise RuntimeError("Codex Desktop 原生任务响应缺少内容")
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            try:
                content = json.loads(item["text"])
            except json.JSONDecodeError:
                continue
            if isinstance(content, dict):
                return content
    raise RuntimeError("Codex Desktop 原生任务响应无法解析")


def _desktop_anchor_thread(project_root: str) -> str:
    """Read the local Desktop session manifests to find a valid parent task.

    A login-started agent can inherit a service PATH/profile, so asking a
    second CLI process to enumerate history is not reliable.  These JSONL
    manifests are read-only Desktop task metadata; task creation still uses
    the running Desktop app's native pipe below.
    """
    root = Path(project_root).resolve()
    candidates: list[tuple[int, str]] = []
    for codex_home in _desktop_codex_homes():
        session_root = codex_home / "sessions"
        if not session_root.is_dir():
            continue
        try:
            manifests = sorted(
                (path for path in session_root.rglob("*.jsonl") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )[:300]
        except OSError:
            manifests = []
        for manifest in manifests:
            try:
                with manifest.open("r", encoding="utf-8") as stream:
                    record = json.loads(stream.readline())
                payload = record.get("payload") if isinstance(record, dict) else None
                if not isinstance(payload, dict):
                    continue
                thread_id = str(payload.get("session_id") or payload.get("id") or "")
                cwd = str(payload.get("cwd") or "")
                if thread_id and cwd and Path(cwd).resolve() == root:
                    candidates.append((int(manifest.stat().st_mtime_ns), thread_id))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
    if not candidates:
        raise RuntimeError("未找到此项目的现有 Codex 桌面任务，请先在 Codex 中打开本项目后重试")
    return max(candidates)[1]


def _desktop_project_id(pipe_path: str, parent_thread_id: str, project_root: str) -> str:
    projects = _native_tool_call(pipe_path, "list_projects", parent_thread_id, {}).get("projects")
    target = Path(project_root).resolve()
    if isinstance(projects, list):
        for project in projects:
            if not isinstance(project, dict):
                continue
            path = str(project.get("path") or "")
            try:
                if path and Path(path).resolve() == target:
                    project_id = str(project.get("projectId") or "")
                    if project_id:
                        return project_id
            except OSError:
                continue
    raise RuntimeError("Codex Desktop 未找到本项目，无法创建可见任务")


def native_task_bridge_available() -> bool:
    """Whether this interactive desktop can answer a native app-tools probe."""
    global _NATIVE_BRIDGE_CACHE
    checked_at, available = _NATIVE_BRIDGE_CACHE
    if time.monotonic() - checked_at < NATIVE_BRIDGE_CACHE_SECONDS:
        return available
    available = False
    for pipe_path in _native_pipe_candidates():
        try:
            response = _native_rpc(pipe_path, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"threadStartKind": "all"}})
            available = isinstance(response.get("result"), dict)
            if available:
                break
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError):
            continue
    _NATIVE_BRIDGE_CACHE = (time.monotonic(), available)
    return available


def copy_text(text: str) -> None:
    opened = False
    for _ in range(12):
        if user32.OpenClipboard(None):
            opened = True
            break
        time.sleep(0.08)
    if not opened:
        raise RuntimeError("无法打开系统剪贴板")
    try:
        if not user32.EmptyClipboard():
            raise RuntimeError("无法清空系统剪贴板")
        data = (text + "\0").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise RuntimeError("无法分配剪贴板内存")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            raise RuntimeError("无法写入系统剪贴板")
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise RuntimeError("无法设置系统剪贴板")
    finally:
        user32.CloseClipboard()


def send_key(vk: int, *, up: bool = False) -> None:
    entry = INPUT(type=1, ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None))
    if user32.SendInput(1, ctypes.byref(entry), ctypes.sizeof(INPUT)) == 1:
        return
    # Some Windows installations protect the packaged Codex shell from
    # SendInput despite allowing the current user to focus it.  Fall back to
    # the focused window's normal message loop; this remains scoped to the
    # exact Codex HWND we just foregrounded.
    if ACTIVE_CODEX_WINDOW:
        scan_code = int(user32.MapVirtualKeyW(vk, 0)) & 0xFF
        lparam = 1 | (scan_code << 16)
        if up:
            lparam |= 0xC0000000
        if user32.PostMessageW(ACTIVE_CODEX_WINDOW, WM_KEYUP if up else WM_KEYDOWN, vk, lparam):
            return
    raise RuntimeError("无法向 Codex 桌面发送键盘操作")


def hotkey(vk: int) -> None:
    send_key(VK_CONTROL)
    send_key(vk)
    send_key(vk, up=True)
    send_key(VK_CONTROL, up=True)


def enter() -> None:
    send_key(0x0D)
    send_key(0x0D, up=True)


def focus(window: int) -> None:
    global ACTIVE_CODEX_WINDOW
    user32.ShowWindow(window, SW_RESTORE)
    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = bool(foreground_thread and foreground_thread != current_thread and user32.AttachThreadInput(current_thread, foreground_thread, True))
    try:
        user32.BringWindowToTop(window)
        user32.SetForegroundWindow(window)
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)
    time.sleep(0.45)
    if user32.GetForegroundWindow() != window:
        raise RuntimeError("无法将 Codex 桌面窗口置前")
    ACTIVE_CODEX_WINDOW = int(window)


def create_visible_task(session_id: str, title: str, prompt_file: str, port: int, *, project_root: str, dry_run: bool = False, window_handle: int = 0) -> int:
    """Create a real Desktop task and return only after its thread id exists.

    The former keyboard path could at most prove that keystrokes were sent to
    a foreground window.  The native Desktop app-tools pipe returns the actual
    new thread id, so the workbench can distinguish a created task from a
    failed attempt without guessing from UI focus or clipboard state.
    """
    prompt_path = Path(prompt_file)
    try:
        prompt = prompt_path.read_text(encoding="utf-8")
        if not prompt.strip():
            raise RuntimeError("固定提示词为空")
        callback = (
            "\n\n工作台阶段回写：任务真正开始后执行以下命令回写 `started`；"
            "审核、修复或结束时按同一方式回写对应事件。\n"
            f"`python 03_工作台/scripts/report_visible_task_event.py --session {session_id} "
            f"--event started --port {port}`"
        )
        message = f"# {title}\n\n{prompt}{callback}"
        report(port, session_id, "focusing", "正在确认当前登录用户的 Codex Desktop 原生桥接。")
        pipe_paths = _native_pipe_candidates()
        if not pipe_paths:
            raise RuntimeError("未检测到 Codex Desktop 原生桥接，请先打开 Codex 桌面应用。")
        if dry_run:
            return 0
        report(port, session_id, "creating", "正在通过 Codex Desktop 原生桥接创建新任务。")
        root = str(Path(project_root).resolve())
        parent_thread_id = _desktop_anchor_thread(root)
        last_error = ""
        for pipe_path in pipe_paths:
            try:
                project_id = _desktop_project_id(pipe_path, parent_thread_id, root)
                created = _native_tool_call(
                    pipe_path,
                    "create_thread",
                    parent_thread_id,
                    {
                        "title": title,
                        "prompt": message,
                        "target": {
                            "type": "project",
                            "projectId": project_id,
                            "environment": {"type": "local"},
                        },
                    },
                )
                thread_id = str(created.get("threadId") or "")
                if not thread_id:
                    raise RuntimeError("Codex Desktop 未返回新任务编号")
                report(
                    port,
                    session_id,
                    "native-created",
                    json.dumps({"threadId": thread_id, "projectId": project_id}, ensure_ascii=False),
                )
                return 0
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
        raise RuntimeError(last_error or "Codex Desktop 原生任务创建失败")
    except (OSError, RuntimeError) as exc:
        report(port, session_id, "failed", str(exc))
        return 1


def resume_visible_task(session_id: str, thread_id: str, title: str, prompt_file: str, port: int, *, project_root: str) -> int:
    """Resume the original visible task, then fall back to a recovery task.

    The fallback deliberately uses the same persisted prompt/checkpoint rather
    than recreating a free-form request.  It therefore cannot skip the visual
    audit gate even if the original Codex turn disappeared.
    """
    prompt = Path(prompt_file).read_text(encoding="utf-8").strip()
    if not prompt:
        raise RuntimeError("恢复提示词为空")
    report(port, session_id, "resuming", "正在读取工作包检查点并续接原 Codex 任务。")
    last_error = ""
    if thread_id:
        try:
            parent_thread_id = _desktop_anchor_thread(str(Path(project_root).resolve()))
            for pipe_path in _native_pipe_candidates():
                try:
                    _native_tool_call(
                        pipe_path,
                        "send_message_to_thread",
                        parent_thread_id,
                        {"threadId": thread_id, "prompt": prompt},
                    )
                    report(port, session_id, "resumed", "原 Codex 任务已收到从当前检查点继续的恢复指令。")
                    return 0
                except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                    last_error = str(exc)
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
    report(port, session_id, "resume-failed", last_error or "原 Codex 任务不可恢复，改建独立恢复任务。")
    # create_visible_task reports the verified new thread id back to the
    # workbench; the recovery prompt contains the full state/anchor contract.
    return create_visible_task(session_id, f"{title}｜自动恢复", prompt_file, port, project_root=project_root)


def create_auxiliary_skill_repair(title: str, prompt_file: str, *, project_root: str) -> str:
    """Create a separately visible repair task without replacing the main task id."""
    prompt = Path(prompt_file).read_text(encoding="utf-8").strip()
    if not prompt:
        raise RuntimeError("Skill 修复提示词为空")
    root = str(Path(project_root).resolve())
    parent_thread_id = _desktop_anchor_thread(root)
    last_error = ""
    for pipe_path in _native_pipe_candidates():
        try:
            project_id = _desktop_project_id(pipe_path, parent_thread_id, root)
            created = _native_tool_call(
                pipe_path,
                "create_thread",
                parent_thread_id,
                {"title": f"配图 Skill 修复｜{title}", "prompt": prompt, "target": {"type": "project", "projectId": project_id, "environment": {"type": "local"}}},
            )
            task_id = str(created.get("threadId") or "")
            if task_id:
                return task_id
            raise RuntimeError("Codex Desktop 未返回 Skill 修复任务编号")
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "无法创建独立 Skill 修复任务")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI爆款内容工厂 Codex 桌面桥接")
    parser.add_argument("--session", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--dry-run", action="store_true", help="只验证 Codex 窗口可定位，不创建任务")
    args = parser.parse_args()
    return create_visible_task(args.session, args.title, args.prompt_file, args.port, project_root=args.project_root, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
