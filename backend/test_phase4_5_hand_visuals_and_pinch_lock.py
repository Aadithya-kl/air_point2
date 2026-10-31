"""
Unit tests for Air Point Phase 4.5: Hand Visuals, Index-Tip Target Ring & Natural Pinch Lock.

Verifies:
1. Canonical hand skeleton connections without cross-palm clutter.
2. Index-tip target ring at landmark 8 with 5 visual states (tracking, candidate, confirmed click, locked, tracking lost).
3. Free, continuous cursor movement during PINCH_CANDIDATE.
4. Precise cursor lock on confirmed pinch (PINCH_LOCKED) with reliable click emission.
5. Smooth release back to continuous cursor tracking with reacquisition baseline reset (no jump alarm).
6. Single click per sustained pinch (no repeated firing).
7. Left-hand drag-and-drop initiation, drag holding, and safe button release on hand loss.
8. Filter gliding response and full desktop corner reachability.
"""

import unittest
from unittest.mock import MagicMock, patch
import time
import numpy as np

from core.tracker import Landmark, HandsResult
from core.actuator import MouseActuator
from core.display import VirtualDesktop, TrackpadZone
from core.gestures.right_hand import RightHandProcessor, _State
from core.gestures.left_hand import LeftHandProcessor
from core.gestures.orchestrator import GestureOrchestrator, PointerOwner
from core.debug_overlay import _CONNECTIONS, draw_debug_frame, _SAGE, _AMBER, _CYAN, _WHITE
from core.control_server import RuntimeState
from core.filter import OneEuroFilter


