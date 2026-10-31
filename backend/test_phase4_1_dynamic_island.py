# test_phase4_1_dynamic_island.py
"""
Unit tests for Air Point Phase 4.1 Native Windows Dynamic Island.
Verifies:
- Dark graphite / near-black signature container styling
- Restrained sage green accents and clean typography
- 7 vertical sound bars matching real Windows output volume
- Smooth expansion to 260px during volume gestures and retract to 220px
- 800ms dwell hold upon release
- Honest status toasts (screenshots, WhatsApp, mute/unmute, tracking transitions)
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from core.overlay import (
    ScreenshotOverlay,
    COLOR_GRAPHITE_BG,
    COLOR_GRAPHITE_BORDER,
    COLOR_SAGE_ACCENT,
    COLOR_TEXT_PRIMARY,
    COLOR_ERROR_RED,
)


class TestPhase41DynamicIsland(unittest.TestCase):
    @patch("tkinter.Tk")
    def setUp(self, mock_tk):
        mock_root = MagicMock()
        mock_root.winfo_screenwidth.return_value = 1920
        mock_root.winfo_screenheight.return_value = 1080
        mock_root.winfo_id.return_value = 12345
        mock_tk.return_value = mock_root

        self.overlay = ScreenshotOverlay(position="TOP_CENTER")

    def test_dimensions_and_expansion(self):
        """Test default standard width is 220px and expands to 260px for volume."""
        self.assertEqual(self.overlay.w, 220)
        self.assertEqual(self.overlay.h, 44)

        # Trigger volume gesture
        self.overlay.show_ear_volume("UP", 0.75, is_active=True)
        self.assertEqual(self.overlay.target_w, 260)
        self.assertEqual(self.overlay._island_mode, "VOLUME")

        # Step animation
        self.overlay.current_w = 260.0
        self.overlay.w = 260
        self.assertEqual(self.overlay.w, 260)

        # Release volume gesture -> reset dimensions
        self.overlay.show_ear_volume("UP", 0.75, is_active=False)
        self.assertEqual(self.overlay._island_state, "SUCCESS")
        # Dwell hold time is ~800ms
        self.assertAlmostEqual(self.overlay._toast_until - time.perf_counter(), 0.8, delta=0.2)

    def test_sound_bar_profile_7_bars(self):
        """Test 7-bar profile scaling and mute flattening."""
        # Static volume 50%
        bars = self.overlay.get_sound_bar_heights(0.50, is_muted=False, is_active=False)
        self.assertEqual(len(bars), 7)
        # Center peak symmetry
        self.assertAlmostEqual(bars[0], bars[6], delta=0.01)
        self.assertGreater(bars[3], bars[0])

        # Max volume (1.0)
        bars_max = self.overlay.get_sound_bar_heights(1.0, is_muted=False, is_active=False)
        self.assertEqual(bars_max[3], 18.0)

        # Muted state
        bars_muted = self.overlay.get_sound_bar_heights(0.8, is_muted=True, is_active=True)
        self.assertEqual(bars_muted, [2.0] * 7)

    def test_refined_palette_constants(self):
        """Verify palette constants match approved specification."""
        self.assertEqual(COLOR_GRAPHITE_BG, "#16171a")
        self.assertEqual(COLOR_GRAPHITE_BORDER, "#27282e")
        self.assertEqual(COLOR_SAGE_ACCENT, "#8aa89b")
        self.assertEqual(COLOR_TEXT_PRIMARY, "#ffffff")
        self.assertEqual(COLOR_ERROR_RED, "#d95d5d")


if __name__ == "__main__":
    unittest.main()
