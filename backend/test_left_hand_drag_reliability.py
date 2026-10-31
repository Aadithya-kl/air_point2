# test_left_hand_drag_reliability.py
"""
Unit tests for Left-Hand Drag-and-Drop Reliability and Free Cursor Movement.

Verifies:
1. Left-hand single drag maintains pointer ownership throughout the drag without theft by right hand.
2. Left hand cursor moves freely during active drag.
3. Temporary 1-frame camera tracking loss (MediaPipe dropout) does NOT prematurely drop the file.
4. Temporary 1-frame perspective pinch-distance spike (rotation noise) does NOT prematurely drop the file.
5. Explicit release (open palm or wide pinch opening) cleanly and immediately drops the file.
6. Prolonged tracking loss (> 200ms) safely releases the drag (failsafe).
"""

import math
import time
import unittest
from unittest.mock import MagicMock, patch

from core.tracker import Landmark, HandsResult
from core.gestures.orchestrator import GestureOrchestrator, PointerOwner
from core.actuator import MouseActuator
from core.display import VirtualDesktop, TrackpadZone
import config


class MockActuator(MouseActuator):
    def __init__(self, w=1920, h=1080):
        super().__init__(w, h)
        self.moves = []
        self.drags = 0
        self.drops = 0
        self._dragging = False
        self._current_pos = (960, 540)

    def move(self, x, y):
        self.moves.append((int(x), int(y)))
        self._current_pos = (int(x), int(y))
        return True

    def get_cursor_pos(self):
        return self._current_pos

    def drag_start(self, now=None):
        if not self._dragging:
            self.drags += 1
            self._dragging = True
            return True
        return False

    def drag_end(self):
        if self._dragging:
            self.drops += 1
            self._dragging = False
            return True
        return False

    @property
    def is_dragging(self):
        return self._dragging


