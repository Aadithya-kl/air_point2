# test_frame_freshness.py
"""
Unit tests for FrameFreshnessDetector in Air Point.

Verifies:
1. Independent baseline snapshot ownership (no shared memory with caller buffers).
2. In-place buffer mutation detection on contiguous arrays.
3. Exact threshold semantics and stale state declaration (threshold=3).
4. Recovery from stale state upon new image content.
5. Non-contiguous input handling (strided slices).
6. Fail-closed behavior on None, empty, and invalid shapes.
7. Clean recovery following invalid frames.
8. Resolution change handling (treated as fresh, establishes new baseline).
9. Explicit reset behavior.
"""

import unittest
import numpy as np

from core.camera import FrameFreshnessDetector


class TestFrameFreshnessDetector(unittest.TestCase):
    def setUp(self) -> None:
        self.rng = np.random.default_rng(42)
        self.base_frame = self.rng.integers(0, 256, (480, 640, 3), dtype=np.uint8)

    def test_independent_baseline_ownership_no_shared_memory(self) -> None:
        det = FrameFreshnessDetector(stale_threshold_count=3)
        frame = np.ascontiguousarray(self.base_frame)
        fresh = det.check(frame)
        self.assertTrue(fresh)
        self.assertIsNotNone(det._last_flat)
        self.assertFalse(np.shares_memory(det._last_flat, frame))

    def test_in_place_mutation_detected_on_contiguous_array(self) -> None:
        det = FrameFreshnessDetector(stale_threshold_count=3)
        frame = np.ascontiguousarray(self.base_frame)
        
        # F0: Establish baseline
        self.assertTrue(det.check(frame))
        self.assertEqual(det._identical_count, 0)
        self.assertFalse(det.is_stale)

        # Mutate array in place and pass same object
        frame[0, 0, 0] ^= 1
        frame[100, 200, 1] ^= 255
        
        # F1: Must recognize content change and reset count
        self.assertTrue(det.check(frame))
        self.assertEqual(det._identical_count, 0)
        self.assertFalse(det.is_stale)

    def test_exact_stale_threshold_sequence(self) -> None:
        det = FrameFreshnessDetector(stale_threshold_count=3)
        frame = np.ascontiguousarray(self.base_frame)

        # F0: Baseline
        self.assertTrue(det.check(frame))
        self.assertEqual(det._identical_count, 0)
        self.assertFalse(det.is_stale)

        # F1: 1st repetition
        self.assertTrue(det.check(frame))
        self.assertEqual(det._identical_count, 1)
        self.assertFalse(det.is_stale)

        # F2: 2nd repetition
        self.assertTrue(det.check(frame))
        self.assertEqual(det._identical_count, 2)
        self.assertFalse(det.is_stale)

        # F3: 3rd repetition (count == threshold) -> STALE
        self.assertFalse(det.check(frame))
        self.assertEqual(det._identical_count, 3)
        self.assertTrue(det.is_stale)

        # F4: Continued repetition stays stale
        self.assertFalse(det.check(frame))
        self.assertEqual(det._identical_count, 4)
        self.assertTrue(det.is_stale)

    def test_recovery_from_stale_on_new_content(self) -> None:
        det = FrameFreshnessDetector(stale_threshold_count=3)
        frame = np.ascontiguousarray(self.base_frame)

        # Drive into stale state
        for _ in range(4):
            det.check(frame)
        self.assertTrue(det.is_stale)

        # Provide fresh content
        new_frame = frame.copy()
        new_frame[0, 0, 0] ^= 1
        self.assertTrue(det.check(new_frame))
        self.assertEqual(det._identical_count, 0)
        self.assertFalse(det.is_stale)

    def test_non_contiguous_input_handling(self) -> None:
        det = FrameFreshnessDetector(stale_threshold_count=3)
        large = self.rng.integers(0, 256, (960, 1280, 3), dtype=np.uint8)
        nc_frame = large[::2, ::2, :]  # Strided non-contiguous 480x640x3
        self.assertFalse(nc_frame.flags["C_CONTIGUOUS"])

        # F0: Baseline
        self.assertTrue(det.check(nc_frame))
        self.assertTrue(det._last_flat.flags["C_CONTIGUOUS"])
        self.assertFalse(np.shares_memory(det._last_flat, large))

        # Repeated passes trigger staleness
        self.assertTrue(det.check(nc_frame))  # F1
        self.assertTrue(det.check(nc_frame))  # F2
        self.assertFalse(det.check(nc_frame)) # F3 -> stale
        self.assertTrue(det.is_stale)

    def test_none_input_fails_closed(self) -> None:
        det = FrameFreshnessDetector(stale_threshold_count=3)
        det.check(self.base_frame)
        
        # Pass None
        self.assertFalse(det.check(None))
        self.assertTrue(det.is_stale)
        self.assertIsNone(det._last_flat)
        self.assertEqual(det._identical_count, 0)

        # Clean recovery on valid frame
        self.assertTrue(det.check(self.base_frame))
        self.assertFalse(det.is_stale)
        self.assertEqual(det._identical_count, 0)

    def test_empty_and_invalid_shapes_fail_closed(self) -> None:
        det = FrameFreshnessDetector(stale_threshold_count=3)
        
        # Empty array
        empty = np.zeros((0, 0, 3), dtype=np.uint8)
        self.assertFalse(det.check(empty))
        self.assertTrue(det.is_stale)

        # 2D array
        bad_2d = np.zeros((480, 640), dtype=np.uint8)
        self.assertFalse(det.check(bad_2d))
        self.assertTrue(det.is_stale)

        # 4D array
        bad_4d = np.zeros((1, 480, 640, 3), dtype=np.uint8)
        self.assertFalse(det.check(bad_4d))
        self.assertTrue(det.is_stale)

    def test_resolution_change_treated_as_fresh(self) -> None:
        det = FrameFreshnessDetector(stale_threshold_count=3)
        f_large = self.rng.integers(0, 256, (480, 640, 3), dtype=np.uint8)
        f_small = self.rng.integers(0, 256, (240, 320, 3), dtype=np.uint8)

        self.assertTrue(det.check(f_large))
        self.assertEqual(det._identical_count, 0)

        # Resolution change resets baseline and is fresh
        self.assertTrue(det.check(f_small))
        self.assertEqual(det._identical_count, 0)
        self.assertFalse(det.is_stale)

    def test_reset(self) -> None:
        det = FrameFreshnessDetector(stale_threshold_count=3)
        for _ in range(5):
            det.check(self.base_frame)
        self.assertTrue(det.is_stale)

        det.reset()
        self.assertFalse(det.is_stale)
        self.assertEqual(det._identical_count, 0)
        self.assertIsNone(det._last_flat)


if __name__ == "__main__":
    unittest.main()
