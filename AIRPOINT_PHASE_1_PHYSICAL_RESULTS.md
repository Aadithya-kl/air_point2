# AIRPOINT — PHASE 1 PHYSICAL TEST RESULTS

Fill this in while executing `AIRPOINT_PHASE_1_PHYSICAL_TEST_PLAN.md`. Record what you saw, not what was expected. Attach `phase1_physical_run.log`.

## Session header

| Field | Value |
|---|---|
| Date / time | |
| Windows build (`winver`) | |
| DPI scaling (Settings → Display) | |
| Monitor layout (count, resolutions, arrangement) | |
| Webcam model and resolution | |
| Engine start command used | |
| Preflight result (`backend\preflight_physical_test.py`) | |
| HUD `FPS` line at idle (`CAM x / PROC y`) | |
| HUD `FPS` line while tracking one hand | |

## Results

Status values: PASS, FAIL, PARTIAL, SKIPPED. Quote log lines verbatim where the plan asks for them.

| Test | HUD `DRAG STATE` | `LOG` | `BTN` | `SEND` | Key log lines seen | OS outcome | Status | Notes |
|---|---|---|---|---|---|---|---|---|
| T1 Pointer baseline | | | | | | | | |
| T2 Grab confirmation | | | | | | | | |
| T3 Hold + right-hand steering | | | | | | | | |
| T4 Deliberate drop | | | | | | | | |
| T5 Noisy release (5 flicks) | | | | | | | | drops / RELEASE_PENDING entries: |
| T6a Tracking loss ~1 s | | | | | | | | |
| T6b Tracking loss ~0.1 s | | | | | | | | |
| T7 Pause during hold | | | | | | | | |
| T8 Exit during hold | | | | | | | | |
| T9 Elevated target (UIPI) | | | | | | | | |
| T10 `/api/status` drag block | | | | | | | | |
| T11 Multi-monitor | | | | | | | | |
| T12 60 s hold | | | | | | | | |

## Repetition counts (reliability)

| Test | Attempts | Passes | Failures | Failure descriptions |
|---|---|---|---|---|
| T2 Grab | | | | |
| T3 Steer | | | | |
| T4 Drop | | | | |
| T5 Noisy release | | | | |

## Observations that do not fit the table

(Anything surprising: latency, jitter, cursor jumps, overlay behaviour, stuck button incidents and how they were cleared.)

## Open questions answered by this run

- T2: does `BTN` read DOWN after an injected LEFTDOWN? →
- T9: did the elevated window react to any injected input? →
