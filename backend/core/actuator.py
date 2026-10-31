# core/actuator.py
"""
Windows mouse actuation via SendInput.

Why SendInput over mouse_event:
- mouse_event is deprecated since Windows Vista; routes through a compatibility shim
- SendInput is the documented, low-overhead replacement
- MOUSEEVENTF_VIRTUALDESK + MOUSEEVENTF_ABSOLUTE correctly spans all monitors

Why SendInput over pynput for movement:
- pynput wraps SendInput anyway; calling ctypes directly removes one layer
- pynput is used here only for click/drag state because its press/release
  abstraction is cleaner than manually managing button flags in INPUT structs

Coordinate system for MOUSEEVENTF_ABSOLUTE:
- The virtual desktop is mapped to a normalized space of [0, 65535] x [0, 65535]
- Physical pixel (x, y) -> norm = (x * 65535 / total_w, y * 65535 / total_h)
- MOUSEEVENTF_VIRTUALDESK flag makes (65535, 65535) = bottom-right of ALL monitors
  Without this flag, (65535, 65535) = bottom-right of the PRIMARY monitor only
"""

import ctypes
from ctypes import wintypes
import logging
import math
import os
import time
from enum import Enum, auto
from PIL import ImageGrab

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Controller as KeyboardController, Key

logger = logging.getLogger(__name__)

if os.environ.get("AIRPOINT_ENABLE_TEST_GUARD", "").strip().lower() in ("1", "true", "yes"):
    try:
        from test_guard import install_test_guard
        install_test_guard()
    except Exception:
        pass

_user32 = ctypes.WinDLL("user32", use_last_error=True)

# ── SendInput ctypes structures ───────────────────────────────────────────────

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx",          ctypes.c_long),
        ("dy",          ctypes.c_long),
        ("mouseData",   ctypes.c_ulong),
        ("dwFlags",     ctypes.c_ulong),
        ("time",        ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("_u",)
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("_u",   _INPUT_UNION),
    ]


INPUT_MOUSE              = 0
MOUSEEVENTF_MOVE         = 0x0001
MOUSEEVENTF_ABSOLUTE     = 0x8000
MOUSEEVENTF_VIRTUALDESK  = 0x4000   # Interpret absolute coords as virtual desktop coords


MOUSEEVENTF_LEFTDOWN     = 0x0002
MOUSEEVENTF_LEFTUP       = 0x0004
MOUSEEVENTF_RIGHTDOWN    = 0x0008
MOUSEEVENTF_RIGHTUP      = 0x0010


class DragStartResult(Enum):
    """
    Explicit, unambiguous lifecycle result for MouseActuator.drag_start().
    """
    STARTED = "STARTED"
    ALREADY_ACTIVE = "ALREADY_ACTIVE"
    FAILED = "FAILED"

    def __bool__(self) -> bool:
        return self is not DragStartResult.FAILED

    def __eq__(self, other):
        if isinstance(other, bool):
            return bool(self) == other
        return super().__eq__(other)


class DragEndResult(Enum):
    """
    Explicit, unambiguous lifecycle result for MouseActuator.drag_end().
    """
    RELEASED = "RELEASED"
    NOT_DRAGGING = "NOT_DRAGGING"
    FAILED = "FAILED"

    def __bool__(self) -> bool:
        return self is DragEndResult.RELEASED

    def __eq__(self, other):
        if isinstance(other, bool):
            return bool(self) == other
        return super().__eq__(other)


def _send_input(inp: INPUT) -> bool:
    if _user32 is None:
        logger.warning("SendInput unavailable: user32 is None")
        return False
    try:
        result = _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        if result == 0:
            err = ctypes.get_last_error()
            # If SendInput returned 0 (UIPI or isolation block), attempt mouse_event fallback
            try:
                if hasattr(_user32, "mouse_event"):
                    _user32.mouse_event(inp.mi.dwFlags, inp.mi.dx, inp.mi.dy, inp.mi.mouseData, inp.mi.dwExtraInfo)
                    logger.debug("SendInput returned 0 (err=%d); dispatched via mouse_event fallback", err)
                    return True
            except Exception as me_err:
                logger.warning("mouse_event fallback failed: %s", me_err)
            logger.warning("SendInput returned 0 (UIPI block or invalid input?). GetLastError=%d", err)
            return False
        return True
    except Exception as e:
        logger.error("Exception during _send_input: %s", e)
        return False


