# test_guard.py
"""
Air Point Test-Wide Execution Guard.
Ensures zero real Windows OS actions (mouse move, click, keyboard, lock, app launch)
and zero live camera hardware opens during testing.
Raises BlockedOSActionError if any protected native API is called.
"""

import sys
import os
import subprocess
import ctypes
from typing import Any

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pynput
except ImportError:
    pynput = None


class BlockedOSActionError(RuntimeError):
    """Raised when a test attempts to execute an unmocked OS action or open a live camera."""
    pass


_GUARD_INSTALLED = False
_ORIGINAL_APIS: dict[str, Any] = {}


def _blocked_send_input(*args, **kwargs):
    raise BlockedOSActionError("Blocked ctypes user32.SendInput call during test execution!")


def _blocked_set_cursor_pos(*args, **kwargs):
    raise BlockedOSActionError("Blocked ctypes user32.SetCursorPos call during test execution!")


def _blocked_mouse_event(*args, **kwargs):
    raise BlockedOSActionError("Blocked ctypes user32.mouse_event call during test execution!")


def _blocked_keybd_event(*args, **kwargs):
    raise BlockedOSActionError("Blocked ctypes user32.keybd_event call during test execution!")


def _blocked_lock_workstation(*args, **kwargs):
    raise BlockedOSActionError("Blocked ctypes user32.LockWorkStation call during test execution!")


def _blocked_startfile(*args, **kwargs):
    raise BlockedOSActionError(f"Blocked os.startfile({args}) call during test execution!")


class _BlockedPopen(subprocess.Popen):
    def __init__(self, cmd, *args, **kwargs):
        cmd_str = str(cmd).strip().lower()
        # Allow internal standard library OS version probe ('ver') from platform.py
        if cmd == "ver" or cmd_str == "ver":
            orig = _ORIGINAL_APIS.get("subprocess_Popen")
            if orig is not None:
                orig.__init__(self, cmd, *args, **kwargs)
                return
        raise BlockedOSActionError(f"Blocked subprocess launch ({cmd_str}) during test execution!")


class _BlockedMouseController:
    def __init__(self, *args, **kwargs):
        raise BlockedOSActionError("Blocked pynput.mouse.Controller instantiation during test execution!")


class _BlockedKeyboardController:
    def __init__(self, *args, **kwargs):
        raise BlockedOSActionError("Blocked pynput.keyboard.Controller instantiation during test execution!")


def _guarded_video_capture(*args, **kwargs):
    if args:
        target = args[0]
        if isinstance(target, int):
            raise BlockedOSActionError(f"Blocked live camera open (device index {target}) during test execution!")
    orig = _ORIGINAL_APIS.get("cv2_VideoCapture")
    if orig:
        return orig(*args, **kwargs)
    raise BlockedOSActionError("cv2.VideoCapture original not found!")


_SIMULATED_CURSOR_POS: tuple[int, int] | None = (960, 540)
_SIMULATED_CURSOR_QUERY_RESULT: int = 1


def set_simulated_cursor_pos(pos: tuple[int, int] | None) -> None:
    """Explicitly set simulated desktop cursor coordinates for testing."""
    global _SIMULATED_CURSOR_POS
    _SIMULATED_CURSOR_POS = pos


def set_simulated_cursor_query_result(result: int) -> None:
    """Explicitly set GetCursorPos query result (1 = success, 0 = failure)."""
    global _SIMULATED_CURSOR_QUERY_RESULT
    _SIMULATED_CURSOR_QUERY_RESULT = 1 if result != 0 else 0


def reset_test_guard_cursor_state() -> None:
    """Reset simulated cursor state to default (960, 540) and success."""
    global _SIMULATED_CURSOR_POS, _SIMULATED_CURSOR_QUERY_RESULT
    _SIMULATED_CURSOR_POS = (960, 540)
    _SIMULATED_CURSOR_QUERY_RESULT = 1


def _guarded_get_cursor_pos(pt_ref: Any) -> int:
    """
    Deterministic guarded implementation of user32.GetCursorPos.
    Prevents tests from querying the real Windows desktop cursor while providing
    deterministic coordinates for tests that do not mock actuator.get_cursor_pos.
    """
    global _SIMULATED_CURSOR_QUERY_RESULT, _SIMULATED_CURSOR_POS
    if _SIMULATED_CURSOR_QUERY_RESULT == 0 or _SIMULATED_CURSOR_POS is None:
        return 0

    x, y = _SIMULATED_CURSOR_POS
    if hasattr(pt_ref, "_obj"):
        pt_ref._obj.x = int(x)
        pt_ref._obj.y = int(y)
    elif hasattr(pt_ref, "contents"):
        pt_ref.contents.x = int(x)
        pt_ref.contents.y = int(y)
    return 1


