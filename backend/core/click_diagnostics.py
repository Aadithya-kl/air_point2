# core/click_diagnostics.py
"""
Diagnostic tracer for right-hand pinch clicking and double-clicking.
Provides detailed, millisecond-precision inspection of real Windows input injection,
spatial tolerances, and state-machine transitions.
"""

import time
import logging
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field

logger = logging.getLogger("airmouse.click_diag")

@dataclass
class ClickRecord:
    click_index: int  # 1 or 2
    timestamp: float
    target_pos: tuple[int, int]
    actual_win_pos: tuple[int, int]
    submitted_ok: bool
    dt_from_prev_ms: float = 0.0
    dist_from_prev_px: float = 0.0

class ClickDiagnosticTracer:
    """
    Lightweight, high-precision tracer for click events and state machine transitions.
    Disabled by default in production, can be toggled via config or environment.
    """
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._user32 = getattr(ctypes.windll, "user32", None) if hasattr(ctypes, "windll") else None
        self.history: list[ClickRecord] = []
        self._active_gesture_clicks = 0
        self._gesture_start_time: float | None = None

    def get_actual_cursor_pos(self) -> tuple[int, int]:
        """Query real Windows desktop cursor position via Win32 GetCursorPos."""
        if not self._user32:
            return (0, 0)
        try:
            pt = wintypes.POINT()
            self._user32.GetCursorPos(ctypes.byref(pt))
            return (int(pt.x), int(pt.y))
        except Exception:
            return (0, 0)

    def get_windows_metrics(self) -> tuple[int, int, int]:
        """Returns (double_click_time_ms, sm_cxdoubleclk, sm_cydoubleclk)."""
        if not self._user32:
            return (500, 4, 4)
        try:
            dbt = self._user32.GetDoubleClickTime()
            cx = self._user32.GetSystemMetrics(36)  # SM_CXDOUBLECLK
            cy = self._user32.GetSystemMetrics(37)  # SM_CYDOUBLECLK
            return (int(dbt), int(cx), int(cy))
        except Exception:
            return (500, 4, 4)

    def log_state_transition(
        self,
        old_state: str,
        new_state: str,
        reason: str,
        pinch_norm: float,
        threshold: float,
        target_pos: tuple[int, int] | None = None,
        is_anchored: bool = False,
    ) -> None:
        if not self.enabled:
            return
        now = time.perf_counter()
        actual_pos = self.get_actual_cursor_pos()
        logger.info(
            "[CLICK_TRACE] STATE: %s -> %s | Reason: %s | DistNorm: %.3f (Thresh: %.3f) | "
            "Target: %s | ActualWin: %s | Anchored: %s | t=%.4f",
            old_state, new_state, reason, pinch_norm, threshold,
            f"({target_pos[0]}, {target_pos[1]})" if target_pos else "None",
            f"({actual_pos[0]}, {actual_pos[1]})",
            is_anchored, now
        )

    def record_click(
        self,
        click_num: int,
        target_pos: tuple[int, int],
        submitted_ok: bool,
    ) -> ClickRecord:
        now = time.perf_counter()
        actual_pos = self.get_actual_cursor_pos()
        dt_ms = 0.0
        dist_px = 0.0

        if click_num == 2 and len(self.history) > 0:
            prev = self.history[-1]
            dt_ms = (now - prev.timestamp) * 1000.0
            dx = float(actual_pos[0] - prev.actual_win_pos[0])
            dy = float(actual_pos[1] - prev.actual_win_pos[1])
            dist_px = (dx**2 + dy**2)**0.5

        rec = ClickRecord(
            click_index=click_num,
            timestamp=now,
            target_pos=target_pos,
            actual_win_pos=actual_pos,
            submitted_ok=submitted_ok,
            dt_from_prev_ms=dt_ms,
            dist_from_prev_px=dist_px,
        )
        self.history.append(rec)
        self._active_gesture_clicks = click_num

        if self.enabled:
            dbt, cx, cy = self.get_windows_metrics()
            if click_num == 1:
                logger.info(
                    "[CLICK_TRACE] >>> NATIVE CLICK #1 EMITTED <<< | Target: (%d, %d) | "
                    "ActualWinCursor: (%d, %d) | Submitted: %s | t=%.4f",
                    target_pos[0], target_pos[1], actual_pos[0], actual_pos[1], submitted_ok, now
                )
            elif click_num == 2:
                in_time = dt_ms <= float(dbt)
                in_box = dist_px <= float(cx)
                logger.info(
                    "[CLICK_TRACE] >>> NATIVE CLICK #2 EMITTED (DOUBLE-CLICK) <<< | Target: (%d, %d) | "
                    "ActualWinCursor: (%d, %d) | DistFromClick1: %.1fpx (WinLimit: %dpx -> %s) | "
                    "DeltaT: %.1fms (WinLimit: %dms -> %s) | Submitted: %s | t=%.4f",
                    target_pos[0], target_pos[1], actual_pos[0], actual_pos[1],
                    dist_px, cx, "PASS" if in_box else "FAIL",
                    dt_ms, dbt, "PASS" if in_time else "FAIL",
                    submitted_ok, now
                )

        return rec

    def reset(self) -> None:
        self.history.clear()
        self._active_gesture_clicks = 0
        self._gesture_start_time = None

# Global diagnostic tracer instance
click_tracer = ClickDiagnosticTracer(enabled=True)
