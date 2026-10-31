# core/camera.py
"""
Asynchronous frame capture using a dedicated daemon thread.

Problem: cv2.VideoCapture.read() is a blocking call. If it blocks in the
main inference thread, every frame waits for the camera's USB transfer to
complete before MediaPipe can start. At 60fps this is ~16ms of forced wait.

Solution: A dedicated thread reads frames as fast as the camera produces them
and drops them into a shared slot. The main thread takes whatever is in the
slot — always the most recent frame — and never waits on I/O.
"""

import threading
import time
import logging

import cv2
import numpy as np

from config import (
    CAMERA_INDEX,
    CAMERA_WIDTH,
    CAMERA_HEIGHT,
    CAMERA_FPS,
    CAMERA_BUFFER_SIZE,
)

logger = logging.getLogger(__name__)


class AsyncCamera:
    """
    Thread-safe frame source backed by a dedicated capture thread.

    Usage:
        cam = AsyncCamera()
        cam.start()
        frame = cam.read()  # always returns latest, never blocks
        cam.stop()

    Context manager protocol supported for clean resource management.
    """

    def __init__(self) -> None:
        self._cap: cv2.VideoCapture | None = None
        self._frame = None
        self._frame_id: int = 0
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> "AsyncCamera":
        """Open the camera and start the capture thread."""
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("Camera already started")
        self._stop_event.clear()
        # CAP_DSHOW: DirectShow backend — lower latency than MSMF (default on Windows)
        self._cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera index {CAMERA_INDEX} via DirectShow. "
                "Verify the webcam is connected and its driver exposes a DirectShow interface."
            )

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        self._cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        # Single-frame buffer: always read the freshest frame, never a stale one
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, CAMERA_BUFFER_SIZE)

        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self._cap.get(cv2.CAP_PROP_FPS)
        logger.info("Camera opened: %dx%d @ %.1f fps", actual_w, actual_h, actual_fps)

        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="CameraCapture")
        self._thread.start()
        return self

    def _capture_loop(self) -> None:
        """Run in background thread. Grab frames as fast as hardware allows."""
        last_time = time.perf_counter()
        frame_count = 0
        while not self._stop_event.is_set():
            try:
                ret, frame = self._cap.read()
            except Exception as e:
                logger.error("Camera read exception: %s", e)
                time.sleep(0.01)
                continue
            if not ret:
                logger.warning("Frame grab failed — camera disconnected?")
                self._stop_event.wait(timeout=0.01)
                continue
            with self._cond:
                self._frame = frame
                self._frame_id += 1
                self._cond.notify_all()
                frame_count += 1
                now = time.perf_counter()
                if now - last_time >= 1.0:
                    self._current_fps = frame_count / (now - last_time)
                    frame_count = 0
                    last_time = now

    def read(self):
        """Return the most recent frame. Returns None until the first frame arrives."""
        with self._lock:
            return self._frame

    def read_fresh(self, last_frame_id: int, timeout: float = 0.04):
        """
        Wait for and return a new frame with its sequence id.
        Blocks for up to timeout seconds until a new frame arrives from the hardware.
        """
        with self._cond:
            if (self._frame is None or self._frame_id == last_frame_id) and not self._stop_event.is_set():
                self._cond.wait(timeout=timeout)
            return self._frame, self._frame_id

    @property
    def fps(self) -> float:
        return getattr(self, "_current_fps", 0.0)

    def stop(self) -> None:
        """Signal the capture thread to stop and release hardware resources."""
        self._stop_event.set()
        with self._cond:
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._thread is not None:
            self._thread = None
        logger.info("Camera released")

    def __enter__(self) -> "AsyncCamera":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()


class FrameFreshnessDetector:
    """
    Detects consecutive byte-identical image buffers indicating a driver or
    USB-level freeze.

    Ownership contract:
        _last_flat is ALWAYS an independent snapshot, never aliasing the caller's
        array. It is safe to mutate the original frame after calling check().
    """

    def __init__(self, stale_threshold_count: int = 3) -> None:
        self._threshold: int = max(2, int(stale_threshold_count))
        self._last_flat: np.ndarray | None = None
        self._identical_count: int = 0
        self.is_stale: bool = False

    def check(self, frame: np.ndarray | None) -> bool:
        """
        Returns True if the frame is considered fresh (not a repeated buffer).
        Returns False for None, invalid shape/size, or a suspected freeze.
        """
        if frame is None or not isinstance(frame, np.ndarray):
            self._identical_count = 0
            self._last_flat = None
            self.is_stale = True
            return False

        if len(frame.shape) != 3 or frame.shape[2] != 3 or frame.size == 0:
            self._identical_count = 0
            self._last_flat = None
            self.is_stale = True
            return False

        contig = np.ascontiguousarray(frame)

        if self._last_flat is not None and contig.shape != self._last_flat.shape:
            self._identical_count = 0
            self._last_flat = contig.copy()
            self.is_stale = False
            return True

        if self._last_flat is None:
            self._identical_count = 0
            self._last_flat = contig.copy()
            self.is_stale = False
            return True

        if np.array_equal(contig, self._last_flat):
            self._identical_count += 1
        else:
            self._identical_count = 0
            self._last_flat = contig.copy()

        self.is_stale = (self._identical_count >= self._threshold)
        return not self.is_stale

    def reset(self) -> None:
        """Reset state, e.g. after camera reopen or test setup."""
        self._last_flat = None
        self._identical_count = 0
        self.is_stale = False
