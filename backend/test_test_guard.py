# test_test_guard.py
"""
Dedicated self-test for test_guard.py.
Proves that every protected native API raises BlockedOSActionError:
1. SendInput
2. SetCursorPos
3. mouse_event
4. keybd_event
5. pynput.mouse.Controller instantiation
6. pynput.keyboard.Controller instantiation
7. LockWorkStation
8. os.startfile
9. subprocess.Popen
10. cv2.VideoCapture with integer device index (e.g. 0)
11. cv2.VideoCapture with string filename (allowed to proceed without BlockedOSActionError)
"""

import os
import subprocess
import unittest
import ctypes

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pynput
except ImportError:
    pynput = None

from test_guard import install_test_guard, uninstall_test_guard, BlockedOSActionError


class TestTestGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        install_test_guard()

    def test_send_input_blocked(self):
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            with self.assertRaises(BlockedOSActionError):
                ctypes.windll.user32.SendInput(0, 0, 0)

        # Also via WinDLL
        u32 = ctypes.WinDLL("user32")
        with self.assertRaises(BlockedOSActionError):
            u32.SendInput(0, 0, 0)

    def test_set_cursor_pos_blocked(self):
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            with self.assertRaises(BlockedOSActionError):
                ctypes.windll.user32.SetCursorPos(100, 100)

        u32 = ctypes.WinDLL("user32")
        with self.assertRaises(BlockedOSActionError):
            u32.SetCursorPos(100, 100)

    def test_mouse_event_blocked(self):
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            with self.assertRaises(BlockedOSActionError):
                ctypes.windll.user32.mouse_event(0, 0, 0, 0, 0)

        u32 = ctypes.WinDLL("user32")
        with self.assertRaises(BlockedOSActionError):
            u32.mouse_event(0, 0, 0, 0, 0)

    def test_keybd_event_blocked(self):
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            with self.assertRaises(BlockedOSActionError):
                ctypes.windll.user32.keybd_event(0, 0, 0, 0)

        u32 = ctypes.WinDLL("user32")
        with self.assertRaises(BlockedOSActionError):
            u32.keybd_event(0, 0, 0, 0)

    def test_lock_workstation_blocked(self):
        if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
            with self.assertRaises(BlockedOSActionError):
                ctypes.windll.user32.LockWorkStation()

        u32 = ctypes.WinDLL("user32")
        with self.assertRaises(BlockedOSActionError):
            u32.LockWorkStation()

    def test_pynput_mouse_controller_blocked(self):
        if pynput is not None:
            with self.assertRaises(BlockedOSActionError):
                pynput.mouse.Controller()

    def test_pynput_keyboard_controller_blocked(self):
        if pynput is not None:
            with self.assertRaises(BlockedOSActionError):
                pynput.keyboard.Controller()

    def test_startfile_blocked(self):
        if hasattr(os, "startfile"):
            with self.assertRaises(BlockedOSActionError):
                os.startfile("whatsapp:")

    def test_subprocess_popen_blocked(self):
        with self.assertRaises(BlockedOSActionError):
            subprocess.Popen(["explorer.exe"])

    def test_cv2_videocapture_integer_index_blocked(self):
        if cv2 is not None:
            with self.assertRaises(BlockedOSActionError):
                cv2.VideoCapture(0)

            with self.assertRaises(BlockedOSActionError):
                cv2.VideoCapture(1, cv2.CAP_DSHOW)

    def test_cv2_videocapture_string_filepath_allowed(self):
        if cv2 is not None:
            # String file path should NOT raise BlockedOSActionError (it returns VideoCapture object)
            try:
                cap = cv2.VideoCapture("nonexistent_test_clip.mp4")
                if cap is not None:
                    cap.release()
            except BlockedOSActionError:
                self.fail("cv2.VideoCapture with string filename should be allowed, but raised BlockedOSActionError!")
            except Exception:
                # Other normal cv2/file exceptions are fine; only BlockedOSActionError is forbidden
                pass

    def test_get_cursor_pos_simulated_default(self):
        from ctypes import wintypes
        from test_guard import reset_test_guard_cursor_state

        reset_test_guard_cursor_state()
        u32 = ctypes.WinDLL("user32")
        pt = wintypes.POINT()
        ok = u32.GetCursorPos(ctypes.byref(pt))
        self.assertEqual(ok, 1)
        self.assertEqual((pt.x, pt.y), (960, 540))

    def test_get_cursor_pos_custom_simulation_and_failure(self):
        from ctypes import wintypes
        from test_guard import (
            set_simulated_cursor_pos,
            set_simulated_cursor_query_result,
            reset_test_guard_cursor_state,
        )

        try:
            # Custom simulated position
            set_simulated_cursor_pos((300, 400))
            u32 = ctypes.WinDLL("user32")
            pt = wintypes.POINT()
            ok = u32.GetCursorPos(ctypes.byref(pt))
            self.assertEqual(ok, 1)
            self.assertEqual((pt.x, pt.y), (300, 400))

            # Simulate API failure
            set_simulated_cursor_query_result(0)
            ok_fail = u32.GetCursorPos(ctypes.byref(pt))
            self.assertEqual(ok_fail, 0)
        finally:
            reset_test_guard_cursor_state()


if __name__ == "__main__":
    unittest.main()
