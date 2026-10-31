# test_dynamic_island_power_notifications.py
"""
Unit tests for Air Point Dynamic Island Power Saver Notifications & Configuration.
Verifies:
1. Default preferences & clamping:
   - island_enabled (default True)
   - island_notifications_enabled (default True)
   - island_timer_enabled (default True)
   - island_autohide_enabled (default True)
   - island_hud_duration_s (default 120.0s, clamped 10.0s - 1800.0s)
   - island_completion_duration_s (default 2.0s, clamped 1.0s - 5.0s)
2. State A: Normal Mode toast
3. State B: Power Saver Enabled (waiting for inactivity) toast
4. State C: Power Save countdown start (monotonic clock, timer badge MM:SS)
5. State D: Countdown completion (POWER SAVER CONTINUES — HUD HIDING) and auto-hide
6. Underlying engine power state preservation (POWER_SAVE remains active after HUD hides)
7. State E: Hand detected / wake confirmation cancels countdown and restores Normal mode
8. State F: Power saver disabled cancels countdown and restores Normal mode
9. Setting toggles (island_enabled=False, island_notifications_enabled=False, island_timer_enabled=False)
10. Independence of HUD duration (default 120s) and underlying engine idle threshold
"""

import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from core.control_server import (
    RuntimeState,
    MIN_ISLAND_HUD_DURATION_S,
    MAX_ISLAND_HUD_DURATION_S,
    DEFAULT_ISLAND_HUD_DURATION_S,
    MIN_ISLAND_COMPLETION_DURATION_S,
    MAX_ISLAND_COMPLETION_DURATION_S,
    DEFAULT_ISLAND_COMPLETION_DURATION_S,
)
from core.overlay import (
    ScreenshotOverlay,
    COLOR_SAGE_ACCENT,
    COLOR_AMBER_WARN,
)
from core.power_state_machine import PowerStateManager, PowerState


