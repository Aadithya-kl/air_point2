# preflight_physical_test.py
"""
Hardware-free pre-flight for AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md.

Verifies that the engine can start on this machine WITHOUT opening the camera
and WITHOUT sending any native input:
  - interpreter is the canonical backend/.venv and nothing from the older
    'antigravity' checkout is on sys.path
  - all runtime packages import
  - both MediaPipe .task models load and run on a blank frame
  - display geometry can be built (screeninfo + DPI awareness)
  - port 8765 is free
  - the screenshot directory is writable
  - the audio endpoint can be read (warning only if not)
  - the native APIs the engine relies on exist (read-only cursor query only)

Run from backend/ with the canonical venv:
    .venv\\Scripts\\python.exe preflight_physical_test.py

Exit code 0 = ready for the physical plan, 1 = fix the FAILED items first.
This script never calls SendInput, SetCursorPos, keybd_event or the camera.
"""

from __future__ import annotations

import ctypes
import importlib
import os
import socket
import sys
import tempfile
import time

RESULTS: list[tuple[str, str, str]] = []  # (status, name, detail)


def record(status: str, name: str, detail: str = "") -> None:
    RESULTS.append((status, name, detail))
    # ASCII only: the Windows console code page may not render dashes or arrows.
    print(f"[{status:<4}] {name}{(': ' + detail) if detail else ''}")


def check(name: str, fn, warn_only: bool = False) -> None:
    try:
        detail = fn()
        record("OK", name, detail or "")
    except Exception as e:  # noqa: BLE001 - every failure must be reported, not raised
        record("WARN" if warn_only else "FAIL", name, f"{type(e).__name__}: {e}")


# ── 1. Interpreter and sys.path hygiene ──────────────────────────────────────

def check_interpreter() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    expected = os.path.join(here, ".venv", "Scripts", "python.exe")
    if os.path.normcase(sys.executable) != os.path.normcase(expected):
        raise RuntimeError(f"interpreter is {sys.executable}, expected {expected}")
    leaks = [p for p in sys.path if "antigravity" in p.lower()]
    if leaks:
        raise RuntimeError(f"older checkout on sys.path: {leaks}")
    return f"Python {sys.version.split()[0]} at {sys.executable}"


check("Interpreter is backend/.venv with a clean sys.path", check_interpreter)


# ── 2. Runtime packages ──────────────────────────────────────────────────────

def check_imports() -> str:
    versions = []
    for mod in ("cv2", "mediapipe", "numpy", "pynput", "screeninfo", "PIL", "psutil", "pycaw", "comtypes", "tkinter"):
        m = importlib.import_module(mod)
        versions.append(f"{mod} {getattr(m, '__version__', '')}".strip())
    return ", ".join(versions)


check("Runtime packages import", check_imports)


# ── 3. Models and MediaPipe inference on a blank frame ───────────────────────

def check_models_exist() -> str:
    import config
    out = []
    for label, path in (("hand", config.MP_MODEL_PATH), ("face", config.MP_FACE_MODEL_PATH)):
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        size = os.path.getsize(path)
        if size < 1_000_000:
            raise RuntimeError(f"{label} model unexpectedly small ({size} bytes): {path}")
        out.append(f"{label}={size // 1024} KB")
    return ", ".join(out)


check("MediaPipe model bundles present", check_models_exist)


def check_hand_model() -> str:
    import numpy as np
    from core.tracker import HandsResult, HandTracker
    t0 = time.perf_counter()
    tracker = HandTracker()
    load_ms = (time.perf_counter() - t0) * 1000.0
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    t1 = time.perf_counter()
    res = tracker.process(frame)
    infer_ms = (time.perf_counter() - t1) * 1000.0
    tracker.close()
    if not isinstance(res, HandsResult):
        raise RuntimeError(f"unexpected result type {type(res).__name__}")
    if res.left is not None or res.right is not None:
        raise RuntimeError("hands detected on a blank frame")
    return f"load {load_ms:.0f} ms, blank-frame inference {infer_ms:.1f} ms"


check("Hand landmarker loads and runs (no hands on blank frame)", check_hand_model)


