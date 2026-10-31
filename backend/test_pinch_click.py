import unittest
import time
from core.tracker import Landmark
from core.gestures.right_hand import RightHandProcessor, _State
from core.actuator import MouseActuator
from core.display import VirtualDesktop, TrackpadZone
import config

class DummyActuator(MouseActuator):
    def __init__(self):
        self.clicks = 0
        self.moves = 0
        self.double_clicks = 0
        self.click_coords: list[tuple[int | None, int | None]] = []
        
    def left_click(self, x: int | None = None, y: int | None = None) -> bool:
        self.clicks += 1
        self.click_coords.append((x, y))
        return True

    def move(self, x: int, y: int) -> bool:
        self.moves += 1
        return True

    def double_click(self, x: int | None = None, y: int | None = None) -> bool:
        self.double_clicks += 1
        self.left_click(x, y)
        return True

    def drag_start(self) -> None: pass
    def drag_end(self) -> None: pass

class TestPinchClick(unittest.TestCase):
    def setUp(self):
        config.POINTER_ONLY_MODE = False
        config.PINCH_CLICK_ENABLED = True
        config.DRAG_ENABLED = False
        config.PINCH_START_NORM_DIST = 0.50
        config.PINCH_RELEASE_NORM_DIST = 0.80
        config.PINCH_CONFIRM_S = 0.10
        config.PINCH_COOLDOWN_S = 0.1
        config.SINGLE_CLICK_MODE = "instant"
        
        self.actuator = DummyActuator()
        self.processor = RightHandProcessor(self.actuator, VirtualDesktop(1920, 1080, 1), TrackpadZone(0, 640, 0, 480))

    def make_hand(self, pinch_dist_norm, x_offset=0.0, y_offset=0.0):
        from core.tracker import HandsResult
        lms = [Landmark(x=0.5 + x_offset, y=0.5 + y_offset, z=0.0)] * 21
        lms[5] = Landmark(x=0.4 + x_offset, y=0.5 + y_offset, z=0.0)
        lms[17] = Landmark(x=0.6 + x_offset, y=0.5 + y_offset, z=0.0)
        lms[8] = Landmark(x=0.5 + x_offset, y=0.5 + y_offset, z=0.0)
        lms[4] = Landmark(x=0.5 + x_offset + (0.2 * pinch_dist_norm), y=0.5 + y_offset, z=0.0)
        return lms

    def test_pinch_candidate(self):
        self.processor.process(self.make_hand(0.4))
        self.assertEqual(self.processor._state, _State.PINCH_CANDIDATE)
        time.sleep(0.05)
        self.processor.process(self.make_hand(0.9)) # release early
        self.assertEqual(self.processor._state, _State.IDLE)
        self.assertEqual(self.actuator.clicks, 0) # Not confirmed yet

    def test_pinch_and_release(self):
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.processor.process(self.make_hand(0.9)) # Release it
        self.assertEqual(self.processor._state, _State.IDLE)
        self.assertEqual(self.actuator.clicks, 1)

    def test_cooldown(self):
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.processor.process(self.make_hand(0.9)) # Clicked and Released
        
        self.processor.process(self.make_hand(0.4)) # Try again immediately
        self.assertEqual(self.processor.click_state_text, "COOLDOWN")

    def test_no_repeated_clicks(self):
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        
        # Hold pinch across multiple frames
        for _ in range(5):
            self.processor.process(self.make_hand(0.3))
            
        self.processor.process(self.make_hand(0.9)) # Release
        self.assertEqual(self.actuator.clicks, 1) # NO repeated clicks

    def test_double_click_snap(self):
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.processor.process(self.make_hand(0.9)) # Release 1
        pos1 = self.processor._locked_cursor_pos
        
        time.sleep(0.15) 
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.processor.process(self.make_hand(0.9)) # Release 2
        
        self.assertEqual(self.actuator.clicks, 2)
        pass

    def test_double_click_outside_time(self):
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.processor.process(self.make_hand(0.9))
        
        time.sleep(0.8) 
        
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.processor.process(self.make_hand(0.9))
        
        self.assertEqual(self.processor.click_state_text, "READY")

    def test_rapid_second_tap_registers_double_click(self):
        # 1st Click
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.assertEqual(self.actuator.clicks, 1)
        
        # Release 1
        self.processor.process(self.make_hand(0.9))
        self.assertEqual(self.processor._state, _State.IDLE)
        
        time.sleep(0.15) # Wait past cooldown
        
        # 2nd Click: rapid single-frame tap in the air
        self.processor.process(self.make_hand(0.4))
        # Instant confirmation registers Click 2 immediately on first frame of contact!
        self.assertEqual(self.actuator.clicks, 2)
        self.assertEqual(self.processor.click_state_text, "DOUBLE CLICK")
        
        # Rapid release after 1 frame
        self.processor.process(self.make_hand(0.9))
        self.assertEqual(self.processor._state, _State.IDLE)
        self.assertEqual(self.actuator.clicks, 2)

    def test_double_click_outside_position_tolerance(self):
        # 1st Click at center (x_offset=0)
        self.processor.process(self.make_hand(0.4, x_offset=0.0))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4, x_offset=0.0))
        self.assertEqual(self.actuator.clicks, 1)
        self.assertEqual(self.processor.click_state_text, "SINGLE CLICK")
        
        # Release
        self.processor.process(self.make_hand(0.9, x_offset=0.0))
        
        time.sleep(0.15)
        
        # 2nd Click far away (x_offset=0.3 -> > 500px away)
        self.processor.process(self.make_hand(0.4, x_offset=0.3))
        # Should NOT be an instant double click because it's far outside DOUBLE_CLICK_POSITION_TOLERANCE_PX
        self.assertEqual(self.processor._state, _State.PINCH_CANDIDATE)
        self.assertEqual(self.actuator.clicks, 1) # Still 1 click

    def test_sustained_pinch_after_double_click(self):
        # 1st Click
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.processor.process(self.make_hand(0.9))
        
        time.sleep(0.15)
        
        # 2nd Click
        self.processor.process(self.make_hand(0.4))
        self.assertEqual(self.actuator.clicks, 2)
        
        # Hold second pinch across 5 consecutive frames
        for _ in range(5):
            self.processor.process(self.make_hand(0.3))
            self.assertEqual(self.actuator.clicks, 2) # Strictly NO triple click or repeated click
            
        self.processor.process(self.make_hand(0.9))
        self.assertEqual(self.processor._state, _State.IDLE)
        self.assertEqual(self.actuator.clicks, 2)

    def test_tracking_loss_resets_double_click_state(self):
        # 1st Click
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.processor.process(self.make_hand(0.9))
        self.assertEqual(self.actuator.clicks, 1)
        
        # Hand drops out of frame
        self.processor.process(None)
        self.assertIsNone(self.processor._last_click_pos)
        self.assertEqual(self.processor._last_click_time, 0.0)
        
        # Hand reappears and pinches
        self.processor.process(self.make_hand(0.4))
        # Should be a fresh candidate, not an instant double-click
        self.assertEqual(self.processor._state, _State.PINCH_CANDIDATE)
        self.assertEqual(self.actuator.clicks, 1)

    def test_click_coordinates_passed_and_identical(self):
        # 1st Click
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.assertEqual(self.actuator.clicks, 1)
        self.assertEqual(len(self.actuator.click_coords), 1)
        c1_x, c1_y = self.actuator.click_coords[0]
        self.assertIsNotNone(c1_x)
        self.assertIsNotNone(c1_y)

        # Release 1 with slight natural air wobble (0.01 offset ~ 19px)
        self.processor.process(self.make_hand(0.9, x_offset=0.01))
        self.assertEqual(self.processor._state, _State.IDLE)
        self.assertFalse(self.processor.is_cursor_locked)

        time.sleep(0.15) # Wait past cooldown, well within 500ms double click window

        # 2nd Click (pinch contact at 0.01 offset)
        self.processor.process(self.make_hand(0.4, x_offset=0.01))
        self.assertEqual(self.actuator.clicks, 2)
        self.assertEqual(len(self.actuator.click_coords), 2)
        c2_x, c2_y = self.actuator.click_coords[1]

        # Both clicks MUST have the exact identical coordinates (snapped for native OS double click)
        self.assertEqual((c1_x, c1_y), (c2_x, c2_y))

    def test_real_actuator_coordinate_click(self):
        real_actuator = MouseActuator(1920, 1080)
        # Calling left_click with coordinates returns bool (mocking native send_input under test guard)
        from unittest.mock import patch
        with patch("core.actuator._send_input", return_value=True):
            res = real_actuator.left_click(100, 100)
            self.assertIsInstance(res, bool)

    def test_pinch_hold_triggers_double_click(self):
        # 1. First pinch contact
        self.processor.process(self.make_hand(0.4))
        time.sleep(0.12)
        self.processor.process(self.make_hand(0.4))
        self.assertEqual(self.actuator.clicks, 1)
        self.assertEqual(self.processor._state, _State.PINCH_LOCKED)
        
        # 2. Hold pinch for 380ms (> PINCH_HOLD_DOUBLE_CLICK_S = 0.35s)
        time.sleep(0.38)
        self.processor.process(self.make_hand(0.4))
        
        # 3. Verify double-click fired from the hold!
        self.assertEqual(self.actuator.clicks, 2)
        self.assertEqual(self.actuator.double_clicks, 1)
        self.assertEqual(self.processor.click_state_text, "DOUBLE CLICK")
        
        # 4. Sustained hold across more frames does NOT repeat or triple click
        for _ in range(5):
            self.processor.process(self.make_hand(0.35))
            self.assertEqual(self.actuator.clicks, 2)
            
        # 5. Release returns cleanly to IDLE
        self.processor.process(self.make_hand(0.9))
        self.assertEqual(self.processor._state, _State.IDLE)
        self.assertEqual(self.processor.click_state_text, "READY")

