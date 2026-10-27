# core/overlay.py
"""
Air Point Phase 7: Dynamic Island-Style Gesture Feedback HUD & Runtime Status.
Renders smooth, non-blocking on-screen feedback capsules for:
  - Volume Up / Down (with live percentage and progress border)
  - Audio Mute / Unmute (with distinct amber/emerald indicators)
  - Screenshot countdown, saved confirmation, and failure handling
  - WhatsApp desktop launch feedback
  - Hand lost and hand reacquired tracking state transitions
  - System paused and resumed status
  - Optional expanded runtime telemetry (Owner, Tracking, FPS, Status)
"""

import tkinter as tk
import ctypes
import time
import math
import logging
import queue
import threading
from typing import Callable, Any
from core.gestures.screenshot import ScreenshotState
from config import (
    SCREENSHOT_HOLD_DURATION_S,
    HUD_ENABLED,
    HUD_ANIMATION_SPEED,
    HUD_TOAST_DURATION_S,
    HUD_STATUS_DURATION_S,
)

logger = logging.getLogger(__name__)

# Event priority hierarchy (higher preempts lower; prevents overlapping flicker)
PRIORITY_CRITICAL = 40    # Screenshot, app launch, audio mute/unmute, pause
PRIORITY_VOLUME = 30      # Ear volume continuous adjustment
PRIORITY_TRACKING = 20    # Hand lost / reacquired
PRIORITY_STATUS = 10      # Runtime status inspect

# Modern Graphite & Sage Theme Palette
COLOR_GRAPHITE_BG = "#16171a"
COLOR_GRAPHITE_BORDER = "#27282e"
COLOR_GRAPHITE_SHADOW = "#0e0f11"
COLOR_TEXT_PRIMARY = "#ffffff"
COLOR_TEXT_SECONDARY = "#9ca3af"
COLOR_SAGE_ACCENT = "#8aa89b"
COLOR_AMBER_WARN = "#d49b56"
COLOR_ERROR_RED = "#d95d5d"
COLOR_APP_GREEN = "#25D366"

# Wakanda Forever Theme Palette
COLOR_WAKANDA_BG = "#0c0a11"
COLOR_WAKANDA_BORDER = "#7959a2"
COLOR_WAKANDA_BORDER_ARMED = "#9865d6"
COLOR_WAKANDA_PROGRESS = "#b983ff"
COLOR_WAKANDA_TEXT = "#f0e1ff"


def get_capsule_path(w: float, h: float, p: float) -> list[tuple]:
    """
    Computes SVG-like path segments along the perimeter of a rounded capsule of dimensions (w, h)
    for progress scalar p in [0.0, 1.0].
    """
    r = h / 2.0
    top_len = w - 2 * r
    arc_len = math.pi * r
    total_len = 2 * top_len + 2 * arc_len
    target = p * total_len

    segments = []
    current = 0.0

    l = top_len / 2.0
    if target > current:
        draw_len = min(l, target - current)
        segments.append(('line', w / 2, 0, w / 2 + draw_len, 0))
        current += l

    if target > current:
        draw_len = min(arc_len, target - current)
        extent = -(draw_len / arc_len) * 180
        segments.append(('arc', w - 2 * r, 0, w, h, 90, extent))
        current += arc_len

    if target > current:
        draw_len = min(top_len, target - current)
        segments.append(('line', w - r, h, w - r - draw_len, h))
        current += top_len

    if target > current:
        draw_len = min(arc_len, target - current)
        extent = -(draw_len / arc_len) * 180
        segments.append(('arc', 0, 0, 2 * r, h, 270, extent))
        current += arc_len

    if target > current:
        draw_len = min(l, target - current)
        segments.append(('line', r, 0, r + draw_len, 0))

    return segments


