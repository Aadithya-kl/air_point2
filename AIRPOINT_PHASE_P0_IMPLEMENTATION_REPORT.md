# AIRPOINT PHASE P0 IMPLEMENTATION REPORT

## Native Windows Input Reliability and Drag Safety

**Repository:** air_point2  
**Branch:** fix/p0-native-input-safety  
**Commit:** 4672829 (baseline)  
**Workspace:** C:\Users\loges\Documents\air_point2_audit  
**Implementation status:** COMPLETE — all tests passing  

---

## 1. Original Defects

The independent architecture audit identified the following Phase P0 defects:

| # | Defect | Severity | Source |
|---|--------|----------|--------|
| D-1 | **SendInput false-success via `mouse_event()` void fallback** | Critical | `backend/core/actuator.py:116-137` — When `SendInput` returns 0, the `mouse_event()` fallback returns `True` without verifying actual Windows delivery. `mouse_event()` is void-returning; no exception does NOT mean the event was received. |
| D-2 | **Failed LEFTDOWN transitions to confirmed grab** | High | `drag_start()` set `self._dragging = True` whenever `_send_input()` returned truthy, including the unconfirmed `mouse_event()` fallback path. |
| D-3 | **Failed LEFTUP silently clears active state** | High | `drag_end()` cleared `self._dragging = False` even when `_send_input()` returned falsy (unconfirmed/failed), potentially releasing a button that was never actually down or leaving state desynchronized. |
| D-4 | **Immediate clear-release bypasses debounce** | High | `drag_controller.py:353-361` and `:388-391` — `clear_release_norm_dist=0.85` causes immediate `_execute_drop()` in both `GRAB_LOCKED` and `RELEASE_PENDING` states without waiting for `release_dwell_s`. A single noisy pinch spike ≥0.85 causes unintended drop. |
| D-5 | **Tracking-loss timeout too short** | Medium | `config.py:149` — `LEFT_DRAG_LOST_TIMEOUT_S=0.075s` is less than one frame at ~15 FPS (~66ms), so a single dropped camera frame triggers premature drag release. |
| D-6 | **No native button-state observation** | Medium | `get_native_left_button_state()` (`actuator.py:486`) was implemented but never called post-activation. No way to distinguish gesture state from actual OS button state. |

---

## 2. Root Causes

| Defect | Root Cause |
|--------|-----------|
| D-1 | `_send_input()` treated the absence of a Python exception from `mouse_event()` as proof of delivery. `mouse_event()` is a void-returning Windows API; success cannot be determined from the Python call alone. |
| D-2 | `drag_start()` used `if not ok:` on `_send_input()`'s bool return, treating `UNCONFIRMED` (from fallback) as `True`/success and setting `_dragging = True`. |
| D-3 | `drag_end()` used the same pattern: `if not ok:` treated `UNCONFIRMED` as failure but still cleared `_dragging = False` only on success — however the retry logic could clear state on the second `UNCONFIRMED` without knowing if UP was actually delivered. |
| D-4 | `clear_release_norm_dist` was checked as an OR condition with `release_dwell_s` in `RELEASE_PENDING`, and as an immediate `if` in `GRAB_LOCKED`, bypassing the debounce entirely. |
| D-5 | `LEFT_DRAG_LOST_TIMEOUT_S=0.075s` was set for a hypothetical 30 FPS camera (~33ms/frame) but actual throughput is ~15 FPS (~66ms/frame), making 75ms < 1 frame. |
| D-6 | `GetAsyncKeyState(VK_LBUTTON)` was implemented as a diagnostic helper but never integrated into the drag lifecycle. |

---

## 3. Exact Files Changed