def install_test_guard() -> None:
    """Installs patches preventing real OS input and live camera access."""
    global _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return

    # 1. Patch ctypes user32 on Windows
    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
        u32 = ctypes.windll.user32
        _ORIGINAL_APIS["user32_SendInput"] = getattr(u32, "SendInput", None)
        _ORIGINAL_APIS["user32_SetCursorPos"] = getattr(u32, "SetCursorPos", None)
        _ORIGINAL_APIS["user32_mouse_event"] = getattr(u32, "mouse_event", None)
        _ORIGINAL_APIS["user32_keybd_event"] = getattr(u32, "keybd_event", None)
        _ORIGINAL_APIS["user32_LockWorkStation"] = getattr(u32, "LockWorkStation", None)
        _ORIGINAL_APIS["user32_GetCursorPos"] = getattr(u32, "GetCursorPos", None)

        u32.SendInput = _blocked_send_input
        u32.SetCursorPos = _blocked_set_cursor_pos
        u32.mouse_event = _blocked_mouse_event
        u32.keybd_event = _blocked_keybd_event
        u32.LockWorkStation = _blocked_lock_workstation
        u32.GetCursorPos = _guarded_get_cursor_pos

    # Also patch WinDLL("user32") if cached or loaded
    orig_windll = ctypes.WinDLL

    def _guarded_windll(name, *args, **kwargs):
        lib = orig_windll(name, *args, **kwargs)
        if "user32" in str(name).lower():
            lib.SendInput = _blocked_send_input
            lib.SetCursorPos = _blocked_set_cursor_pos
            lib.mouse_event = _blocked_mouse_event
            lib.keybd_event = _blocked_keybd_event
            lib.LockWorkStation = _blocked_lock_workstation
            lib.GetCursorPos = _guarded_get_cursor_pos
        return lib

    _ORIGINAL_APIS["WinDLL"] = orig_windll
    ctypes.WinDLL = _guarded_windll

    # 2. Patch pynput controllers
    if pynput is not None:
        if hasattr(pynput, "mouse"):
            _ORIGINAL_APIS["pynput_mouse_Controller"] = pynput.mouse.Controller
            pynput.mouse.Controller = _BlockedMouseController
        if hasattr(pynput, "keyboard"):
            _ORIGINAL_APIS["pynput_keyboard_Controller"] = pynput.keyboard.Controller
            pynput.keyboard.Controller = _BlockedKeyboardController

    # 3. Patch os.startfile
    if hasattr(os, "startfile"):
        _ORIGINAL_APIS["os_startfile"] = os.startfile
        os.startfile = _blocked_startfile

    # 4. Patch subprocess.Popen
    _ORIGINAL_APIS["subprocess_Popen"] = subprocess.Popen
    subprocess.Popen = _BlockedPopen

    # 5. Patch cv2.VideoCapture (block integer camera index, allow string file paths)
    if cv2 is not None:
        _ORIGINAL_APIS["cv2_VideoCapture"] = cv2.VideoCapture
        cv2.VideoCapture = _guarded_video_capture

    _GUARD_INSTALLED = True


def uninstall_test_guard() -> None:
    """Restores original APIs (for cleanup if needed)."""
    global _GUARD_INSTALLED
    if not _GUARD_INSTALLED:
        return

    if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
        u32 = ctypes.windll.user32
        for api_name in ("SendInput", "SetCursorPos", "mouse_event", "keybd_event", "LockWorkStation", "GetCursorPos"):
            orig = _ORIGINAL_APIS.get(f"user32_{api_name}")
            if orig is not None:
                setattr(u32, api_name, orig)

    if "WinDLL" in _ORIGINAL_APIS:
        ctypes.WinDLL = _ORIGINAL_APIS["WinDLL"]

    if pynput is not None:
        if "pynput_mouse_Controller" in _ORIGINAL_APIS:
            pynput.mouse.Controller = _ORIGINAL_APIS["pynput_mouse_Controller"]
        if "pynput_keyboard_Controller" in _ORIGINAL_APIS:
            pynput.keyboard.Controller = _ORIGINAL_APIS["pynput_keyboard_Controller"]

    if "os_startfile" in _ORIGINAL_APIS:
        os.startfile = _ORIGINAL_APIS["os_startfile"]

    if "subprocess_Popen" in _ORIGINAL_APIS:
        subprocess.Popen = _ORIGINAL_APIS["subprocess_Popen"]

    if cv2 is not None and "cv2_VideoCapture" in _ORIGINAL_APIS:
        cv2.VideoCapture = _ORIGINAL_APIS["cv2_VideoCapture"]

    _GUARD_INSTALLED = False
