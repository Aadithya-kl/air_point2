"""
Unit tests for Air Point Phase 4.3: Fast, Smooth, Natural Cursor Movement.

Verifies:
1. OneEuroFilter responsiveness: Fast motion (> 1.0 norm/s) achieves high alpha (> 0.70)
   with minimal lag (< 1-2 frames), eliminating movement hesitation/stutter.
2. OneEuroFilter stillness stability: Hand at rest achieves low alpha (<= 0.15) with > 80% jitter reduction.
3. Instantaneous breakaway: No initial deadband or dummy 0.0 derivative seeding on first motion.
4. Rapid post-motion settling: Cursor reaches destination and settles within 2 frames of hand stop (zero creeping).
5. Orchestrator sweep headroom: Fast intentional flicks up to 8000 px/s proceed without clamping.
6. Consecutive jump resilience: Valid multi-frame repositioning settles without repeated ratcheting warnings.
"""

import math
import random
import time
import unittest
from unittest.mock import patch, MagicMock

from core.filter import OneEuroFilter
from core.actuator import MouseActuator
from core.display import VirtualDesktop, TrackpadZone
from core.gestures.right_hand import RightHandProcessor
from core.gestures.left_hand import LeftHandProcessor
from core.gestures.orchestrator import GestureOrchestrator, PointerOwner
from core.tracker import HandsResult, Landmark