| File | Changes |
|------|---------|
| `backend/core/actuator.py` | Added `SendInputResult` enum; rewrote `_send_input()` to return `SendInputResult` (CONFIRMED/UNCONFIRMED/FAILED); removed `mouse_event()` false-success path; updated `_send_mouse_flag()`, `drag_start()`, `drag_end()`, `move()`, `left_click()`, `right_click()`; added `GetAsyncKeyState` diagnostic telemetry; made logging robust against bool returns from mocked actuators |
| `backend/core/gestures/drag_controller.py` | Removed `clear_release_norm_dist` immediate bypass from `GRAB_LOCKED` and `RELEASE_PENDING`; release now requires sustained `release_dwell_s` in `RELEASE_PENDING`; added DEBUG-level per-frame pinch telemetry logging |
| `backend/config.py` | Increased `LEFT_DRAG_LOST_TIMEOUT_S` from `0.075` to `0.150` (~2 frames at 15 FPS) |
| `backend/test_drag_and_drop_pipeline.py` | Updated `test_05_mouse_up_occurs_exactly_once_on_unpinch` to verify release dwell behavior (no immediate UP on unpinch; UP after dwell completes) |
| `backend/test_native_input_safety.py` | **NEW** — 21 regression tests covering the SendInputResult contract, drag session safety, and drag state machine reliability |

---

## 4. Architecture Changes

### 4.1 Native Input Safety Contract (`backend/core/actuator.py`)

**New `SendInputResult` enum:**
```
CONFIRMED   — SendInput inserted exactly 1 event (result == 1)
UNCONFIRMED — SendInput returned 0; mouse_event fallback attempted but cannot verify delivery
FAILED      — SendInput raised exception or user32 unavailable
```

**`_send_input()` behavior:**
- `user32 is None` → `FAILED` (logged at WARNING)
- `SendInput` returns 1 → `CONFIRMED` (delivery confirmed)
- `SendInput` returns 0 → `UNCONFIRMED` (logged at WARNING; `mouse_event` fallback NO LONGER returns `True`)
- `SendInput` raises exception → `FAILED` (logged at ERROR)

**Caller updates:**
- `drag_start()`: Only `CONFIRMED` → `DragStartResult.STARTED` + `_dragging = True`. `UNCONFIRMED`/`FAILED` → `DragStartResult.FAILED`, `_dragging` stays `False`.
- `drag_end()`: Only `CONFIRMED` → `DragEndResult.RELEASED` + `_dragging = False`. `UNCONFIRMED`/`FAILED` → retry once; if still not `CONFIRMED`, `DragEndResult.FAILED` with `_dragging` retained `True` (watchdog can retry).
- `move()`: Returns `bool` — `True` only on `CONFIRMED`.
- `left_click()`: Returns `bool` — `True` only if both DOWN and UP are `CONFIRMED`.
- `right_click()`: Logs WARNING if either DOWN or UP is not `CONFIRMED`.
- `get_native_left_button_state()`: Called at DEBUG level in `drag_start()` and `drag_end()` as supplementary telemetry (NOT an activation gate).

### 4.2 Drag Session State Safety

| Guarantee | Implementation |
|-----------|---------------|
| Failed LEFTDOWN never starts grab | `drag_start()` returns `FAILED` on `UNCONFIRMED`/`FAILED`; `_dragging` remains `False` |
| Successful LEFTDOWN establishes one session | `drag_start()` returns `STARTED` on `CONFIRMED`; `_dragging = True`; `ALREADY_ACTIVE` on re-entry |
| Failed LEFTUP doesn't clear state | `drag_end()` returns `FAILED`; `_dragging` stays `True` for watchdog retry |
| Safe release retries are idempotent | `drag_end()` retries once on failure; repeated calls return `NOT_DRAGGING` after success |
| Watchdog remains operational | `check_drag_watchdog()` calls `drag_end()` which handles `UNCONFIRMED`/`FAILED` |
| All cancellation paths release drag | `release_grab()`, `reset()`, tracking loss, feature disable, screenshot, wakanda, shutdown — all route through `drag_end()` |

### 4.3 Grab Lock and Release Reliability

**State machine transitions (revised):**