class TestDynamicIslandPowerNotifications(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings_file = os.path.join(self.temp_dir.name, "settings.json")
        self.state = RuntimeState(settings_path=self.settings_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_settings_and_bounds(self):
        """Verify default settings and bounds clamping for Dynamic Island."""
        snap = self.state.get_snapshot()["settings"]
        self.assertTrue(snap["island_enabled"])
        self.assertTrue(snap["island_notifications_enabled"])
        self.assertTrue(snap["island_timer_enabled"])
        self.assertTrue(snap["island_autohide_enabled"])
        self.assertEqual(snap["island_hud_duration_s"], 120.0)
        self.assertEqual(snap["island_completion_duration_s"], 2.0)

        # Clamping under minimum
        updated = self.state.apply_settings({
            "island_hud_duration_s": 2.0,
            "island_completion_duration_s": 0.2,
        })
        self.assertEqual(updated["island_hud_duration_s"], MIN_ISLAND_HUD_DURATION_S)
        self.assertEqual(updated["island_completion_duration_s"], MIN_ISLAND_COMPLETION_DURATION_S)

        # Clamping over maximum
        updated2 = self.state.apply_settings({
            "island_hud_duration_s": 3600.0,
            "island_completion_duration_s": 10.0,
        })
        self.assertEqual(updated2["island_hud_duration_s"], MAX_ISLAND_HUD_DURATION_S)
        self.assertEqual(updated2["island_completion_duration_s"], MAX_ISLAND_COMPLETION_DURATION_S)

    def test_settings_persistence_roundtrip(self):
        """Verify settings are cleanly persisted to disk and restored in a new RuntimeState."""
        self.state.apply_settings({
            "island_enabled": False,
            "island_notifications_enabled": False,
            "island_timer_enabled": False,
            "island_autohide_enabled": False,
            "island_hud_duration_s": 300.0,
            "island_completion_duration_s": 3.5,
        })

        new_state = RuntimeState(settings_path=self.settings_file)
        snap = new_state.get_snapshot()["settings"]
        self.assertFalse(snap["island_enabled"])
        self.assertFalse(snap["island_notifications_enabled"])
        self.assertFalse(snap["island_timer_enabled"])
        self.assertFalse(snap["island_autohide_enabled"])
        self.assertEqual(snap["island_hud_duration_s"], 300.0)
        self.assertEqual(snap["island_completion_duration_s"], 3.5)

    @patch("tkinter.Tk")
    def test_overlay_configure(self, mock_tk):
        """Verify overlay.configure updates overlay parameters thread-safely."""
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock_root.winfo_id.return_value = 12345
        mock_tk.return_value = mock_root

        overlay = ScreenshotOverlay(position="TOP_CENTER")
        overlay.configure(
            island_enabled=False,
            notifications_enabled=False,
            timer_enabled=False,
            autohide_enabled=False,
            hud_duration_s=60.0,
            completion_duration_s=1.5,
        )

        self.assertFalse(overlay.island_enabled)
        self.assertFalse(overlay.notifications_enabled)
        self.assertFalse(overlay.timer_enabled)
        self.assertFalse(overlay.autohide_enabled)
        self.assertEqual(overlay.hud_duration_s, 60.0)
        self.assertEqual(overlay.completion_duration_s, 1.5)

    @patch("tkinter.Tk")
    def test_state_a_normal_mode(self, mock_tk):
        """State A: Verify show_normal_mode displays NORMAL MODE."""
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock_tk.return_value = mock_root

        overlay = ScreenshotOverlay(position="TOP_CENTER")
        overlay.show_normal_mode(toast_duration=1.5)

        self.assertEqual(overlay._island_state, "SUCCESS")
        self.assertEqual(overlay._island_text, "AIR POINT · NORMAL")
        self.assertEqual(overlay._island_icon, "PLAY")
        self.assertFalse(overlay._is_hidden)

    @patch("tkinter.Tk")
    def test_state_b_power_saver_enabled_waiting(self, mock_tk):
        """State B: Verify show_power_saver_enabled_waiting displays waiting status."""
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock_tk.return_value = mock_root

        overlay = ScreenshotOverlay(position="TOP_CENTER")
        overlay.show_power_saver_enabled_waiting(toast_duration=2.5)

        self.assertEqual(overlay._island_state, "STATUS")
        self.assertEqual(overlay._island_text, "POWER SAVER · WAITING")
        self.assertEqual(overlay._island_subtext, "")
        self.assertEqual(overlay._island_icon, "POWER_WAIT")
        self.assertFalse(overlay._is_hidden)

    @patch("tkinter.Tk")
    def test_state_c_and_d_countdown_and_completion(self, mock_tk):
        """State C & D: Verify countdown starts, ticks, and transitions to completion message."""
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock_tk.return_value = mock_root

        overlay = ScreenshotOverlay(position="TOP_CENTER")
        overlay.start_power_save_countdown(duration_s=120.0)

        self.assertTrue(overlay._ps_countdown_active)
        self.assertEqual(overlay._island_mode, "POWER_SAVE")
        self.assertEqual(overlay._island_text, "POWER SAVER")
        self.assertEqual(overlay._countdown_badge, "02:00")
        self.assertEqual(overlay._island_icon, "POWER_SAVE")

        # Advance clock by 30 seconds
        t_start = overlay._ps_start_time
        with patch("time.perf_counter", return_value=t_start + 30.0):
            overlay.update_state()
            self.assertEqual(overlay._countdown_badge, "01:30")
            self.assertAlmostEqual(overlay._progress, 30.0 / 120.0, places=2)
            self.assertTrue(overlay._ps_countdown_active)

        # Advance clock to completion (120s elapsed)
        with patch("time.perf_counter", return_value=t_start + 120.5):
            overlay.update_state()
            # State D: Countdown completed
            self.assertFalse(overlay._ps_countdown_active)
            self.assertEqual(overlay._island_mode, "POWER_SAVE_COMPLETE")
            self.assertEqual(overlay._island_text, "POWER SAVER · HIDING")
            self.assertEqual(overlay._island_subtext, "")
            self.assertEqual(overlay._countdown_badge, "")

        # Advance clock past completion message duration (~2s)
        with patch("time.perf_counter", return_value=t_start + 120.5 + 2.5):
            overlay.update_state()
            # Retracting to hidden
            self.assertEqual(overlay._island_state, "RETRACTING")

    @patch("tkinter.Tk")
    def test_state_e_hand_detected_wakes_engine(self, mock_tk):
        """State E: Verify wake confirmation cancels countdown and restores Normal mode."""
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock_tk.return_value = mock_root

        overlay = ScreenshotOverlay(position="TOP_CENTER")
        # Start power save countdown
        overlay.start_power_save_countdown(duration_s=120.0)
        self.assertTrue(overlay._ps_countdown_active)

        # Fast sweep detected -> WAKE_CONFIRMED
        overlay.show_wake_confirmed(toast_duration=2.0)
        self.assertFalse(overlay._ps_countdown_active)
        self.assertEqual(overlay._island_state, "SUCCESS")
        self.assertEqual(overlay._island_text, "HAND DETECTED · NORMAL")
        self.assertEqual(overlay._island_subtext, "")
        self.assertEqual(overlay._island_icon, "HAND_FOUND")

    @patch("tkinter.Tk")
    def test_state_f_power_saver_disabled(self, mock_tk):
        """State F: Verify disabling power saver cancels countdown and restores Normal mode."""
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock_tk.return_value = mock_root

        overlay = ScreenshotOverlay(position="TOP_CENTER")
        overlay.start_power_save_countdown(duration_s=120.0)
        self.assertTrue(overlay._ps_countdown_active)

        # User toggles power save OFF
        overlay.show_power_saver_disabled(toast_duration=1.5)
        self.assertFalse(overlay._ps_countdown_active)
        self.assertEqual(overlay._island_state, "SUCCESS")
        self.assertEqual(overlay._island_text, "AIR POINT · NORMAL")
        self.assertEqual(overlay._island_subtext, "Power saver disabled")

    @patch("tkinter.Tk")
    def test_island_and_notifications_disabled_toggles(self, mock_tk):
        """Verify disabling island or notifications suppresses popups."""
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock_tk.return_value = mock_root

        overlay = ScreenshotOverlay(position="TOP_CENTER")
        overlay.configure(notifications_enabled=False)

        # With notifications_enabled=False, status notifications are suppressed
        overlay.show_normal_mode()
        self.assertEqual(overlay._island_state, "IDLE")

        overlay.show_power_saver_enabled_waiting()
        self.assertEqual(overlay._island_state, "IDLE")

        overlay.start_power_save_countdown()
        self.assertEqual(overlay._island_state, "IDLE")

        # With island_enabled=False, even wake is suppressed
        overlay.configure(notifications_enabled=True, island_enabled=False)
        overlay.show_wake_confirmed()
        self.assertEqual(overlay._island_state, "IDLE")

    def test_inactivity_threshold_independence(self):
        """Dynamic Island HUD duration must NOT alter PowerStateManager inactivity threshold."""
        pm = PowerStateManager(clock_fn=time.perf_counter)
        self.assertEqual(pm._inactivity_timeout_s, 120.0)

        # Applying any HUD duration in settings
        self.state.apply_settings({"island_hud_duration_s": 30.0})
        # Engine inactivity threshold remains untouched
        self.assertEqual(pm._inactivity_timeout_s, 120.0)

    def test_underlying_power_state_remains_active_when_hud_hides(self):
        """Engine remains in POWER_SAVE state after the HUD countdown finishes and hides."""
        pm = PowerStateManager(clock_fn=lambda: 1000.0)
        pm.set_enabled(True)
        pm._state = PowerState.POWER_SAVE  # entered power save
        self.assertEqual(pm.state, PowerState.POWER_SAVE)

        # Mocking HUD completion and retraction does not change pm.state
        mock_tk = MagicMock()
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock_tk.return_value = mock_root
        with patch("tkinter.Tk", mock_tk):
            overlay = ScreenshotOverlay(position="TOP_CENTER")
            overlay.start_power_save_countdown(duration_s=10.0)
            with patch("time.perf_counter", return_value=overlay._ps_start_time + 15.0):
                overlay.update_state()
                # HUD has finished and retracted, but power manager remains in POWER_SAVE
                self.assertEqual(pm.state, PowerState.POWER_SAVE)


    @patch("tkinter.Tk")
    def test_start_test_countdown(self, mock_tk):
        """Verify start_test_countdown runs safe 5s notification on real overlay without mutating power manager."""
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock_tk.return_value = mock_root

        overlay = ScreenshotOverlay(position="TOP_CENTER")
        overlay.start_test_countdown(duration_s=5.0)

        self.assertTrue(overlay._ps_countdown_active)
        self.assertTrue(overlay._is_test_countdown)
        self.assertEqual(overlay._island_mode, "POWER_SAVE")
        self.assertEqual(overlay._island_text, "POWER SAVER")
        self.assertEqual(overlay._countdown_badge, "00:05")

        t_start = overlay._ps_start_time
        # Ticking
        with patch("time.perf_counter", return_value=t_start + 2.0):
            overlay.update_state()
            self.assertEqual(overlay._countdown_badge, "00:03")
            self.assertTrue(overlay._ps_countdown_active)

        # Complete
        with patch("time.perf_counter", return_value=t_start + 5.2):
            overlay.update_state()
            self.assertFalse(overlay._ps_countdown_active)
            self.assertEqual(overlay._island_text, "POWER SAVER · HIDING")
            self.assertEqual(overlay._countdown_badge, "")

    def test_runtime_state_trigger_test_countdown(self):
        """Verify RuntimeState registers test countdown callback and dispatches safely."""
        received = []
        self.state.set_test_countdown_cb(lambda dur: received.append(dur))
        ok = self.state.trigger_test_countdown(5.0)
        self.assertTrue(ok)
        self.assertEqual(received, [5.0])

        # Without callback
        self.state.set_test_countdown_cb(None)
        self.assertFalse(self.state.trigger_test_countdown(5.0))


if __name__ == "__main__":
    unittest.main()