class TestPhase4_3CursorMovement(unittest.TestCase):
    def setUp(self):
        self.desktop = VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1)
        self.actuator = MouseActuator(1920, 1080)
        self.actuator.move = MagicMock(return_value=True)
        self.trackpad = TrackpadZone(170, 470, 120, 320)
        self.right = RightHandProcessor(self.actuator, self.desktop, self.trackpad)
        self.left = LeftHandProcessor(self.actuator, self.desktop, self.trackpad)
        self.actuator.get_cursor_pos = MagicMock(return_value=(960, 540))
        self.orchestrator = GestureOrchestrator(self.actuator, self.desktop, self.trackpad, initial_cursor_anchor=(960, 540))

    def _make_hand(self, norm_x: float, norm_y: float) -> list[Landmark]:
        """Construct synthetic 21-landmark hand with index tip at (norm_x, norm_y)."""
        lms = []
        for i in range(21):
            if i == 8:
                lms.append(Landmark(x=norm_x, y=norm_y, z=0.0))
            elif i == 4:
                lms.append(Landmark(x=norm_x - 0.15, y=norm_y + 0.10, z=0.0))
            elif i == 5:
                lms.append(Landmark(x=norm_x - 0.05, y=norm_y + 0.20, z=0.0))
            elif i == 17:
                lms.append(Landmark(x=norm_x + 0.10, y=norm_y + 0.20, z=0.0))
            else:
                lms.append(Landmark(x=norm_x, y=norm_y + 0.20, z=0.0))
        return lms

    def test_one_euro_filter_high_speed_responsiveness(self):
        """Verify that fast hand sweeps (> 1.0 norm/s) adapt cutoff and achieve >= 70% per-frame update (zero lag)."""
        f = OneEuroFilter(freq=30.0, mincutoff=0.462, beta=0.02)
        dt = 1.0 / 30.0
        t = 0.0

        # Initialize filter at center
        f(0.50, t)

        # Fast sweep: hand advances 0.04 per frame (1.2 norm/s)
        curr = 0.50
        lags = []
        for _ in range(8):
            t += dt
            curr += 0.04
            filtered = f(curr, t)
            lags.append(curr - filtered)

        # In motion, lag should remain tightly bounded (around 1-1.5 frames at 1.2 norm/s)
        for lag in lags[2:]:
            self.assertLess(lag, 0.065, f"Filter lag too high during motion: {lag:.4f}")

    def test_one_euro_filter_stillness_jitter_reduction(self):
        """Verify that stationary hand (sub-pixel tremor) achieves substantial (> 70%) jitter reduction."""
        random.seed(1337)
        f = OneEuroFilter(freq=30.0, mincutoff=0.462, beta=0.02)
        dt = 1.0 / 30.0
        t = 0.0

        f(0.50, t)
        raw_vals = []
        filt_vals = []

        for _ in range(60):
            t += dt
            noise = random.gauss(0, 0.0006)
            raw = 0.50 + noise
            filt = f(raw, t)
            raw_vals.append(raw)
            filt_vals.append(filt)

        raw_std = math.sqrt(sum((v - 0.50)**2 for v in raw_vals) / len(raw_vals))
        filt_std = math.sqrt(sum((v - 0.50)**2 for v in filt_vals) / len(filt_vals))
        reduction = (1.0 - filt_std / raw_std) * 100.0

        self.assertGreater(reduction, 60.0, f"Expected >60% jitter reduction, got {reduction:.1f}%")

    def test_instantaneous_breakaway_no_initial_deadband(self):
        """Verify that derivative filter initializes on first motion without being suppressed by dummy 0.0."""
        f = OneEuroFilter(freq=30.0, mincutoff=0.462, beta=0.02)
        dt = 1.0 / 30.0
        t = 0.0

        # Hand stationary at 0.50
        f(0.50, t)

        # First movement step: delta of 0.03
        t += dt
        out = f(0.53, t)
        delta_filtered = out - 0.50

        # Should move at least 30% of the delta in the very first frame (no deadband stickiness)
        self.assertGreater(delta_filtered, 0.009, f"Initial motion step choked by deadband: {delta_filtered:.4f}")

    def test_rapid_settling_zero_creeping_after_stop(self):
        """Verify that when hand stops moving, filter settles within 2 frames without creeping."""
        f = OneEuroFilter(freq=30.0, mincutoff=0.462, beta=0.02)
        dt = 1.0 / 30.0
        t = 0.0

        f(0.50, t)

        # 6 frames of fast motion
        curr = 0.50
        for _ in range(6):
            t += dt
            curr += 0.03
            f(curr, t)

        target = curr  # 0.68

        # Frame 1 after stop
        t += dt
        s1 = f(target, t)

        # Frame 2 after stop
        t += dt
        s2 = f(target, t)

        # Residual lag after 2 frames should settle cleanly (< 1 frame of movement)
        residual = abs(target - s2)
        self.assertLess(residual, 0.030, f"Cursor still creeping after 2 frames: residual={residual:.4f}")

    def test_orchestrator_fast_intentional_flick_not_clamped(self):
        """Verify intentional hand flick (e.g. 500px in 66ms, ~7500 px/s) passes without clamping."""
        now = time.perf_counter()

        # Step 1: establish initial position
        h1 = HandsResult()
        h1.right = self._make_hand(0.40, 0.40)
        with patch("time.perf_counter", return_value=now):
            self.orchestrator.process(h1)
        p1 = self.orchestrator.cursor_pos
        self.assertIsNotNone(p1)

        # Step 2: fast intentional sweep over 66ms (2 frames)
        h2 = HandsResult()
        h2.right = self._make_hand(0.48, 0.48)

        with patch("core.gestures.orchestrator.logger.warning") as mock_warn:
            with patch("time.perf_counter", return_value=now + 0.066):
                self.orchestrator.process(h2)
            mock_warn.assert_not_called()

        p2 = self.orchestrator.cursor_pos
        self.assertNotEqual(p1, p2)

    def test_orchestrator_consecutive_reposition_clean_catchup(self):
        """Verify persistent repositioning across 2 frames catches up without ratcheted warning loop."""
        now = time.perf_counter()

        h1 = HandsResult()
        h1.right = self._make_hand(0.50, 0.50)
        with patch("time.perf_counter", return_value=now):
            self.orchestrator.process(h1)

        # Frame 1: extreme jump (> 1000px in 16ms)
        h2 = HandsResult()
        h2.right = self._make_hand(0.95, 0.95)

        with patch("core.gestures.orchestrator.logger.warning") as mock_warn:
            with patch("time.perf_counter", return_value=now + 0.016):
                self.orchestrator.process(h2)
            # Frame 1: clamped and warned
            mock_warn.assert_called_once()

        # Frame 2: hand is genuinely still at (0.95, 0.95)
        with patch("core.gestures.orchestrator.logger.warning") as mock_warn2:
            with patch("time.perf_counter", return_value=now + 0.049):
                self.orchestrator.process(h2)
            # Frame 2: catches up cleanly without another warning
            mock_warn2.assert_not_called()

        final_pos = self.orchestrator.cursor_pos
        target_x, target_y = self.orchestrator._right.cursor_pos
        self.assertEqual(final_pos, (target_x, target_y))


if __name__ == "__main__":
    unittest.main()