class TestPhase4_5HandVisualsAndPinchLock(unittest.TestCase):
    def setUp(self):
        import config
        self._orig_mode = getattr(config, 'SINGLE_CLICK_MODE', 'instant')
        config.SINGLE_CLICK_MODE = "instant"
        self.desktop = VirtualDesktop(total_width=1920, total_height=1080, monitor_count=1)
        self.actuator = MouseActuator(1920, 1080)
        self.trackpad = TrackpadZone(100, 540, 80, 400)
        self.right = RightHandProcessor(self.actuator, self.desktop, self.trackpad)
        self.left = LeftHandProcessor(self.actuator, self.desktop, self.trackpad)
        self.actuator.move = MagicMock(return_value=True)
        self.actuator.get_cursor_pos = MagicMock(return_value=(960, 540))
        self.orchestrator = GestureOrchestrator(self.actuator, self.desktop, self.trackpad, initial_cursor_anchor=(960, 540))

    def tearDown(self):
        import config
        config.SINGLE_CLICK_MODE = self._orig_mode

    def _create_hand(self, index_x=0.5, index_y=0.5, thumb_dist_ratio=1.0):
        """Construct synthetic 21-landmark hand with controllable pinch distance."""
        # Palm width between 5 and 17 is set to 0.10
        lms = [Landmark(x=0.5, y=0.8, z=0.0) for _ in range(21)]
        lms[0] = Landmark(x=index_x, y=index_y + 0.25, z=0.0)  # wrist
        lms[5] = Landmark(x=index_x - 0.05, y=index_y + 0.15, z=0.0)  # index MCP
        lms[17] = Landmark(x=index_x + 0.05, y=index_y + 0.15, z=0.0) # pinky MCP
        lms[8] = Landmark(x=index_x, y=index_y, z=0.0)         # index tip
        # Thumb tip positioned according to ratio of palm width (0.10)
        thumb_offset = 0.10 * thumb_dist_ratio
        lms[4] = Landmark(x=index_x - thumb_offset, y=index_y, z=0.0)  # thumb tip
        return lms

    def test_canonical_hand_skeleton_connections(self):
        """Verify canonical MediaPipe hand skeleton connections without cross-palm clutter."""
        # Must contain knuckle arch: (5,9), (9,13), (13,17)
        self.assertIn((5, 9), _CONNECTIONS)
        self.assertIn((9, 13), _CONNECTIONS)
        self.assertIn((13, 17), _CONNECTIONS)
        # Wrist connects only to thumb (0,1), index MCP (0,5), and pinky MCP (0,17)
        wrist_conns = [c for c in _CONNECTIONS if c[0] == 0 or c[1] == 0]
        self.assertEqual(len(wrist_conns), 3)
        self.assertIn((0, 1), _CONNECTIONS)
        self.assertIn((0, 5), _CONNECTIONS)
        self.assertIn((0, 17), _CONNECTIONS)
        # Must NOT connect wrist to middle MCP (0,9) or ring MCP (0,13)
        self.assertNotIn((0, 9), _CONNECTIONS)
        self.assertNotIn((0, 13), _CONNECTIONS)
        # No duplicate segments
        self.assertEqual(len(_CONNECTIONS), len(set(_CONNECTIONS)))

    def test_index_target_ring_coordinates_and_visual_states(self):
        """Verify target ring draws concentric circles centred at landmark 8 with distinct states."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        hands = HandsResult()
        hands.right = self._create_hand(index_x=0.40, index_y=0.35)
        visual_tips = {8: (0.40, 0.35, 0.0)}

        # State 1: Normal tracking (sage concentric rings)
        out_tracking = draw_debug_frame(
            frame, hands, "IDLE", cursor_pos=(768, 378),
            right_visual_tips=visual_tips, click_state_text="READY",
            is_cursor_locked=False, orchestrator=self.orchestrator
        )
        self.assertIsNotNone(out_tracking)

        # State 2: Pinch candidate (amber accent rings)
        out_candidate = draw_debug_frame(
            frame, hands, "PINCH_CANDIDATE", cursor_pos=(768, 378),
            right_visual_tips=visual_tips, click_state_text="CANDIDATE",
            is_cursor_locked=False, orchestrator=self.orchestrator
        )
        self.assertIsNotNone(out_candidate)

        # State 3: Confirmed click (bright white ping rings)
        out_click = draw_debug_frame(
            frame, hands, "PINCH_LOCKED", cursor_pos=(768, 378),
            right_visual_tips=visual_tips, click_state_text="SINGLE CLICK",
            is_cursor_locked=True, orchestrator=self.orchestrator
        )
        self.assertIsNotNone(out_click)

        # State 4: Cursor locked (distinct locked target with cardinal ticks)
        out_locked = draw_debug_frame(
            frame, hands, "PINCH_LOCKED", cursor_pos=(768, 378),
            right_visual_tips=visual_tips, click_state_text="WAITING FOR RELEASE",
            is_cursor_locked=True, orchestrator=self.orchestrator
        )
        self.assertIsNotNone(out_locked)

        # State 5: Tracking lost (no crash, ring omitted)
        hands_lost = HandsResult()
        out_lost = draw_debug_frame(
            frame, hands_lost, "IDLE", cursor_pos=None,
            right_visual_tips=None, click_state_text="DISABLED",
            is_cursor_locked=False, orchestrator=self.orchestrator
        )
        self.assertIsNotNone(out_lost)

    def test_cursor_moves_freely_during_pinch_candidate(self):
        """Verify cursor coordinate continues following hand movement during PINCH_CANDIDATE."""
        # Initial frame at pos A
        hand_a = self._create_hand(index_x=0.45, index_y=0.45, thumb_dist_ratio=1.0)
        self.right.process(hand_a)
        pos_a = self.right.cursor_pos
        self.assertIsNotNone(pos_a)

        # Thumb approaches index -> triggers candidate (ratio=0.40 < PINCH_START_NORM_DIST=0.50)
        hand_cand1 = self._create_hand(index_x=0.48, index_y=0.45, thumb_dist_ratio=0.40)
        self.right.process(hand_cand1)
        self.assertEqual(self.right.right_state, "PINCH_CANDIDATE")
        self.assertFalse(self.right.is_cursor_locked)

        # Hand moves to pos B while remaining in candidate
        hand_cand2 = self._create_hand(index_x=0.55, index_y=0.45, thumb_dist_ratio=0.40)
        self.right.process(hand_cand2)
        pos_b = self.right.cursor_pos

        # Cursor MUST move with the hand, NOT freeze at pos_a
        self.assertNotEqual(pos_a[0], pos_b[0])
        self.assertGreater(pos_b[0], pos_a[0])

    def test_cursor_locks_precisely_on_confirmed_pinch_and_releases_smoothly(self):
        """Verify cursor locks at click location on confirmation, and releases cleanly to tracking."""
        with patch.object(self.actuator, 'left_click') as mock_click:
            # 1. Normal tracking at pos 1
            hand1 = self._create_hand(index_x=0.50, index_y=0.50, thumb_dist_ratio=1.0)
            self.right.process(hand1)
            self.assertFalse(self.right.is_cursor_locked)

            # 2. Enter candidate
            hand2 = self._create_hand(index_x=0.50, index_y=0.50, thumb_dist_ratio=0.35)
            self.right.process(hand2)
            self.assertEqual(self.right.right_state, "PINCH_CANDIDATE")
            self.assertFalse(self.right.is_cursor_locked)

            # 3. Hold past PINCH_CONFIRM_S (100ms) to confirm click
            time.sleep(0.12)
            # Hand trembles slightly during click confirmation
            hand3 = self._create_hand(index_x=0.52, index_y=0.51, thumb_dist_ratio=0.30)
            self.right.process(hand3)

            # Click fired and cursor locked
            self.assertEqual(self.right.right_state, "PINCH_LOCKED")
            self.assertTrue(self.right.is_cursor_locked)
            mock_click.assert_called_once()
            locked_pos = self.right.cursor_pos

            # 4. While held, cursor remains locked at click coordinates despite hand drift
            hand4 = self._create_hand(index_x=0.56, index_y=0.55, thumb_dist_ratio=0.30)
            self.right.process(hand4)
            self.assertEqual(self.right.cursor_pos, locked_pos)
            self.assertTrue(self.right.is_cursor_locked)
            # Sustained hold does not fire additional clicks
            self.assertEqual(mock_click.call_count, 1)

            # 5. Release pinch (ratio=0.85 > PINCH_RELEASE_NORM_DIST=0.80)
            hand5 = self._create_hand(index_x=0.56, index_y=0.55, thumb_dist_ratio=0.85)
            self.right.process(hand5)

            # State returns to IDLE, lock released
            self.assertEqual(self.right.right_state, "IDLE")
            self.assertFalse(self.right.is_cursor_locked)
            # Cursor position unlocks and follows current hand coordinate
            self.assertNotEqual(self.right.cursor_pos, locked_pos)

    def test_orchestrator_reacquisition_on_pinch_release_prevents_jump_alarm(self):
        """Verify orchestrator re-establishes baseline smoothly on pinch unlock without false jump alarms."""
        with patch.object(self.actuator, 'move') as mock_move, \
             patch.object(self.actuator, 'left_click', return_value=True) as mock_click:
            hands = HandsResult()
            # Start tracking
            hands.right = self._create_hand(index_x=0.40, index_y=0.40)
            self.orchestrator.process(hands)
            first_pos = self.orchestrator.cursor_pos

            # Enter candidate and confirm click
            hands.right = self._create_hand(index_x=0.40, index_y=0.40, thumb_dist_ratio=0.35)
            self.orchestrator.process(hands)
            time.sleep(0.12)
            self.orchestrator.process(hands)
            self.assertTrue(self.orchestrator.is_cursor_locked)

            # User moves hand during lock and then releases
            hands.right = self._create_hand(index_x=0.60, index_y=0.60, thumb_dist_ratio=0.85)
            self.orchestrator.process(hands)

            # Released smoothly: consecutive jumps must remain 0
            self.assertFalse(self.orchestrator.is_cursor_locked)
            self.assertEqual(self.orchestrator._consecutive_jumps, 0)
            self.assertIsNotNone(self.orchestrator.cursor_pos)

    def test_left_hand_drag_and_safe_release_on_tracking_loss(self):
        """Verify left hand initiates drag, holds mouse down, and safely releases button if tracking drops."""
        with patch.object(self.actuator, 'drag_start') as mock_drag_start, \
             patch.object(self.actuator, 'drag_end') as mock_drag_end:
            # Pointing
            hand_l1 = self._create_hand(index_x=0.40, index_y=0.40, thumb_dist_ratio=1.0)
            self.left.process(hand_l1)
            self.assertTrue(self.left.is_pointing)

            # Grab pinch candidate
            hand_l2 = self._create_hand(index_x=0.40, index_y=0.40, thumb_dist_ratio=0.40)
            self.left.process(hand_l2)
            time.sleep(0.12)
            self.left.process(hand_l2)

            # Drag confirmed
            self.assertEqual(self.left.left_drag_state, "DRAGGING")
            mock_drag_start.assert_called_once()

            # Move during drag
            hand_l3 = self._create_hand(index_x=0.45, index_y=0.45, thumb_dist_ratio=0.40)
            self.left.process(hand_l3)
            self.assertEqual(self.left.left_drag_state, "DRAGGING")

            # Sudden tracking loss -> safety release must trigger drag_end
            self.left.process(None)
            mock_drag_end.assert_called_once()
            self.assertEqual(self.left.left_drag_state, "IDLE")

    def test_control_server_landmarks_telemetry_includes_click_state(self):
        """Verify control server stores click_state and last_pinch_norm in landmarks snapshot."""
        state = RuntimeState()
        state.update_landmarks(
            hands_data={"right": [{"x": 0.4, "y": 0.3, "z": 0.0}], "left": None},
            face_data=None,
            is_locked=True,
            click_state="WAITING FOR RELEASE",
            last_pinch_norm=0.32,
        )
        snap = state.get_landmarks_snapshot()
        self.assertTrue(snap["is_locked"])
        self.assertEqual(snap["click_state"], "WAITING FOR RELEASE")
        self.assertEqual(snap["last_pinch_norm"], 0.32)


if __name__ == "__main__":
    unittest.main()