def check_face_model() -> str:
    import numpy as np
    from core.face_tracker import FaceTracker
    t0 = time.perf_counter()
    tracker = FaceTracker()
    load_ms = (time.perf_counter() - t0) * 1000.0
    if not tracker.is_ready:
        raise RuntimeError("FaceTracker not ready (model failed to load)")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    t1 = time.perf_counter()
    res = tracker.process(frame)
    infer_ms = (time.perf_counter() - t1) * 1000.0
    tracker.close()
    if res.detected:
        raise RuntimeError("face detected on a blank frame")
    return f"load {load_ms:.0f} ms, blank-frame inference {infer_ms:.1f} ms"


check("Face landmarker loads and runs (no face on blank frame)", check_face_model)


# ── 4. Display geometry ──────────────────────────────────────────────────────

def check_display() -> str:
    from core.display import build_trackpad_zone, build_virtual_desktop
    d = build_virtual_desktop()
    z = build_trackpad_zone()
    if d.total_width <= 0 or d.total_height <= 0:
        raise RuntimeError(f"bad desktop size {d.total_width}x{d.total_height}")
    return f"{d.total_width}x{d.total_height} over {d.monitor_count} monitor(s); trackpad {z.x_min}-{z.x_max} x {z.y_min}-{z.y_max}"


check("Virtual desktop geometry", check_display)


# ── 5. Bridge port ───────────────────────────────────────────────────────────

def check_port() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(("127.0.0.1", 8765))
    except OSError as e:
        raise RuntimeError("127.0.0.1:8765 is in use; stop the other process (scripts\\stop_airpoint.ps1) "
                           f"or the engine will refuse to start ({e})")
    finally:
        s.close()
    return "127.0.0.1:8765 is free"


check("Bridge port 8765 free", check_port)


# ── 6. Screenshot directory ──────────────────────────────────────────────────

def check_screenshot_dir() -> str:
    import config
    os.makedirs(config.SCREENSHOT_DIR, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix="preflight_", suffix=".tmp", dir=config.SCREENSHOT_DIR)
    os.close(fd)
    os.remove(path)
    return config.SCREENSHOT_DIR


check("Screenshot directory writable", check_screenshot_dir)


# ── 7. Audio endpoint (read-only) ────────────────────────────────────────────

def check_audio() -> str:
    from core.audio_controller import AudioController
    state = AudioController().get_current_state()
    if state is None:
        raise RuntimeError("no default audio endpoint readable (ear-volume / lip-mute tests will not work)")
    muted, vol = state
    return f"muted={muted}, volume={vol:.2f}"


check("Audio endpoint readable (warning only)", check_audio, warn_only=True)


# ── 8. Native APIs present (no injection) ────────────────────────────────────

def check_native_apis() -> str:
    from ctypes import wintypes
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    for api in ("SendInput", "GetAsyncKeyState", "GetCursorPos", "SetProcessDpiAwarenessContext", "SystemParametersInfoW"):
        if not hasattr(u32, api):
            raise RuntimeError(f"user32.{api} missing")
    pt = wintypes.POINT()
    if not u32.GetCursorPos(ctypes.byref(pt)):
        raise RuntimeError(f"GetCursorPos failed (GetLastError={ctypes.get_last_error()}); "
                           "the engine runs in a session where cursor queries are blocked")
    btn = "DOWN" if (u32.GetAsyncKeyState(0x01) & 0x8000) else "UP"
    return f"cursor at ({pt.x}, {pt.y}), physical left button {btn}"


check("Native user32 APIs available (read-only cursor query)", check_native_apis)


# ── 9. Entry point imports ───────────────────────────────────────────────────

def check_main_imports() -> str:
    import main  # noqa: F401 - import only; run() is never called here
    return "backend/main.py imports cleanly (run() not invoked)"


check("Engine entry point imports", check_main_imports)


# ── Summary ──────────────────────────────────────────────────────────────────

fails = [r for r in RESULTS if r[0] == "FAIL"]
warns = [r for r in RESULTS if r[0] == "WARN"]
print()
print(f"PREFLIGHT: {len(RESULTS) - len(fails) - len(warns)} ok, {len(warns)} warnings, {len(fails)} failed")
if fails:
    print("NOT READY: fix the FAILED items before running the physical plan.")
    sys.exit(1)
print("READY: the engine can start on this machine. No camera or native input was used by this script.")
print("(Lines starting with W0000 ... inference_feedback_manager / landmark_projection_calculator are MediaPipe "
      "start-up notices and are expected.)")
sys.exit(0)