| State | Trigger | Next State | Action |
|-------|---------|------------|--------|
| `READY` | `norm_pinch_dist < start_th` | `GRAB_PENDING` | Start confirm dwell |
| `GRAB_PENDING` | dwell ≥ `confirm_dwell_s` | `GRAB_LOCKED` | Native DOWN (must be CONFIRMED) |
| `GRAB_PENDING` | `norm_pinch_dist ≥ release_th` | `READY` | Cancel (pinch released before dwell) |
| `GRAB_LOCKED` | `norm_pinch_dist ≥ release_th` | `RELEASE_PENDING` | Start release debounce (NO immediate drop) |
| `RELEASE_PENDING` | `norm_pinch_dist ≤ release_th` | `GRAB_LOCKED` | Jitter recovery |
| `RELEASE_PENDING` | dwell ≥ `release_dwell_s` | `READY` | Native UP (deliberate unpinch) |
| Any | Tracking loss > `lost_timeout_s` | `READY` | Safe release (watchdog) |
| Any | Feature disable / reset / shutdown | `READY` | Safe release |

**Key change:** `clear_release_norm_dist=0.85` no longer causes immediate drop. A single noisy frame at 0.90 enters `RELEASE_PENDING`; if the next frame returns below `release_th`, the state recovers to `GRAB_LOCKED` without any UP event.

---

## 5. Native Input Safety Contract

### 5.1 Result Type Distinctions

| Result | Meaning | Action |
|--------|---------|--------|
| `CONFIRMED` | SendInput inserted 1 event | Proceed with state transition |
| `UNCONFIRMED` | SendInput returned 0; fallback unverified | Treat as failure; do not change gesture state |
| `FAILED` | Exception or user32 unavailable | Treat as failure; log diagnostics |

### 5.2 No False Success

The `mouse_event()` fallback is **no longer called** in `_send_input()`. Previously, when `SendInput` returned 0 (e.g., UIPI block), the code would call `mouse_event()` and return `True` if no exception was raised. Since `mouse_event()` returns void, this was a false-success report. Now, `SendInput` returning 0 always yields `UNCONFIRMED`, which is treated as failure by `drag_start()` and `drag_end()`.

### 5.3 Native Button-State Observation

`GetAsyncKeyState(VK_LBUTTON)` is called at DEBUG level after `drag_start()` and `drag_end()` as supplementary telemetry. It is **NOT** used as an activation gate, per the audit requirement: "Do not make it an unconditional activation gate without establishing its semantics under injected input on the actual supported Windows environment."

---

## 6. Drag State-Machine Changes

### 6.1 GRAB_LOCKED (before → after)

**Before:** `norm_pinch_dist ≥ clear_release_norm_dist (0.85)` → immediate `_execute_drop()`  
**After:** `norm_pinch_dist ≥ release_th (0.75)` → enter `RELEASE_PENDING` (start debounce). No immediate drop.

### 6.2 RELEASE_PENDING (before → after)

**Before:** `elapsed_rel ≥ release_dwell_s OR norm_pinch_dist ≥ clear_release_norm_dist` → `_execute_drop()`  
**After:** `elapsed_rel ≥ release_dwell_s` → `_execute_drop()`. The `clear_release_norm_dist` shortcut is removed.

### 6.3 Configuration Changes

| Parameter | Before | After | Reason |
|-----------|--------|-------|--------|
| `LEFT_DRAG_LOST_TIMEOUT_S` | 0.075s | 0.150s | ~2 frames at 15 FPS; prevents single dropped frame from releasing drag |
| `clear_release_norm_dist` | 0.85 (immediate bypass) | 0.85 (retained but no bypass) | Threshold value kept; bypass logic removed |

---

## 7. New Regression Tests