class ScreenshotOverlay:
    """
    Dynamic Island desktop HUD overlay.
    Provides non-blocking, transparent, click-through graphical feedback at top-center of desktop.
    """

    def __init__(self, position: str = "TOP_CENTER") -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.wm_attributes('-transparentcolor', '#000001')
        self.root.configure(bg='#000001')

        try:
            wid = self.root.winfo_id()
            if type(wid) is int and wid != 0:
                hwnd = ctypes.windll.user32.GetParent(wid)
                style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00080000 | 0x00000020)
        except Exception as e:
            logger.warning("Could not make overlay click-through: %s", e)

        self.w = 220
        self.h = 44
        self.target_w = 220
        self.target_h = 44
        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()

        self.pad_top = 16
        self.x = (self.sw - self.w) // 2
        self.y_hidden = -self.h - 10
        self.y_visible = self.pad_top

        self.current_y = float(self.y_hidden)
        self.root.geometry(f"{self.w}x{self.h}+{self.x}+{int(self.current_y)}")

        self.canvas = tk.Canvas(self.root, width=self.w, height=self.h, bg='#000001', highlightthickness=0)
        self.canvas.pack()

        self._is_hidden = True
        self.root.withdraw()

        self._last_ui_update = 0.0
        self._toast_until = 0.0
        self._island_state = "IDLE"  # IDLE, DROPPING, HOLDING, SUCCESS, ERROR, STATUS, RETRACTING
        self._island_text = "Hold still"
        self._island_subtext = ""
        self._island_icon = "CHECK"
        self._island_color = COLOR_SAGE_ACCENT
        self._progress = 0.0
        self._countdown_badge = ""

        # Phase 7.1 / 4.1 Dynamic Island Volume Visualizer state
        self._island_mode = ""  # "", "STANDARD", "STATUS", "VOLUME"
        self._volume_scalar = 0.50
        self._volume_muted = False
        self._is_volume_active = False
        self._volume_direction = "NONE"
        self._bar_heights = [2.5] * 7
        self._audio_controller = None

        self._current_priority = 0
        self._last_event_text = ""
        self._last_event_time = 0.0

        self._force_hide = False
        self._dispatch_queue: queue.Queue[Callable[[], None]] = queue.Queue()

        # Dynamic Island Configuration & Power State Notifications
        self.island_enabled: bool = True
        self.notifications_enabled: bool = True
        self.timer_enabled: bool = True
        self.autohide_enabled: bool = True
        self.hud_duration_s: float = 120.0
        self.completion_duration_s: float = 2.0
        self._ps_countdown_active: bool = False
        self._ps_start_time: float = 0.0
        self._ps_duration: float = 120.0
        self._ps_deadline: float = 0.0
        self._ps_token: object | None = None
        self._is_test_countdown: bool = False

        logger.info("Dynamic Island HUD initialized (w=%d, h=%d)", self.w, self.h)

    def _dispatch_to_main(self, action: Callable[[], None]) -> None:
        """
        Thread-safe UI dispatcher.
        If called from the main thread, executes immediately.
        If called from a background thread (e.g. HTTP server, pynput), queues action for main loop.
        """
        if threading.current_thread() is threading.main_thread():
            try:
                action()
            except Exception as e:
                logger.debug("Overlay action error on main thread: %s", e)
        else:
            self._dispatch_queue.put(action)

    @property
    def volume_scalar(self) -> float:
        return self._volume_scalar

    @property
    def volume_pct(self) -> int:
        return int(round(self._volume_scalar * 100.0))

    @property
    def displayed_volume_pct(self) -> str:
        return f"{self.volume_pct}%"

    @property
    def is_volume_active(self) -> bool:
        return self._is_volume_active

    @property
    def is_volume_muted(self) -> bool:
        return self._volume_muted

    @property
    def volume_direction(self) -> str:
        return self._volume_direction

    @property
    def sound_bars(self) -> list[float]:
        return getattr(self, '_bar_heights', self.get_sound_bar_heights(self._volume_scalar, self._volume_muted, self._is_volume_active))

    def set_audio_controller(self, audio_controller) -> None:
        self._audio_controller = audio_controller

    def _set_dimensions(self, w: int, h: int) -> None:
        self.target_w = w
        self.target_h = h

    def _reset_dimensions(self) -> None:
        self._island_mode = ""
        self._countdown_badge = ""
        self._set_dimensions(220, 44)

    def _animate_dimensions(self, speed: float = 0.28) -> None:
        """Smoothly interpolate width and height between states (e.g. 220px <-> 260px)."""
        dw = self.target_w - self.w
        dh = self.target_h - self.h
        changed = False

        if abs(dw) > 1:
            self.w += int(dw * speed)
            changed = True
        elif self.w != self.target_w:
            self.w = self.target_w
            changed = True

        if abs(dh) > 1:
            self.h += int(dh * speed)
            changed = True
        elif self.h != self.target_h:
            self.h = self.target_h
            changed = True

        if changed:
            self.x = (self.sw - self.w) // 2
            self.canvas.configure(width=self.w, height=self.h)
            self.root.geometry(f"{self.w}x{self.h}+{self.x}+{int(self.current_y)}")

    def hide(self) -> None:
        if not self._force_hide:
            self.root.withdraw()
            self.root.update()
            self._force_hide = True
            time.sleep(0.02)

    def show(self) -> None:
        if self._force_hide:
            if self._island_state != "IDLE":
                self.root.deiconify()
                self.root.lift()
            self.root.update()
            self._force_hide = False

    def _can_post_event(self, priority: int, text: str, now: float) -> bool:
        """Determines whether a new event can be displayed, enforcing duplicate suppression and priority."""
        # Duplicate suppression: identical message within 0.8s ignored
        if text == self._last_event_text and (now - self._last_event_time) < 0.8:
            return False

        # Priority arbitration: active higher priority toast is protected
        if self._island_state in ("SUCCESS", "ERROR", "HOLDING", "STATUS"):
            if now < self._toast_until and priority < self._current_priority:
                return False

        return True

    def _draw_vector_icon(self, cx: float, cy: float) -> None:
        """Renders refined native Canvas vector icons."""
        icon = self._island_icon
        color = self._island_color

        if icon == "CHECK":
            self.canvas.create_line(cx - 6, cy, cx - 2, cy + 5, cx + 6, cy - 5, fill=COLOR_SAGE_ACCENT, width=2.2, capstyle=tk.ROUND, joinstyle=tk.ROUND)
        elif icon == "CROSS":
            self.canvas.create_line(cx - 5, cy - 5, cx + 5, cy + 5, fill=COLOR_ERROR_RED, width=2, capstyle=tk.ROUND)
            self.canvas.create_line(cx - 5, cy + 5, cx + 5, cy - 5, fill=COLOR_ERROR_RED, width=2, capstyle=tk.ROUND)
        elif icon == "VOL_UP":
            self.canvas.create_polygon(cx - 8, cy - 3, cx - 5, cy - 3, cx - 2, cy - 6, cx - 2, cy + 6, cx - 5, cy + 3, cx - 8, cy + 3, fill=COLOR_TEXT_PRIMARY, outline="")
            self.canvas.create_arc(cx - 1, cy - 5, cx + 5, cy + 5, start=-45, extent=90, style=tk.ARC, outline=COLOR_SAGE_ACCENT, width=1.8)
            self.canvas.create_arc(cx + 2, cy - 8, cx + 10, cy + 8, start=-45, extent=90, style=tk.ARC, outline=COLOR_SAGE_ACCENT, width=1.8)
        elif icon == "VOL_DOWN":
            self.canvas.create_polygon(cx - 8, cy - 3, cx - 5, cy - 3, cx - 2, cy - 6, cx - 2, cy + 6, cx - 5, cy + 3, cx - 8, cy + 3, fill=COLOR_TEXT_PRIMARY, outline="")
            self.canvas.create_arc(cx - 1, cy - 5, cx + 5, cy + 5, start=-45, extent=90, style=tk.ARC, outline=COLOR_SAGE_ACCENT, width=1.8)
        elif icon == "MUTE":
            self.canvas.create_polygon(cx - 8, cy - 3, cx - 5, cy - 3, cx - 2, cy - 6, cx - 2, cy + 6, cx - 5, cy + 3, cx - 8, cy + 3, fill=COLOR_AMBER_WARN, outline="")
            self.canvas.create_line(cx - 7, cy + 6, cx + 6, cy - 6, fill=COLOR_ERROR_RED, width=2, capstyle=tk.ROUND)
        elif icon == "UNMUTE":
            self.canvas.create_polygon(cx - 8, cy - 3, cx - 5, cy - 3, cx - 2, cy - 6, cx - 2, cy + 6, cx - 5, cy + 3, cx - 8, cy + 3, fill=COLOR_TEXT_PRIMARY, outline="")
            self.canvas.create_arc(cx - 1, cy - 5, cx + 5, cy + 5, start=-45, extent=90, style=tk.ARC, outline=COLOR_SAGE_ACCENT, width=1.8)
            self.canvas.create_arc(cx + 2, cy - 8, cx + 10, cy + 8, start=-45, extent=90, style=tk.ARC, outline=COLOR_SAGE_ACCENT, width=1.8)
        elif icon == "APP":
            self.canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, fill=COLOR_APP_GREEN, outline="")
            self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=COLOR_TEXT_PRIMARY, outline="")
        elif icon == "HAND_LOST":
            self.canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, outline=COLOR_AMBER_WARN, width=1.8)
            self.canvas.create_line(cx - 3, cy, cx + 3, cy, fill=COLOR_AMBER_WARN, width=2, capstyle=tk.ROUND)
        elif icon == "HAND_FOUND":
            self.canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, outline=COLOR_SAGE_ACCENT, width=1.5)
            self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=COLOR_SAGE_ACCENT, outline="")
        elif icon == "PAUSE":
            self.canvas.create_rectangle(cx - 5, cy - 6, cx - 2, cy + 6, fill=COLOR_AMBER_WARN, outline="")
            self.canvas.create_rectangle(cx + 2, cy - 6, cx + 5, cy + 6, fill=COLOR_AMBER_WARN, outline="")
        elif icon == "PLAY":
            self.canvas.create_polygon(cx - 4, cy - 6, cx + 5, cy, cx - 4, cy + 6, fill=COLOR_SAGE_ACCENT, outline="")
        elif icon == "STATUS":
            self.canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, outline=COLOR_SAGE_ACCENT, width=1.5)
            self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=COLOR_SAGE_ACCENT, outline="")
        elif icon == "POWER_SAVE":
            self.canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, outline=COLOR_SAGE_ACCENT, width=1.5)
            self.canvas.create_line(cx - 3, cy + 3, cx + 3, cy - 3, fill=COLOR_SAGE_ACCENT, width=1.8, capstyle=tk.ROUND)
        elif icon == "POWER_WAIT":
            self.canvas.create_oval(cx - 7, cy - 7, cx + 7, cy + 7, outline=COLOR_AMBER_WARN, width=1.5)
            self.canvas.create_line(cx, cy, cx, cy - 3.5, fill=COLOR_AMBER_WARN, width=1.6, capstyle=tk.ROUND)
            self.canvas.create_line(cx, cy, cx + 3.0, cy, fill=COLOR_AMBER_WARN, width=1.6, capstyle=tk.ROUND)
        else:
            self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=color, outline="")

    def get_sound_bar_heights(
        self,
        volume_scalar: float,
        is_muted: bool = False,
        is_active: bool = False,
        now: float | None = None,
        num_bars: int = 7,
    ) -> list[float]:
        """
        Calculates vertical sound bar heights strictly tied to the system volume scalar [0.0, 1.0].
        Matches the 7-bar profile from the React Control Center.
        - Muted: bars become flat (2.5px).
        - Low volume: short bars.
        - High volume: tall bars.
        - Active dwell: subtle harmonic oscillation while maintaining true volume proportions.
        """
        if is_muted:
            return [2.0] * num_bars

        if now is None:
            now = time.perf_counter()

        vol = max(0.0, min(1.0, float(volume_scalar)))
        profile = [0.35, 0.60, 0.85, 1.00, 0.85, 0.60, 0.35]
        min_h = 2.0
        max_h = 18.0

        heights = []
        for i in range(num_bars):
            p = profile[i % len(profile)]
            base_h = min_h + (max_h - min_h) * vol * p
            if is_active and vol > 0.001:
                osc = 0.08 * math.sin(now * 8.0 + i * 0.9)
                h_bar = max(min_h, min(max_h, base_h * (1.0 + osc)))
            else:
                h_bar = base_h
            heights.append(round(h_bar, 2))
        return heights

    def _draw_volume_visualizer(self, w: float, h: float, cy: float) -> None:
        """
        Renders the Dynamic Island live audio visualizer:
        [ 🔊   ▁ ▃ ▆ █ ▆ ▃ ▁   68%   + ]
        - Clean speaker icon reflecting actual mute/unmute state
        - 7 vertical sound bars in sage accent scaled to system volume
        - Accurate volume percentage (e.g. '68%') in clean white text
        - Subtle direction indicator ('+' for Volume Up, '−' for Volume Down)
        - Subtle bottom progress line
        """
        now = time.perf_counter()
        vol = self._volume_scalar
        muted = self._volume_muted
        is_active = self._is_volume_active
        direction = self._volume_direction

        # 1. Speaker icon (reflecting mute state)
        cx_spk = 26.0
        if muted or vol <= 0.001:
            self.canvas.create_polygon(
                cx_spk - 7, cy - 3, cx_spk - 4, cy - 3,
                cx_spk - 1, cy - 6, cx_spk - 1, cy + 6,
                cx_spk - 4, cy + 3, cx_spk - 7, cy + 3,
                fill=COLOR_AMBER_WARN, outline=""
            )
            self.canvas.create_line(
                cx_spk - 6, cy + 6, cx_spk + 6, cy - 6,
                fill=COLOR_ERROR_RED, width=2, capstyle=tk.ROUND
            )
        else:
            self.canvas.create_polygon(
                cx_spk - 7, cy - 3, cx_spk - 4, cy - 3,
                cx_spk - 1, cy - 6, cx_spk - 1, cy + 6,
                cx_spk - 4, cy + 3, cx_spk - 7, cy + 3,
                fill=COLOR_TEXT_PRIMARY, outline=""
            )
            if vol > 0.05:
                self.canvas.create_arc(
                    cx_spk - 1, cy - 5, cx_spk + 5, cy + 5,
                    start=-45, extent=90, style=tk.ARC,
                    outline=COLOR_SAGE_ACCENT, width=1.8
                )
            if vol > 0.50:
                self.canvas.create_arc(
                    cx_spk + 2, cy - 8, cx_spk + 10, cy + 8,
                    start=-45, extent=90, style=tk.ARC,
                    outline=COLOR_SAGE_ACCENT, width=1.8
                )

        # 2. Sound bars (7 vertical bars with volume-proportional heights)
        bar_heights = self.get_sound_bar_heights(vol, is_muted=muted, is_active=is_active, now=now)
        self._bar_heights = bar_heights
        bars_cx = 95.0
        spacing = 7.5
        start_x = bars_cx - (len(bar_heights) - 1) * spacing / 2.0
        bar_color = "#4b5563" if muted else COLOR_SAGE_ACCENT

        for i, bh in enumerate(bar_heights):
            bx = start_x + i * spacing
            self.canvas.create_line(
                bx, cy - bh / 2.0, bx, cy + bh / 2.0,
                fill=bar_color, width=3.5, capstyle=tk.ROUND
            )

        # 3. Volume percentage text
        vol_pct = int(round(vol * 100.0))
        tx = 175.0
        text_color = COLOR_TEXT_SECONDARY if muted else COLOR_TEXT_PRIMARY
        self.canvas.create_text(
            tx, cy, anchor="center",
            text=f"{vol_pct}%",
            fill=text_color,
            font=("Segoe UI", 12, "bold")
        )

        # 4. Subtle direction indicator badge ('+' or '−')
        dx = 224.0
        self.canvas.create_oval(
            dx - 10, cy - 10, dx + 10, cy + 10,
            fill="#222429", outline="#2f323a", width=1
        )
        if direction in ("VOLUME_UP", "UP"):
            self.canvas.create_text(
                dx, cy - 1, anchor="center",
                text="+",
                fill=COLOR_SAGE_ACCENT,
                font=("Segoe UI", 12, "bold")
            )
        elif direction in ("VOLUME_DOWN", "DOWN"):
            self.canvas.create_text(
                dx, cy - 1, anchor="center",
                text="−",
                fill=COLOR_AMBER_WARN,
                font=("Segoe UI", 12, "bold")
            )

        # 5. Subtle bottom progress line
        track_y = h - 3.0
        track_x1 = 24.0
        track_x2 = w - 24.0
        self.canvas.create_line(
            track_x1, track_y, track_x2, track_y,
            fill="#222429", width=2, capstyle=tk.ROUND
        )
        if vol > 0.001 and not muted:
            fill_x2 = track_x1 + (track_x2 - track_x1) * vol
            self.canvas.create_line(
                track_x1, track_y, fill_x2, track_y,
                fill=COLOR_SAGE_ACCENT, width=2, capstyle=tk.ROUND
            )

    def _draw_wakanda_capsule(self, w: float, h: float, cy: float) -> None:
        """
        Renders the Dynamic Island Wakanda Forever capsule:
        - Matte black vertical body (#0c0a11)
        - Subtle violet perimeter border (#7959a2 or #9865d6)
        - Top specular reflection line (#e9d6ff)
        - Centered wordmark 'WAKANDA FOREVER'
        - Violet bottom progress line (#b983ff) representing elapsed hold fraction
        - STRICT RULE: No countdown numbers, no icons, no badges, no subtitle copy inside capsule.
        """
        r = h / 2.0
        # 1. Soft shadow
        self.canvas.create_oval(0, 1, h, h + 1, fill=COLOR_GRAPHITE_SHADOW, outline="")
        self.canvas.create_oval(w - h, 1, w, h + 1, fill=COLOR_GRAPHITE_SHADOW, outline="")
        self.canvas.create_rectangle(r, 1, w - r, h + 1, fill=COLOR_GRAPHITE_SHADOW, outline="")

        # 2. Violet outer hairline border
        border_col = COLOR_WAKANDA_BORDER_ARMED if self._progress > 0 else COLOR_WAKANDA_BORDER
        self.canvas.create_oval(0, 0, h, h, fill=border_col, outline="")
        self.canvas.create_oval(w - h, 0, w, h, fill=border_col, outline="")
        self.canvas.create_rectangle(r, 0, w - r, h, fill=border_col, outline="")

        # 3. Inner solid body inset by 1px
        self.canvas.create_oval(1, 1, h - 1, h - 1, fill=COLOR_WAKANDA_BG, outline="")
        self.canvas.create_oval(w - h + 1, 1, w - 1, h - 1, fill=COLOR_WAKANDA_BG, outline="")
        self.canvas.create_rectangle(r, 1, w - r, h - 1, fill=COLOR_WAKANDA_BG, outline="")

        # 4. Top glass specular reflection
        self.canvas.create_line(r + 10, 1, w - r - 10, 1, fill="#e9d6ff", width=1)

        # 5. Centered wordmark: strictly 'WAKANDA FOREVER'
        # Subtle underline glow
        self.canvas.create_line(w / 2.0 - 45, cy + 9, w / 2.0 + 45, cy + 9, fill="#4a2d68", width=1)
        self.canvas.create_text(
            w / 2.0, cy - 1, anchor="center",
            text="WAKANDA FOREVER",
            fill=COLOR_WAKANDA_TEXT,
            font=("Segoe UI", 11, "bold")
        )

        # 6. Bottom progress track & fill
        track_y = h - 4.0
        track_x1 = 26.0
        track_x2 = w - 26.0
        self.canvas.create_line(track_x1, track_y, track_x2, track_y, fill="#27212e", width=3, capstyle=tk.ROUND)
        if self._progress > 0.001:
            fill_x2 = track_x1 + (track_x2 - track_x1) * min(1.0, self._progress)
            self.canvas.create_line(track_x1, track_y, fill_x2, track_y, fill=COLOR_WAKANDA_PROGRESS, width=3, capstyle=tk.ROUND)

    def _draw_island(self) -> None:
        self.canvas.delete("all")
        w = self.w
        h = self.h
        r = h / 2.0
        cy = h / 2.0

        # Dynamic Island Wakanda Forever Capsule layout
        if self._island_mode == "WAKANDA":
            self._draw_wakanda_capsule(w, h, cy)
            return

        # Precision capsule geometry (Apple / macOS Dynamic Island style)
        # 1. Subtle soft shadow base
        self.canvas.create_oval(0, 1, h, h + 1, fill=COLOR_GRAPHITE_SHADOW, outline="")
        self.canvas.create_oval(w - h, 1, w, h + 1, fill=COLOR_GRAPHITE_SHADOW, outline="")
        self.canvas.create_rectangle(r, 1, w - r, h + 1, fill=COLOR_GRAPHITE_SHADOW, outline="")

        # 2. Outer hairline border in modern graphite border
        self.canvas.create_oval(0, 0, h, h, fill=COLOR_GRAPHITE_BORDER, outline="")
        self.canvas.create_oval(w - h, 0, w, h, fill=COLOR_GRAPHITE_BORDER, outline="")
        self.canvas.create_rectangle(r, 0, w - r, h, fill=COLOR_GRAPHITE_BORDER, outline="")

        # 3. Inner solid body inset by 1px
        self.canvas.create_oval(1, 1, h - 1, h - 1, fill=COLOR_GRAPHITE_BG, outline="")
        self.canvas.create_oval(w - h + 1, 1, w - 1, h - 1, fill=COLOR_GRAPHITE_BG, outline="")
        self.canvas.create_rectangle(r, 1, w - r, h - 1, fill=COLOR_GRAPHITE_BG, outline="")

        # 4. Subtle top glass specular reflection
        self.canvas.create_line(r + 6, 1, w - r - 6, 1, fill="#2e313a", width=1)

        # Dynamic Island Volume Visualizer layout
        if self._island_mode == "VOLUME":
            self._draw_volume_visualizer(w, h, cy)
            return

        # Vector icon
        cx = 26.0 if self._countdown_badge else 28.0
        self._draw_vector_icon(cx, cy)

        # Text rendering
        tx = 44.0 if self._countdown_badge else 48.0
        if self._countdown_badge:
            # Main label on left
            self.canvas.create_text(
                tx, cy, anchor="w",
                text=self._island_text,
                fill=COLOR_TEXT_PRIMARY,
                font=("Segoe UI", 10, "bold")
            )
            # Dedicated countdown badge pill on right
            badge_x2 = w - 16.0
            badge_w = 56.0
            badge_x1 = badge_x2 - badge_w
            badge_y1 = cy - 10.0
            badge_y2 = cy + 10.0
            # Subtle badge background pill
            self.canvas.create_oval(badge_x1, badge_y1, badge_x1 + 20, badge_y2, fill="#1c1e24", outline="#2f323a", width=1)
            self.canvas.create_oval(badge_x2 - 20, badge_y1, badge_x2, badge_y2, fill="#1c1e24", outline="#2f323a", width=1)
            self.canvas.create_rectangle(badge_x1 + 10, badge_y1, badge_x2 - 10, badge_y2, fill="#1c1e24", outline="")
            self.canvas.create_line(badge_x1 + 10, badge_y1, badge_x2 - 10, badge_y1, fill="#2f323a", width=1)
            self.canvas.create_line(badge_x1 + 10, badge_y2, badge_x2 - 10, badge_y2, fill="#2f323a", width=1)
            # Badge text centered in badge
            self.canvas.create_text(
                (badge_x1 + badge_x2) / 2.0, cy, anchor="center",
                text=self._countdown_badge,
                fill=COLOR_SAGE_ACCENT,
                font=("Segoe UI", 9, "bold")
            )
        elif self._island_subtext:
            self.canvas.create_text(tx, cy - 8, anchor="w", text=self._island_text, fill=COLOR_TEXT_PRIMARY, font=("Segoe UI", 10, "bold"))
            self.canvas.create_text(tx, cy + 9, anchor="w", text=self._island_subtext, fill=COLOR_TEXT_SECONDARY, font=("Segoe UI", 8))
        else:
            self.canvas.create_text(tx, cy, anchor="w", text=self._island_text, fill=COLOR_TEXT_PRIMARY, font=("Segoe UI", 11, "bold"))

        # Progress bar along bottom
        if self._progress > 0:
            track_y = h - 3.0
            track_x1 = 20.0
            track_x2 = w - 20.0
            self.canvas.create_line(track_x1, track_y, track_x2, track_y, fill="#222429", width=2, capstyle=tk.ROUND)
            fill_x2 = track_x1 + (track_x2 - track_x1) * self._progress
            self.canvas.create_line(track_x1, track_y, fill_x2, track_y, fill=self._island_color, width=2, capstyle=tk.ROUND)

    def _animate_y(self, target_y: float, speed: float = HUD_ANIMATION_SPEED) -> None:
        dy = target_y - self.current_y
        self.current_y += dy * speed
        if abs(self.current_y - target_y) < 1.0:
            self.current_y = target_y
        self.root.geometry(f"{self.w}x{self.h}+{self.x}+{int(self.current_y)}")

    def update_state(self, ss_controller=None, is_paused: bool = False, runtime_status: dict | None = None, wakanda_gesture=None) -> None:
        # Drain all background-dispatched UI actions on the main thread
        while not self._dispatch_queue.empty():
            try:
                action = self._dispatch_queue.get_nowait()
                action()
            except queue.Empty:
                break
            except Exception as e:
                logger.debug("Error executing queued overlay action: %s", e)

        now = time.perf_counter()
        if now - self._last_ui_update < 0.033:
            return
        self._last_ui_update = now

        # Animate dimensions smoothly
        self._animate_dimensions()

        # State transitions
        if self._island_state in ("SUCCESS", "ERROR", "STATUS"):
            if self.autohide_enabled and now > self._toast_until:
                self._island_state = "RETRACTING"
                self._current_priority = 0
                self._island_subtext = ""
                self._reset_dimensions()
        elif self._island_mode == "POWER_SAVE" and self._ps_countdown_active:
            elapsed = now - self._ps_start_time
            rem = max(0.0, self._ps_deadline - now)
            if self.timer_enabled:
                mins = int(rem // 60)
                secs = int(rem % 60)
                self._countdown_badge = f"{mins:02d}:{secs:02d}"
                self._progress = min(1.0, max(0.0, elapsed / self._ps_duration))
            else:
                self._countdown_badge = ""
                self._progress = 0.0

            if rem <= 0.0:
                # State D: Countdown completed -> Show completion message for completion_duration_s
                self._ps_countdown_active = False
                self._island_state = "SUCCESS"
                self._island_mode = "POWER_SAVE_COMPLETE"
                self._island_text = "POWER SAVER · HIDING"
                self._island_subtext = ""
                self._island_icon = "POWER_SAVE"
                self._island_color = COLOR_SAGE_ACCENT
                self._countdown_badge = ""
                self._progress = 1.0
                self._toast_until = now + self.completion_duration_s
                self._set_dimensions(250, 44)
        elif wakanda_gesture and getattr(wakanda_gesture, 'is_holding', False):
            prog = getattr(wakanda_gesture, 'progress', 0.0)
            self._current_priority = PRIORITY_CRITICAL
            if self._island_state in ("IDLE", "RETRACTING"):
                self._island_state = "DROPPING"
                self.root.deiconify()
                self.root.lift()
                self._is_hidden = False
            elif self._island_state == "DROPPING" and self.current_y == self.y_visible:
                self._island_state = "HOLDING"

            self._island_mode = "WAKANDA"
            self._set_dimensions(260, 46)
            self._island_text = "WAKANDA FOREVER"
            self._countdown_badge = ""
            self._island_subtext = ""
            self._progress = min(1.0, max(0.0, float(prog)))
            self._island_color = COLOR_WAKANDA_PROGRESS
        elif ss_controller and ss_controller._state == ScreenshotState.HOLDING:
            rem = getattr(ss_controller, 'remaining', SCREENSHOT_HOLD_DURATION_S)
            prog = getattr(ss_controller, 'progress', 0.0)

            self._current_priority = PRIORITY_CRITICAL
            if self._island_state in ("IDLE", "RETRACTING"):
                self._island_state = "DROPPING"
                self._island_color = COLOR_SAGE_ACCENT
                self.root.deiconify()
                self.root.lift()
                self._is_hidden = False
            elif self._island_state == "DROPPING" and self.current_y == self.y_visible:
                self._island_state = "HOLDING"

            self._island_mode = "SCREENSHOT_HOLD"
            self._set_dimensions(270, 46)
            self._island_text = "Hold both palms"
            self._countdown_badge = f"{rem:.1f}s"
            self._island_subtext = ""
            self._island_icon = "CHECK"
            self._progress = min(1.0, max(0.0, float(prog)))
        elif ss_controller and getattr(ss_controller, '_display_until', 0) > now:
            if "CANCELLED" in getattr(ss_controller, 'hud_text', '') and self._island_state in ("DROPPING", "HOLDING"):
                self._island_state = "RETRACTING"
                self._progress = 0.0
                self._current_priority = 0
                self._countdown_badge = ""
                self._reset_dimensions()
        else:
            if self._island_state in ("DROPPING", "HOLDING"):
                if self._island_mode == "VOLUME":
                    if now > self._toast_until and not self._is_volume_active:
                        self._island_state = "RETRACTING"
                        self._progress = 0.0
                        self._current_priority = 0
                        self._reset_dimensions()
                elif self._island_mode == "WAKANDA":
                    if not (wakanda_gesture and getattr(wakanda_gesture, 'is_holding', False)):
                        self._island_state = "RETRACTING"
                        self._progress = 0.0
                        self._current_priority = 0
                        self._reset_dimensions()
                elif self._island_mode == "POWER_SAVE":
                    # While POWER_SAVE countdown is active, do not retract until countdown finishes
                    if not self._ps_countdown_active:
                        self._island_state = "RETRACTING"
                        self._progress = 0.0
                        self._current_priority = 0
                        self._countdown_badge = ""
                        self._reset_dimensions()
                else:
                    self._island_state = "RETRACTING"
                    self._progress = 0.0
                    self._current_priority = 0
                    self._countdown_badge = ""
                    self._reset_dimensions()

        if ss_controller:
            if ss_controller._state == ScreenshotState.CAPTURED:
                if "CAPTURED" in getattr(ss_controller, 'hud_text', '') and self._island_state != "SUCCESS":
                    import re
                    m = re.search(r'\((.*?)\)', ss_controller.hud_text)
                    if m:
                        self.show_success_toast(m.group(1))
                    else:
                        self.show_success_toast()
            elif ss_controller._state == ScreenshotState.ERROR:
                if self._island_state != "ERROR":
                    self.show_error_toast()

        # Animation dispatch
        if self._island_state in ("DROPPING", "HOLDING", "SUCCESS", "ERROR", "STATUS"):
            self._animate_y(self.y_visible)
        elif self._island_state == "RETRACTING":
            self._animate_y(self.y_hidden)
            if self.current_y == self.y_hidden and not self._is_hidden:
                self.root.withdraw()
                self.root.update()
                self._is_hidden = True
                self._island_state = "IDLE"
                self._island_mode = ""
                self._is_volume_active = False
                self._progress = 0.0
                self._current_priority = 0
                self._island_subtext = ""
                self._reset_dimensions()
        elif self._island_state == "IDLE":
            self._progress = 0.0

        if not self._is_hidden and not self._force_hide:
            self._draw_island()
            self.root.update()

    def show_success_toast(self, filename: str | None = None) -> None:
        now = time.perf_counter()
        if not self._can_post_event(PRIORITY_CRITICAL, "Screenshot saved", now):
            return
        self._current_priority = PRIORITY_CRITICAL
        self._last_event_text = "Screenshot saved"
        self._last_event_time = now
        self._toast_until = now + HUD_TOAST_DURATION_S
        self._island_state = "SUCCESS"
        self._island_text = "Screenshot saved"
        self._island_subtext = ""
        self._island_icon = "CHECK"
        self._island_color = "#00ff66"
        self._progress = 1.0
        self._reset_dimensions()
        self.root.deiconify()
        self.root.lift()
        self._is_hidden = False

    def show_error_toast(self) -> None:
        now = time.perf_counter()
        if not self._can_post_event(PRIORITY_CRITICAL, "Screenshot failed", now):
            return
        self._current_priority = PRIORITY_CRITICAL
        self._last_event_text = "Screenshot failed"
        self._last_event_time = now
        self._toast_until = now + HUD_TOAST_DURATION_S
        self._island_state = "ERROR"
        self._island_text = "Screenshot failed"
        self._island_subtext = ""
        self._island_icon = "CROSS"
        self._island_color = "#ff4444"
        self._progress = 1.0
        self._reset_dimensions()
        self.root.deiconify()
        self.root.lift()
        self._is_hidden = False

    def show_app_toast(self, app_name: str = "WhatsApp", success: bool = True) -> None:
        def _action():
            now = time.perf_counter()
            text = f"Opening {app_name}" if success else f"{app_name} not found"
            if not self._can_post_event(PRIORITY_CRITICAL, text, now):
                return
            self._current_priority = PRIORITY_CRITICAL
            self._last_event_text = text
            self._last_event_time = now
            self._toast_until = now + HUD_TOAST_DURATION_S
            self._island_state = "SUCCESS" if success else "ERROR"
            self._island_text = text
            self._island_subtext = ""
            self._island_icon = "APP" if success else "CROSS"
            self._island_color = "#25D366" if success else "#ff4444"
            self._progress = 1.0
            self._reset_dimensions()
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def show_audio_toast(self, action: str, success: bool = True) -> None:
        def _action():
            now = time.perf_counter()
            if not success:
                text = "Audio control failed"
                icon = "CROSS"
                color = "#ff4444"
                state = "ERROR"
            elif action == "MUTED":
                text = "Muted"
                icon = "MUTE"
                color = "#ff9900"
                state = "SUCCESS"
            elif action in ("RESTORED", "UNMUTED"):
                text = "Unmuted" if action == "UNMUTED" else "Volume restored"
                icon = "UNMUTE"
                color = "#00ff66"
                state = "SUCCESS"
            else:
                text = f"Audio {action.lower()}"
                icon = "UNMUTE"
                color = "#00ff66"
                state = "SUCCESS"

            if not self._can_post_event(PRIORITY_CRITICAL, text, now):
                return
            self._current_priority = PRIORITY_CRITICAL
            self._last_event_text = text
            self._last_event_time = now
            self._toast_until = now + HUD_TOAST_DURATION_S
            self._island_state = state
            self._island_text = text
            self._island_subtext = ""
            self._island_icon = icon
            self._island_color = color
            self._progress = 1.0
            self._reset_dimensions()
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def show_ear_volume(
        self,
        direction_name: str,
        volume_scalar: float,
        is_active: bool,
        is_muted: bool | None = None,
    ) -> None:
        now = time.perf_counter()
        vol = max(0.0, min(1.0, float(volume_scalar)))
        vol_pct = int(round(vol * 100.0))

        # Determine mute state
        if is_muted is not None:
            muted = bool(is_muted)
        elif self._audio_controller is not None:
            muted = bool(getattr(self._audio_controller, 'is_muted', False))
        else:
            muted = (vol <= 0.001)

        self._volume_scalar = vol
        self._volume_muted = muted
        self._is_volume_active = is_active
        self._volume_direction = direction_name

        arrow = "↑" if direction_name in ("VOLUME_UP", "UP") else "↓"
        icon = "MUTE" if muted else ("VOL_UP" if direction_name in ("VOLUME_UP", "UP") else "VOL_DOWN")
        text = f"Volume {arrow}  {vol_pct}%"

        self._current_priority = PRIORITY_VOLUME
        self._last_event_text = text
        self._last_event_time = now
        self._island_mode = "VOLUME"
        self._island_text = text
        self._island_subtext = ""
        self._island_icon = icon
        self._island_color = "#ffaa00" if muted else "#00e5ff"
        self._progress = vol

        if not is_active:
            self._is_volume_active = False
            # When ending gesture, keep island visible briefly (~800ms) then dismiss smoothly
            self._toast_until = now + 0.8
            self._island_state = "SUCCESS"
            return

        self._toast_until = now + 1.2
        self._island_state = "HOLDING"
        self._set_dimensions(260, 44)
        self.root.deiconify()
        self.root.lift()
        self._is_hidden = False

    def show_tracking_toast(self, transition: str) -> None:
        def _action():
            now = time.perf_counter()
            if transition == "LOST":
                text = "Hand lost"
                icon = "HAND_LOST"
                color = "#ffaa00"
            else:
                text = "Hand reacquired"
                icon = "HAND_FOUND"
                color = "#00e5ff"

            if not self._can_post_event(PRIORITY_TRACKING, text, now):
                return
            self._current_priority = PRIORITY_TRACKING
            self._last_event_text = text
            self._last_event_time = now
            self._toast_until = now + 1.2
            self._island_state = "SUCCESS"
            self._island_text = text
            self._island_subtext = ""
            self._island_icon = icon
            self._island_color = color
            self._progress = 1.0
            self._reset_dimensions()
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def show_pause_toast(self, is_paused: bool) -> None:
        def _action():
            now = time.perf_counter()
            text = "System Paused" if is_paused else "System Resumed"
            icon = "PAUSE" if is_paused else "PLAY"
            color = "#ffaa00" if is_paused else "#00ff66"

            if not self._can_post_event(PRIORITY_CRITICAL, text, now):
                return
            self._current_priority = PRIORITY_CRITICAL
            self._last_event_text = text
            self._last_event_time = now
            self._toast_until = now + 1.5
            self._island_state = "SUCCESS"
            self._island_text = text
            self._island_subtext = ""
            self._island_icon = icon
            self._island_color = color
            self._progress = 1.0
            self._reset_dimensions()
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def show_runtime_status(self, status_info: dict, duration: float = HUD_STATUS_DURATION_S) -> None:
        def _action():
            now = time.perf_counter()
            if not self._can_post_event(PRIORITY_STATUS, "STATUS", now):
                return

            fps = float(status_info.get("fps", 0.0))
            owner = str(status_info.get("owner", "NONE"))
            tracking = str(status_info.get("tracking", "No Hands"))
            paused = "PAUSED" if status_info.get("paused", False) else "ACTIVE"

            self._current_priority = PRIORITY_STATUS
            self._last_event_text = "STATUS"
            self._last_event_time = now
            self._toast_until = now + duration
            self._island_state = "STATUS"
            self._island_icon = "STATUS"
            self._island_color = COLOR_SAGE_ACCENT
            self._island_text = f"Air Point · {fps:.0f} FPS · {paused}"
            self._island_subtext = f"Cursor: {owner} | Track: {tracking}"
            self._progress = 0.0
            self.w = 320
            self.h = 52
            self._set_dimensions(320, 52)
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def show_wakanda_complete(self) -> None:
        def _action():
            now = time.perf_counter()
            self._current_priority = PRIORITY_CRITICAL
            self._last_event_text = "WAKANDA FOREVER"
            self._last_event_time = now
            self._toast_until = now + 1.2
            self._island_state = "SUCCESS"
            self._island_mode = "WAKANDA"
            self._island_text = "WAKANDA FOREVER"
            self._countdown_badge = ""
            self._island_subtext = ""
            self._progress = 1.0
            self._set_dimensions(260, 46)
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def configure(
        self,
        island_enabled: bool | None = None,
        notifications_enabled: bool | None = None,
        timer_enabled: bool | None = None,
        autohide_enabled: bool | None = None,
        hud_duration_s: float | None = None,
        completion_duration_s: float | None = None,
    ) -> None:
        """Thread-safe dynamic configuration update from Control Server settings."""
        def _action():
            if island_enabled is not None:
                self.island_enabled = bool(island_enabled)
                if not self.island_enabled:
                    self.cancel_power_save_countdown()
                    if not self._is_hidden:
                        self.hide()
                elif self._is_hidden and self._force_hide:
                    self._force_hide = False
            if notifications_enabled is not None:
                self.notifications_enabled = bool(notifications_enabled)
            if timer_enabled is not None:
                self.timer_enabled = bool(timer_enabled)
            if autohide_enabled is not None:
                self.autohide_enabled = bool(autohide_enabled)
            if hud_duration_s is not None:
                self.hud_duration_s = max(10.0, min(1800.0, float(hud_duration_s)))
            if completion_duration_s is not None:
                self.completion_duration_s = max(1.0, min(5.0, float(completion_duration_s)))
        self._dispatch_to_main(_action)

    def cancel_power_save_countdown(self) -> None:
        """Immediately stops any active Power Saver countdown or completion toast."""
        self._ps_token = None
        self._ps_countdown_active = False
        self._ps_start_time = 0.0
        self._ps_deadline = 0.0
        self._is_test_countdown = False
        if self._island_mode in ("POWER_SAVE", "POWER_SAVE_COMPLETE"):
            self._island_mode = ""
            self._countdown_badge = ""
            self._progress = 0.0

    def show_normal_mode(self, toast_duration: float = 1.5) -> None:
        """State A: Displays AIR POINT · NORMAL notification."""
        def _action():
            if not self.island_enabled or not self.notifications_enabled:
                return
            self.cancel_power_save_countdown()
            now = time.perf_counter()
            text = "AIR POINT · NORMAL"
            if not self._can_post_event(PRIORITY_STATUS, text, now):
                return
            self._current_priority = PRIORITY_STATUS
            self._last_event_text = text
            self._last_event_time = now
            self._toast_until = now + toast_duration
            self._island_state = "SUCCESS"
            self._island_mode = ""
            self._island_text = text
            self._island_subtext = ""
            self._island_icon = "PLAY"
            self._island_color = COLOR_SAGE_ACCENT
            self._countdown_badge = ""
            self._progress = 1.0
            self._set_dimensions(250, 44)
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def show_power_saver_enabled_waiting(self, toast_duration: float = 2.5) -> None:
        """State B: User toggles Power Saver ON, waiting for inactivity."""
        def _action():
            if not self.island_enabled or not self.notifications_enabled:
                return
            self.cancel_power_save_countdown()
            now = time.perf_counter()
            text = "POWER SAVER · WAITING"
            subtext = ""
            full_event_key = "POWER_SAVER_WAITING"
            if not self._can_post_event(PRIORITY_STATUS, full_event_key, now):
                return
            self._current_priority = PRIORITY_STATUS
            self._last_event_text = full_event_key
            self._last_event_time = now
            self._toast_until = now + toast_duration
            self._island_state = "STATUS"
            self._island_mode = ""
            self._island_text = text
            self._island_subtext = subtext
            self._island_icon = "POWER_WAIT"
            self._island_color = COLOR_AMBER_WARN
            self._countdown_badge = ""
            self._progress = 0.0
            self._set_dimensions(250, 44)
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def start_power_save_countdown(self, duration_s: float | None = None) -> None:
        """State C: Inactivity threshold reached; engine entered POWER_SAVE. Start countdown."""
        def _action():
            if not self.island_enabled or not self.notifications_enabled:
                return
            dur = float(duration_s) if duration_s is not None else self.hud_duration_s
            dur = max(10.0, min(1800.0, dur))
            now = time.perf_counter()
            self._ps_token = object()
            self._ps_countdown_active = True
            self._ps_start_time = now
            self._ps_duration = dur
            self._ps_deadline = now + dur
            self._is_test_countdown = False
            self._current_priority = PRIORITY_STATUS
            self._last_event_text = "POWER_SAVER_COUNTDOWN"
            self._last_event_time = now
            self._island_state = "HOLDING"
            self._island_mode = "POWER_SAVE"
            self._island_text = "POWER SAVER"
            self._island_subtext = ""
            self._island_icon = "POWER_SAVE"
            self._island_color = COLOR_SAGE_ACCENT

            mins = int(dur // 60)
            secs = int(dur % 60)
            self._countdown_badge = f"{mins:02d}:{secs:02d}" if self.timer_enabled else ""
            self._progress = 0.0
            self._set_dimensions(250, 44)
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def start_test_countdown(self, duration_s: float = 5.0) -> None:
        """
        Runs a safe test countdown directly on the real desktop overlay.
        Does NOT modify PowerStateManager or send native input.
        """
        def _action():
            if not self.island_enabled:
                return
            now = time.perf_counter()
            dur = max(1.0, min(30.0, float(duration_s)))
            self._ps_token = object()
            self._ps_countdown_active = True
            self._ps_start_time = now
            self._ps_duration = dur
            self._ps_deadline = now + dur
            self._is_test_countdown = True
            self._current_priority = PRIORITY_STATUS
            self._last_event_text = "POWER_SAVER_COUNTDOWN_TEST"
            self._last_event_time = now
            self._island_state = "HOLDING"
            self._island_mode = "POWER_SAVE"
            self._island_text = "POWER SAVER"
            self._island_subtext = ""
            self._island_icon = "POWER_SAVE"
            self._island_color = COLOR_SAGE_ACCENT

            mins = int(dur // 60)
            secs = int(dur % 60)
            self._countdown_badge = f"{mins:02d}:{secs:02d}" if self.timer_enabled else ""
            self._progress = 0.0
            self._set_dimensions(250, 44)
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def show_wake_confirmed(self, toast_duration: float = 2.0) -> None:
        """State E: Hand detected during probe; engine wakes to NORMAL mode."""
        def _action():
            if not self.island_enabled or not self.notifications_enabled:
                return
            self.cancel_power_save_countdown()
            now = time.perf_counter()
            text = "HAND DETECTED · NORMAL"
            subtext = ""
            full_event_key = "WAKE_CONFIRMED"
            if not self._can_post_event(PRIORITY_CRITICAL, full_event_key, now):
                return
            self._current_priority = PRIORITY_CRITICAL
            self._last_event_text = full_event_key
            self._last_event_time = now
            self._toast_until = now + toast_duration
            self._island_state = "SUCCESS"
            self._island_mode = ""
            self._island_text = text
            self._island_subtext = subtext
            self._island_icon = "HAND_FOUND"
            self._island_color = COLOR_SAGE_ACCENT
            self._countdown_badge = ""
            self._progress = 1.0
            self._set_dimensions(250, 44)
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def show_power_saver_disabled(self, toast_duration: float = 1.5) -> None:
        """State F: User toggles Power Saver OFF."""
        def _action():
            if not self.island_enabled or not self.notifications_enabled:
                return
            self.cancel_power_save_countdown()
            now = time.perf_counter()
            text = "AIR POINT · NORMAL"
            subtext = "Power saver disabled"
            full_event_key = "POWER_SAVER_DISABLED"
            if not self._can_post_event(PRIORITY_STATUS, full_event_key, now):
                return
            self._current_priority = PRIORITY_STATUS
            self._last_event_text = full_event_key
            self._last_event_time = now
            self._toast_until = now + toast_duration
            self._island_state = "SUCCESS"
            self._island_mode = ""
            self._island_text = text
            self._island_subtext = subtext
            self._island_icon = "PLAY"
            self._island_color = COLOR_SAGE_ACCENT
            self._countdown_badge = ""
            self._progress = 1.0
            self._set_dimensions(250, 44)
            self.root.deiconify()
            self.root.lift()
            self._is_hidden = False
        self._dispatch_to_main(_action)

    def close(self) -> None:
        self.cancel_power_save_countdown()
        try:
            self.root.destroy()
        except Exception:
            pass


# Backward & Forward Compatibility Aliases
DynamicIslandHUD = ScreenshotOverlay
FeedbackOverlay = ScreenshotOverlay
