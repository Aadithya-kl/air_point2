# test_debug_hud_startup.py
"""
Regression tests for the --debug / Ctrl+Alt+D start-up crash (finding F-26).

backend/main.py used to import draw_debug_frame only when config.DEBUG_GESTURES
was True, while the debug window can also be enabled by the --debug flag or the
Ctrl+Alt+D hotkey. With the shipped default (DEBUG_GESTURES = False) the first
debug frame raised:

    NameError: name 'draw_debug_frame' is not defined

These tests import backend/main.py the way the interpreter does (run() is never
called) and check that the renderer is bound and usable whatever the value of
DEBUG_GESTURES. No camera is opened and no native input is sent: the only engine
code executed is module import and one HUD render on a synthetic frame with a
fake orchestrator.
"""

from __future__ import annotations

import importlib
import logging
import unittest
from unittest.mock import patch

import numpy as np

import config
from core.tracker import HandsResult


class _FakeActuator:
    _last_send_input_result = None
    is_dragging = False

    def get_native_left_button_state(self) -> str:
        return "UNKNOWN"


class _FakeLeftProcessor:
    drag_state_name = "READY"
    drag_state_text = "READY"
    last_pinch_norm = 0.0
    is_in_dropout_grace = False
    is_pinch_candidate = False
    release_reason = None


class _FakeOrchestrator:
    def __init__(self) -> None:
        self._actuator = _FakeActuator()
        self._left = _FakeLeftProcessor()
        self.drag_enabled = True
        self.pointer_owner = "NONE"
        self.cursor_source_name = "NONE"
        self.is_cursor_moving = False


class TestDebugHudStartup(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # main.py calls logging.basicConfig at import; remember the root logger so
        # the rest of the suite is not left with an extra INFO stream handler.
        cls._root_handlers = list(logging.root.handlers)
        cls._root_level = logging.root.level

    @classmethod
    def tearDownClass(cls) -> None:
        for h in list(logging.root.handlers):
            if h not in cls._root_handlers:
                logging.root.removeHandler(h)
        logging.root.setLevel(cls._root_level)

    def setUp(self) -> None:
        self.assertFalse(
            getattr(config, "DEBUG_GESTURES", False),
            "these tests assume the shipped default config.DEBUG_GESTURES = False",
        )

    def test_renderer_bound_with_shipped_default(self) -> None:
        """With DEBUG_GESTURES = False, main.draw_debug_frame is the real renderer (the --debug path)."""
        import main
        from core.debug_overlay import draw_debug_frame

        self.assertIsNone(main.DEBUG_HUD_IMPORT_ERROR)
        self.assertIs(main.draw_debug_frame, draw_debug_frame)

    def test_renderer_bound_regardless_of_debug_gestures(self) -> None:
        """The binding must not depend on the config flag at all."""
        import main

        try:
            for flag in (True, False):
                with patch.object(config, "DEBUG_GESTURES", flag):
                    reloaded = importlib.reload(main)
                    self.assertIsNotNone(
                        reloaded.draw_debug_frame,
                        f"draw_debug_frame unbound with DEBUG_GESTURES={flag}",
                    )
                    self.assertIsNone(reloaded.DEBUG_HUD_IMPORT_ERROR)
        finally:
            importlib.reload(main)  # leave the module in its default state

    def test_debug_branch_call_renders_without_camera(self) -> None:
        """The exact call made on the first debug frame succeeds with fake engine objects."""
        import main

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        out = main.draw_debug_frame(
            frame,
            HandsResult(),
            "IDLE",            # right_state
            None,              # cursor_pos
            {},                # right_visual_tips
            {},                # left_visual_tips
            0.0,               # inference_time_ms
            0.0,               # total_time_ms
            0.0,               # fps
            0.0,               # cam_fps
            "DISABLED",        # click_state_text
            0.0,               # last_pinch_norm
            False,             # is_cursor_locked
            _FakeOrchestrator(),
        )
        self.assertEqual(out.shape, frame.shape)
        self.assertIsNot(out, frame, "renderer must return an annotated copy, not the input frame")


if __name__ == "__main__":
    unittest.main()