# ── Public Actuator ───────────────────────────────────────────────────────────

class MouseActuator:
    """
    Handles all mouse movement and click state.

    Args:
        total_width:  Physical pixel width of the full virtual desktop
        total_height: Physical pixel height of the full virtual desktop
    """

    def __init__(
        self,
        total_width: int,
        total_height: int,
        origin_x: int | None = None,
        origin_y: int | None = None,
    ) -> None:
        try:
            _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            pass
        self._total_w = total_width
        self._total_h = total_height

        # Virtual desktop origin offset (SM_XVIRTUALSCREEN / SM_YVIRTUALSCREEN)
        if origin_x is not None and origin_y is not None:
            self._origin_x = int(origin_x)
            self._origin_y = int(origin_y)
        elif _user32 is not None:
            try:
                self._origin_x = int(_user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
                self._origin_y = int(_user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
            except Exception:
                self._origin_x = 0
                self._origin_y = 0
        else:
            self._origin_x = 0
            self._origin_y = 0

        self._pynput = None
        try:
            self._pynput = MouseController()
        except Exception:
            pass
        self._dragging = False
        self._last_drag_time: float = 0.0
        self._last_send_input_result: bool | None = None
        self._last_drag_error: str | None = None
        self._keyboard = None
        try:
            self._keyboard = KeyboardController()
        except Exception:
            pass

        logger.info("MouseActuator ready (%dx%d desktop, origin=(%d,%d))", total_width, total_height, self._origin_x, self._origin_y)

    def get_cursor_pos(self) -> tuple[int, int] | None:
        """
        Query current Windows desktop cursor position in physical pixels relative to
        Air Point's virtual desktop space [0, total_w - 1] x [0, total_h - 1].

        Returns:
            (x, y) coordinates mapped to virtual desktop space, or None if retrieval fails
            or if desktop dimensions are missing/invalid.
        """
        total_w = getattr(self, "_total_w", None)
        total_h = getattr(self, "_total_h", None)
        if (
            not isinstance(total_w, (int, float))
            or not isinstance(total_h, (int, float))
            or total_w <= 0
            or total_h <= 0
        ):
            return None

        if _user32 is None:
            return None
        try:
            pt = wintypes.POINT()
            ok = _user32.GetCursorPos(ctypes.byref(pt))
            if not ok:
                err = ctypes.get_last_error()
                logger.warning("GetCursorPos returned 0 (error=%d)", err)
                return None

            origin_x = getattr(self, "_origin_x", 0)
            origin_y = getattr(self, "_origin_y", 0)
            if not isinstance(origin_x, (int, float)):
                origin_x = 0
            if not isinstance(origin_y, (int, float)):
                origin_y = 0

            # Convert Windows virtual coordinates to Air Point virtual desktop space:
            vx = int(pt.x) - int(origin_x)
            vy = int(pt.y) - int(origin_y)

            # Clamp to virtual desktop bounding box
            vx = max(0, min(int(total_w) - 1, vx))
            vy = max(0, min(int(total_h) - 1, vy))
            return (vx, vy)
        except Exception as e:
            logger.warning("get_cursor_pos failed: %s", e)
            return None

    @staticmethod
    def verify_physical_displacement(
        p_pre: tuple[int, int] | None,
        p_post: tuple[int, int] | None,
        dispatched_pos: tuple[int, int],
        max_physical_disp: float = 50.0,
        disp_tolerance: float = 2.0,
        target_tolerance: float = 2.0,
    ) -> tuple[bool, float | None, float | None, str | None]:
        """
        Verifies physical cursor displacement between independently queried positions.

        Args:
            p_pre: Physical (x, y) cursor position immediately before movement.
            p_post: Physical (x, y) cursor position immediately after movement.
            dispatched_pos: The target (x, y) coordinates dispatched to the OS.
            max_physical_disp: Maximum permissible physical displacement (default: 50.0px).
            disp_tolerance: Permissible integer rounding / quantization slack between pre and post
                            positions (default: 2.0px). Accounts for 16-bit SendInput mapping
                            quantization (+-1px per axis).
            target_tolerance: Permissible discrepancy between dispatched target and physical post
                              position (default: 2.0px). Accounts for coordinate snapping and
                              multi-monitor desktop origin offsets.

        Returns:
            (verified, phys_displacement_px, target_error_px, failure_reason)
        """
        if p_pre is None:
            return False, None, None, "PRE_QUERY_FAILED: Physical cursor position could not be queried before movement."
        if p_post is None:
            return False, None, None, "POST_QUERY_FAILED: Physical cursor position could not be queried after movement."

        phys_disp = math.hypot(p_post[0] - p_pre[0], p_post[1] - p_pre[1])
        target_err = math.hypot(p_post[0] - dispatched_pos[0], p_post[1] - dispatched_pos[1])

        max_allowed_disp = max_physical_disp + disp_tolerance
        if phys_disp > max_allowed_disp + 1e-6:
            reason = (
                f"PHYSICAL_DISPLACEMENT_EXCEEDED: Actual displacement {phys_disp:.2f}px "
                f"exceeds limit {max_allowed_disp:.2f}px (base={max_physical_disp}px, tol={disp_tolerance}px)."
            )
            return False, phys_disp, target_err, reason

        if target_err > target_tolerance + 1e-6:
            reason = (
                f"TARGET_DISAGREEMENT_EXCEEDED: Physical result {p_post} differs from target {dispatched_pos} "
                f"by {target_err:.2f}px (tolerance={target_tolerance}px)."
            )
            return False, phys_disp, target_err, reason

        return True, phys_disp, target_err, None

    def move(self, x: int, y: int) -> bool:
        """
        Move cursor to absolute desktop coordinates (physical pixels).
        Maps to SendInput's [0, 65535] normalized space.
        """
        norm_x = int(x * 65535 / max(self._total_w - 1, 1))
        norm_y = int(y * 65535 / max(self._total_h - 1, 1))

        # Clamp to valid range
        norm_x = max(0, min(65535, norm_x))
        norm_y = max(0, min(65535, norm_y))

        inp = INPUT(
            type=INPUT_MOUSE,
            mi=MOUSEINPUT(
                dx=norm_x,
                dy=norm_y,
                mouseData=0,
                dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                time=0,
                dwExtraInfo=0,
            ),
        )
        return _send_input(inp)

    def _send_mouse_flag(self, flag: int) -> bool:
        inp = INPUT(
            type=INPUT_MOUSE,
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=0,
                dwFlags=flag,
                time=0,
                dwExtraInfo=0,
            ),
        )
        return _send_input(inp)

    def left_click(self, x: int | None = None, y: int | None = None) -> bool:
        """
        Emit left click down + up.
        If x, y are provided, performs atomic position synchronisation and absolute
        coordinate click injection to prevent inter-frame spatial jitter from breaking
        Windows double-click recognition (SM_CXDOUBLECLK tolerance = 4px).
        """
        logger.debug("OS left_click executing via SendInput (coords=%s)", (x, y) if x is not None else "current")
        if x is not None and y is not None:
            try:
                _user32.SetCursorPos(int(x), int(y))
            except Exception:
                pass
            norm_x = int(x * 65535 / max(self._total_w - 1, 1))
            norm_y = int(y * 65535 / max(self._total_h - 1, 1))
            norm_x = max(0, min(65535, norm_x))
            norm_y = max(0, min(65535, norm_y))
            flags_base = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
            down_inp = INPUT(
                type=INPUT_MOUSE,
                mi=MOUSEINPUT(
                    dx=norm_x,
                    dy=norm_y,
                    mouseData=0,
                    dwFlags=flags_base | MOUSEEVENTF_LEFTDOWN,
                    time=0,
                    dwExtraInfo=0,
                ),
            )
            up_inp = INPUT(
                type=INPUT_MOUSE,
                mi=MOUSEINPUT(
                    dx=norm_x,
                    dy=norm_y,
                    mouseData=0,
                    dwFlags=flags_base | MOUSEEVENTF_LEFTUP,
                    time=0,
                    dwExtraInfo=0,
                ),
            )
            ok_down = _send_input(down_inp)
            time.sleep(0.005)
            ok_up = _send_input(up_inp)
            return ok_down and ok_up
        else:
            ok_down = self._send_mouse_flag(MOUSEEVENTF_LEFTDOWN)
            time.sleep(0.005)
            ok_up = self._send_mouse_flag(MOUSEEVENTF_LEFTUP)
            return ok_down and ok_up

    def right_click(self) -> None:
        self._send_mouse_flag(MOUSEEVENTF_RIGHTDOWN)
        self._send_mouse_flag(MOUSEEVENTF_RIGHTUP)

    def drag_start(self, now: float | None = None) -> DragStartResult:
        """
        Begins dragging by depressing the left mouse button if not already dragging.

        Returns:
            DragStartResult.STARTED: native button-down successfully injected.
            DragStartResult.ALREADY_ACTIVE: drag is already active; keep-alive updated.
            DragStartResult.FAILED: native button-down injection failed.
        """
        if self.is_dragging:
            self._last_drag_time = now if now is not None else time.perf_counter()
            logger.debug("Drag already active; keep-alive updated")
            return DragStartResult.ALREADY_ACTIVE

        ok = self._send_mouse_flag(MOUSEEVENTF_LEFTDOWN)
        self._last_send_input_result = ok
        if not ok:
            logger.error("Failed to inject native MOUSEEVENTF_LEFTDOWN for drag")
            self._dragging = False
            if hasattr(self, '_is_dragging'):
                self._is_dragging = False
            self._last_drag_error = "SENDINPUT_LEFTDOWN_FAILED"
            return DragStartResult.FAILED

        self._dragging = True
        if hasattr(self, '_is_dragging'):
            self._is_dragging = True
        self._last_drag_time = now if now is not None else time.perf_counter()
        self._last_drag_error = None
        logger.info("Drag started successfully (native MOUSEEVENTF_LEFTDOWN confirmed)")
        return DragStartResult.STARTED

    def keep_drag_alive(self, now: float | None = None) -> None:
        """Updates the monotonic timestamp of the active drag session."""
        if self.is_dragging:
            self._last_drag_time = now if now is not None else time.perf_counter()

    def drag_end(self) -> DragEndResult:
        """
        Ends dragging by releasing the left mouse button if currently held.
        Idempotent: safe to call repeatedly without emitting phantom clicks.

        Returns:
            DragEndResult.RELEASED: drag was active and native button-up was successfully injected.
            DragEndResult.NOT_DRAGGING: drag was not active (idempotent no-op).
            DragEndResult.FAILED: native button-up injection failed.
        """
        if not self.is_dragging:
            return DragEndResult.NOT_DRAGGING

        ok = self._send_mouse_flag(MOUSEEVENTF_LEFTUP)
        self._last_send_input_result = ok
        if not ok:
            logger.error("Failed to inject native MOUSEEVENTF_LEFTUP for drag release; retrying once safely")
            time.sleep(0.005)
            ok = self._send_mouse_flag(MOUSEEVENTF_LEFTUP)
            self._last_send_input_result = ok

        if not ok:
            logger.critical(
                "Native button-up injection failed after retry. Left mouse button state is uncertain; "
                "retaining is_dragging=True for watchdog/cleanup retry."
            )
            self._last_drag_error = "SENDINPUT_LEFTUP_FAILED"
            return DragEndResult.FAILED

        self._dragging = False
        if hasattr(self, '_is_dragging'):
            self._is_dragging = False
        self._last_drag_time = 0.0
        self._last_drag_error = None
        logger.info("Drag ended successfully (native MOUSEEVENTF_LEFTUP confirmed)")
        return DragEndResult.RELEASED

    def check_drag_watchdog(self, now: float | None = None, timeout_s: float = 0.25) -> bool:
        """
        Failsafe watchdog: releases held left button if drag has been active
        without keep-alive touch for longer than timeout_s.
        Returns True if watchdog triggered drag_end, False otherwise.
        """
        if not self.is_dragging:
            return False
        if now is None:
            now = time.perf_counter()
        last_t = getattr(self, '_last_drag_time', 0.0)
        if last_t > 0.0 and (now - last_t) > timeout_s:
            logger.warning(
                "Drag safety watchdog triggered: left button held for %.3fs without touch (> %.3fs) — releasing",
                now - last_t,
                timeout_s,
            )
            res = self.drag_end()
            return bool(res)
        return False


    def get_native_left_button_state(self) -> str:
        """Query native Windows left mouse button state: DOWN / UP / UNKNOWN."""
        if _user32 is not None and hasattr(_user32, "GetAsyncKeyState"):
            try:
                # 0x01 = VK_LBUTTON
                state = _user32.GetAsyncKeyState(0x01)
                if state & 0x8000:
                    return "DOWN"
                return "UP"
            except Exception:
                pass
        return "UNKNOWN"
    def scroll(self, ticks: int) -> None:
        """
        Scroll vertically. Positive ticks = scroll up, negative = scroll down.
        """
        self._pynput.scroll(0, ticks)

    def double_click(self, x: int | None = None, y: int | None = None) -> bool:
        logger.debug("OS double_click executing via SendInput (coords=%s)", (x, y) if x is not None else "current")
        ok1 = self.left_click(x, y)
        time.sleep(0.05)
        ok2 = self.left_click(x, y)
        return ok1 and ok2

    def win_d(self) -> None:
        with self._keyboard.pressed(Key.cmd):
            self._keyboard.press('d')
            self._keyboard.release('d')

    def alt_tab(self) -> None:
        with self._keyboard.pressed(Key.alt):
            self._keyboard.press(Key.tab)
            self._keyboard.release(Key.tab)

    def win_tab(self) -> None:
        with self._keyboard.pressed(Key.cmd):
            self._keyboard.press(Key.tab)
            self._keyboard.release(Key.tab)

    def win_key(self) -> None:
        self._keyboard.press(Key.cmd)
        self._keyboard.release(Key.cmd)

    def alt_left(self) -> None:
        with self._keyboard.pressed(Key.alt):
            self._keyboard.press(Key.left)
            self._keyboard.release(Key.left)

    def win_l(self) -> None:
        with self._keyboard.pressed(Key.cmd):
            self._keyboard.press('l')
            self._keyboard.release('l')

    def win_snap_left(self) -> None:
        with self._keyboard.pressed(Key.cmd):
            self._keyboard.press(Key.left)
            self._keyboard.release(Key.left)

    def win_snap_right(self) -> None:
        with self._keyboard.pressed(Key.cmd):
            self._keyboard.press(Key.right)
            self._keyboard.release(Key.right)

    def ctrl_down(self) -> None:
        self._keyboard.press(Key.ctrl)

    def ctrl_up(self) -> None:
        self._keyboard.release(Key.ctrl)

    def zoom_in(self) -> None:
        with self._keyboard.pressed(Key.ctrl):
            self._keyboard.press('=')
            self._keyboard.release('=')

    def zoom_out(self) -> None:
        with self._keyboard.pressed(Key.ctrl):
            self._keyboard.press('-')
            self._keyboard.release('-')

    def mag_zoom_in(self) -> None:
        with self._keyboard.pressed(Key.cmd):
            self._keyboard.press('=')
            self._keyboard.release('=')

    def mag_zoom_out(self) -> None:
        with self._keyboard.pressed(Key.cmd):
            self._keyboard.press('-')
            self._keyboard.release('-')

    def take_screenshot(self, directory: str, pre_capture_cb=None, post_capture_cb=None) -> str | None:
        try:
            if not os.path.exists(directory):
                os.makedirs(directory)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(directory, f"screenshot_{timestamp}.png")
            
            if pre_capture_cb:
                pre_capture_cb()
                
            img = ImageGrab.grab(all_screens=True)
            
            if post_capture_cb:
                post_capture_cb()
                
            img.save(filename)
            logger.info("Screenshot saved to %s", filename)
            return filename
        except Exception as e:
            if post_capture_cb:
                post_capture_cb()
            logger.error("Screenshot failed: %s", e)
            return None

    @property
    def is_dragging(self) -> bool:
        return bool(getattr(self, '_dragging', False) or getattr(self, '_is_dragging', False))