**File:** `backend/test_native_input_safety.py` (21 tests)

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestSendInputResultContract` | 4 | CONFIRMED, UNCONFIRMED, FAILED, user32 unavailable |
| `TestDragStartSafety` | 5 | Failed LEFTDOWN never starts grab; successful LEFTDOWN establishes session; no duplicate DOWN; error recording |
| `TestDragEndSafety` | 6 | Successful LEFTUP releases; failed LEFTUP retains state; retry after failed UP; idempotent release; watchdog release |
| `TestDragControllerReleaseReliability` | 5 | Noisy spike doesn't drop; spike+recovery remains dragging; sustained unpinch drops; tracking loss releases; feature disable releases; no duplicate DOWN/UP |
| `TestRightHandClicksDuringDrag` | 1 | Right-hand click functional during left-hand grab |

**File:** `backend/test_drag_and_drop_pipeline.py` (1 modified test)

| Test | Change |
|------|--------|
| `test_05_mouse_up_occurs_exactly_once_on_unpinch` | Updated to verify release dwell: unpinch enters `RELEASE_PENDING` with no UP; UP sent only after dwell completes |

---

## 8. Exact Test Results

**Command:**
```
python -c "import unittest; ...loader.loadTestsFromName('test_power_state_machine')...loader.loadTestsFromName('test_test_guard')...loader.loadTestsFromName('test_frame_freshness')...loader.loadTestsFromName('test_drag_and_drop_pipeline')...loader.loadTestsFromName('test_drag_safety')...loader.loadTestsFromName('test_native_input_safety')..."
```

**Results: 81 tests, 0 failures, 0 errors**

| Test File | Tests | Result |
|-----------|-------|--------|
| `test_power_state_machine.py` | 16 | PASS |
| `test_test_guard.py` | 13 | PASS |
| `test_frame_freshness.py` | 9 | PASS |
| `test_drag_and_drop_pipeline.py` | 17 | PASS |
| `test_drag_safety.py` | 5 | PASS |
| `test_native_input_safety.py` | 21 | PASS |
| **Total** | **81** | **ALL PASS** |

**Note:** 34 additional backend test files exist but cannot run in this environment due to missing dependencies (`pynput`, `screeninfo`, `pycaw`). These are environment limitations, not test failures. Frontend tests could not be executed (Node.js v24.14.0 available but `node_modules` absent; dependency installation not permitted).

**No real Windows input was sent during testing.** All tests use mocked native APIs (`SafeTestActuator`, `MockInputActuator`, `MockMouseActuator`).

---

## 9. Remaining Risks

| Risk | Description | Mitigation |
|------|-------------|------------|
| **Real Windows drag not verified** | All tests use mocked `SendInput`. Actual `SendInput` behavior under UIPI, elevated processes, or remote desktop is untested. | Physical Windows interactive test required before commercial release. |
| **`GetAsyncKeyState` semantics unverified** | Called at DEBUG level only. Its behavior under injected input (SendInput vs hardware) is not established on actual hardware. | Not used as activation gate; diagnostic only. |
| **Multi-monitor not tested** | Coordinate mapping uses `MOUSEEVENTF_VIRTUALDESK` but no multi-monitor test exists. | Coordinate tests on secondary monitors left/above primary needed. |
| **34 backend tests can't run** | Missing `pynput`, `screeninfo`, `pycaw` prevents import of `core.actuator` dependents. | Install dependencies in CI environment; run full suite. |
| **Frontend not tested** | Node.js available but `node_modules` absent. | `npm install` + `npx vitest run` in CI environment. |

---

## 10. Real Windows Validation Checklist

The following must be verified on a physical Windows machine with a webcam before claiming drag-and-drop is commercially reliable:

- [ ] Real `SendInput` delivery confirmation (does `SendInput` return 1 on normal desktop?)
- [ ] `mouse_event()` behavior under UIPI block (does it actually deliver?)
- [ ] `GetAsyncKeyState(VK_LBUTTON)` after injected `SendInput` LEFTDOWN (does it report DOWN?)
- [ ] End-to-end drag/hold/drop: file follows cursor during held button, drops on unpinch
- [ ] No stuck button after process crash during drag (watchdog recovery)
- [ ] Multi-monitor: cursor mapping on secondary monitor left of primary
- [ ] Frame timing: actual FPS and release dwell (80ms) behavior at measured FPS
- [ ] No duplicate DOWN/UP events in sustained drag sessions

---

**IMPORTANT:** Drag-and-drop is **NOT** commercially reliable until a real Windows interactive test confirms it. Mock-based tests prove state machine logic but not actual Windows input delivery.