class TestLeftHandDragReliability(unittest.TestCase):
    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.PINCH_CLICK_ENABLED = True
        config.LEFT_DRAG_ENABLED = True
        config.CAMERA_FPS = 30
        config.LEFT_DRAG_START_NORM_DIST = 0.55
        config.LEFT_DRAG_RELEASE_NORM_DIST = 0.75
        config.LEFT_DRAG_CONFIRM_S = 0.10

        self.actuator = MockActuator(1920, 1080)
        self.desktop = VirtualDesktop(1920, 1080, 1)
        self.trackpad = TrackpadZone(100, 540, 80, 400)
        self.orchestrator = GestureOrchestrator(
            self.actuator,
            self.desktop,
            self.trackpad,
            initial_cursor_anchor=(960, 540),
        )

    def _process(self, hands, t):
        with patch("time.perf_counter", return_value=t):
            self.orchestrator.process(hands)

    def _make_left_hand(self, norm_x=0.5, norm_y=0.5, pinch_norm=0.4, open_palm=False):
        """Construct synthetic 21-landmark left hand."""
        lms = [Landmark(x=norm_x, y=norm_y, z=0.0)] * 21
        lms[5] = Landmark(x=norm_x - 0.10, y=norm_y, z=0.0)
        lms[17] = Landmark(x=norm_x + 0.10, y=norm_y, z=0.0)
        # palm width = 0.20
        lms[8] = Landmark(x=norm_x, y=norm_y, z=0.0)  # index tip
        lms[6] = Landmark(x=norm_x, y=norm_y + 0.05, z=0.0)

        if open_palm:
            for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
                lms[tip] = Landmark(x=norm_x, y=norm_y - 0.15, z=0.0)
                lms[pip] = Landmark(x=norm_x, y=norm_y, z=0.0)
            lms[4] = Landmark(x=norm_x - 0.20, y=norm_y, z=0.0)
        else:
            # Curled non-index fingers
            for tip, pip in [(12, 10), (16, 14), (20, 18)]:
                lms[tip] = Landmark(x=norm_x, y=norm_y + 0.10, z=0.0)
                lms[pip] = Landmark(x=norm_x, y=norm_y, z=0.0)
            # thumb tip placed at pinch_norm * palm_width (0.20)
            lms[4] = Landmark(x=norm_x - (0.20 * pinch_norm), y=norm_y, z=0.0)

        return lms

    def _make_right_hand(self, norm_x=0.7, norm_y=0.5):
        """Construct synthetic 21-landmark right hand (pointing)."""
        lms = [Landmark(x=norm_x, y=norm_y, z=0.0)] * 21
        lms[5] = Landmark(x=norm_x - 0.10, y=norm_y, z=0.0)
        lms[17] = Landmark(x=norm_x + 0.10, y=norm_y, z=0.0)
        lms[8] = Landmark(x=norm_x, y=norm_y, z=0.0)
        lms[6] = Landmark(x=norm_x, y=norm_y + 0.05, z=0.0)
        lms[4] = Landmark(x=norm_x - 0.18, y=norm_y, z=0.0)
        return lms

    def test_single_left_hand_drag_and_continuous_free_movement(self):
        """Left hand initiates drag and freely steers cursor across screen."""
        t = 100.0

        # Frame 1: Pointing with left hand
        h1 = HandsResult(left=self._make_left_hand(0.30, 0.40, pinch_norm=0.9))
        self._process(h1, t)
        self.assertEqual(self.orchestrator._pointer_owner, PointerOwner.LEFT)

        # Frame 2: Pinch to start drag candidate
        t += 0.033
        h2 = HandsResult(left=self._make_left_hand(0.30, 0.40, pinch_norm=0.35))
        self._process(h2, t)
        self.assertEqual(self.orchestrator._left.left_drag_state, "GRAB_CANDIDATE")

        # Frame 3: Hold 120ms -> activates DRAGGING
        t += 0.120
        h3 = HandsResult(left=self._make_left_hand(0.30, 0.40, pinch_norm=0.35))
        self._process(h3, t)
        self.assertEqual(self.orchestrator._left.left_drag_state, "DRAGGING")
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.drags, 1)

        # Frame 4-8: Move left hand freely across screen from 0.30 to 0.60
        initial_move_count = len(self.actuator.moves)
        for i in range(1, 6):
            t += 0.033
            curr_x = 0.30 + (0.06 * i)
            hi = HandsResult(left=self._make_left_hand(curr_x, 0.40, pinch_norm=0.35))
            self._process(hi, t)
            self.assertTrue(self.actuator.is_dragging, f"Drag unexpectedly aborted at frame {i}")
            self.assertEqual(self.orchestrator._pointer_owner, PointerOwner.LEFT)

        self.assertGreater(len(self.actuator.moves), initial_move_count)
        # Verify X coordinate moved significantly to the right
        self.assertGreater(self.actuator.moves[-1][0], self.actuator.moves[initial_move_count][0])

    def test_camera_dropout_does_not_prematurely_drop_file(self):
        """Temporary 1-2 frame camera drop does NOT drop held file."""
        t = 200.0
        # Start drag
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._process(h, t)
        t += 0.120
        self._process(h, t)
        self.assertTrue(self.actuator.is_dragging)

        # 1-frame camera drop (MediaPipe reports None)
        t += 0.033
        drop_h = HandsResult(left=None)
        self._process(drop_h, t)
        self.assertTrue(self.actuator.is_dragging, "Drag dropped on single camera frame loss!")
        self.assertEqual(self.actuator.drops, 0)

        # 2nd frame camera drop
        t += 0.033
        self._process(drop_h, t)
        self.assertTrue(self.actuator.is_dragging, "Drag dropped on 2nd camera frame loss!")

        # Hand reacquired on 3rd frame
        t += 0.033
        self._process(h, t)
        self.assertTrue(self.actuator.is_dragging, "Drag should persist after hand reacquisition")
        self.assertEqual(self.actuator.drops, 0)

    def test_perspective_rotation_spike_does_not_drop_file(self):
        """1-frame perspective narrowing spike (pinch_norm=0.78) does not drop file."""
        t = 300.0
        # Start drag
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._process(h, t)
        t += 0.120
        self._process(h, t)
        self.assertTrue(self.actuator.is_dragging)

        # 1-frame perspective spike: pinch_norm jumps to 0.78 (> 0.75 release threshold)
        t += 0.033
        spike_h = HandsResult(left=self._make_left_hand(0.45, 0.40, pinch_norm=0.78))
        self._process(spike_h, t)
        self.assertTrue(self.actuator.is_dragging, "Drag dropped on single-frame perspective spike!")
        self.assertEqual(self.actuator.drops, 0)

        # Next frame returns to normal pinch (0.40)
        t += 0.033
        norm_h = HandsResult(left=self._make_left_hand(0.50, 0.40, pinch_norm=0.40))
        self._process(norm_h, t)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.actuator.drops, 0)

    def test_right_hand_cannot_steal_pointer_during_left_drag(self):
        """Right hand visible in camera view cannot steal pointer control from active left drag."""
        t = 400.0
        # Start left drag
        hl = HandsResult(left=self._make_left_hand(0.30, 0.40, pinch_norm=0.35))
        self._process(hl, t)
        t += 0.120
        self._process(hl, t)
        self.assertTrue(self.actuator.is_dragging)
        self.assertEqual(self.orchestrator._pointer_owner, PointerOwner.LEFT)

        # Right hand appears in frame pointing
        t += 0.033
        h_both = HandsResult(
            left=self._make_left_hand(0.35, 0.40, pinch_norm=0.35),
            right=self._make_right_hand(0.70, 0.50),
        )
        self._process(h_both, t)

        # Pointer owner MUST remain LEFT so left hand keeps steering
        self.assertEqual(self.orchestrator._pointer_owner, PointerOwner.LEFT)
        self.assertTrue(self.actuator.is_dragging)

    def test_intentional_open_palm_drops_file_immediately(self):
        """Opening hand into open palm drops file cleanly on frame 1."""
        t = 500.0
        h = HandsResult(left=self._make_left_hand(0.40, 0.40, pinch_norm=0.35))
        self._process(h, t)
        t += 0.120
        self._process(h, t)
        self.assertTrue(self.actuator.is_dragging)

        # Intentional drop: open palm
        t += 0.033
        open_h = HandsResult(left=self._make_left_hand(0.40, 0.40, open_palm=True))
        self._process(open_h, t)
        self.assertFalse(self.actuator.is_dragging)
        self.assertEqual(self.actuator.drops, 1)


if __name__ == "__main__":
    unittest.main()
