# AIR POINT — PYTHON BRIDGE CONTRACT VERIFICATION
**Document version:** 1.0.0  
**Inspection target:** `C:\Users\loges\Documents\antigravity\air_point_clean\core\control_server.py`  
**Verification status:** Authoritative, verified from source code.  
**Bridge binding:** `http://127.0.0.1:8765` (Loopback only)  

---

## 1. Executive Summary

This document establishes the authoritative API contract between the Air Point Python tracking engine (`air_point_clean`) and the React Control Center UI. Every endpoint, payload structure, data type, boundary condition, and security rule has been verified by inspecting `core/control_server.py` and `main.py` directly.

The Python control server is a lightweight, zero-dependency `ThreadingHTTPServer` operating on a dedicated daemon thread. It does not block the 30+ FPS computer vision inference loop.

---

## 2. Network & Security Architecture

| Attribute | Specification | Verification Details |
| :--- | :--- | :--- |
| **Binding Host** | `127.0.0.1` | Exclusively binds to loopback interface. Does not listen on `0.0.0.0`. |
| **Default Port** | `8765` | If port `8765` is busy, falls back dynamically to an ephemeral loopback port (`port=0`). |
| **Origin Protection** | Whitelisted | Rejects non-local origins with `403 Forbidden`. Only allows `Origin: http://127.0.0.1:*`, `http://localhost:*`, or origin-less requests (curl/scripts). |
| **Host Header Protection** | Enforced | Verifies `Host` matches `127.0.0.1` or `localhost`. Rejects DNS rebinding attacks. |
| **Payload Size Limit** | 16 KB max | Requests with `Content-Length > 16384` are rejected with `413 Payload Too Large`. |
| **CORS Headers** | Present | Sends `Access-Control-Allow-Origin`, `Methods: GET, POST, OPTIONS`, `Headers: Content-Type, Accept`. |

---

## 3. Endpoints Matrix & Payload Contracts

### 3.1. `GET /api/status`
Returns the current engine telemetry, active gesture recognizer states, persisted settings, and the recent events ring buffer.

- **Request:** `GET http://127.0.0.1:8765/api/status`
- **Response Headers:** `Content-Type: application/json; charset=utf-8`
- **Response Body Schema:**
```json
{
  "running": true,
  "tracking": "Right Hand (Pointer)",
  "fps": 31.4,
  "owner": "RIGHT",
  "volume": 68,
  "muted": false,
  "active_gesture": "pointer",
  "settings": {
    "hold": 3.0,
    "sensitivity": 0.85,
    "smoothing": 65,
    "enabled": {
      "pointer": true,
      "drag": true,
      "screenshot": true,
      "whatsapp": true,
      "mute": true,
      "volume-up": true,
      "volume-down": true
    }
  },
  "events": [
    {
      "time": "22:54:10",
      "action": "Screenshot saved",
      "type": "gesture"
    }
  ]
}
```

- **Field Semantics:**
  - `running` (boolean): `true` when tracking loop is actively processing; `false` when paused.
  - `tracking` (string): Human-readable tracking status (e.g. `"No Hands"`, `"Right Hand"`, `"Left Hand"`, `"Both Hands"`).
  - `fps` (float): Engine processing frame rate, rounded to 1 decimal place.
  - `owner` (string): Active pointer control hand: `"NONE"`, `"RIGHT"`, or `"LEFT"`.
  - `volume` (integer): Master audio volume percentage `0` to `100`.
  - `muted` (boolean): `true` if audio is currently muted.
  - `active_gesture` (string): Identifier of currently active recognizer (e.g. `"pointer"`, `"drag"`, `"idle"`).
  - `settings.hold` (float): Clamped between `1.0` and `10.0` seconds (default: `3.0`).
  - `settings.sensitivity` (float): Clamped between `0.2` and `4.0` (default: `0.85`).
  - `settings.smoothing` (integer): Clamped between `10` and `100` percent (default: `65`).
  - `settings.enabled` (dictionary): Booleans for each of the 7 supported gestures.
  - `events` (array): Max 5 recent events ring buffer; empty on clean engine start.

---

### 3.2. `POST /api/settings`
Applies partial or full updates to persisted engine settings.

- **Request:** `POST http://127.0.0.1:8765/api/settings`
- **Headers:** `Content-Type: application/json`
- **Request Body (Partial updates allowed):**
```json
{
  "hold": 3.5,
  "sensitivity": 1.10,
  "smoothing": 70,
  "enabled": {
    "drag": false
  }
}
```
- **Validation & Clamping Rules:**
  - `hold`: `clamp_val(v, 1.0, 10.0)`
  - `sensitivity`: `clamp_val(v, 0.2, 4.0)`
  - `smoothing`: `int(clamp_val(v, 10, 100))`
  - `enabled`: Keys must belong to `SUPPORTED_GESTURES`: `("pointer", "drag", "screenshot", "whatsapp", "mute", "volume-up", "volume-down")`. Values must be boolean. Unrecognized keys are ignored.
- **Persistence:** Immediately serialized to disk at `settings.json`.
- **Response:**
```json
{
  "status": "ok",
  "settings": {
    "hold": 3.5,
    "sensitivity": 1.1,
    "smoothing": 70,
    "enabled": {
      "pointer": true,
      "drag": false,
      "screenshot": true,
      "whatsapp": true,
      "mute": true,
      "volume-up": true,
      "volume-down": true
    }
  }
}
```

---

### 3.3. `POST /api/toggle`
Toggles tracking pause state.

- **Request:** `POST http://127.0.0.1:8765/api/toggle`
- **Response:**
```json
{
  "status": "ok",
  "running": false
}
```

---

### 3.4. `GET /api/landmarks`
Returns normalized spatial coordinates for hand skeletons and facial anchors at up to 20-30 FPS.

- **Request:** `GET http://127.0.0.1:8765/api/landmarks`
- **Response Headers:** `Content-Type: application/json; charset=utf-8`
- **Response Body Schema (CRITICAL):**
```json
{
  "timestamp": 1729000123.456,
  "hands": {
    "right": [
      {"x": 0.4521, "y": 0.3214, "z": -0.0123}
    ],
    "left": null
  },
  "face": {
    "detected": true,
    "lip_center": [0.4952, 0.6124],
    "right_ear": [0.3812, 0.4912],
    "left_ear": [0.6124, 0.4891],
    "mouth_width": 0.0821,
    "lip_contour": [
      [0.4512, 0.6012],
      [0.5312, 0.6014]
    ]
  },
  "tracking": "Right Hand (Pointer)",
  "owner": "RIGHT",
  "active_gesture": "pointer",
  "is_locked": true,
  "click_state": "WAITING FOR RELEASE",
  "last_pinch_norm": 0.354
}
```

> [!CAUTION]
> **Schema Contract Warning**: Notice that `hands` is a **dictionary** (`{"right": [...], "left": [...]}`), NOT an array (`[...]`). Each hand, when detected, is an array of exactly 21 normalized landmarks `[{"x": float, "y": float, "z": float}, ...]`.
> `face` is a dictionary containing `lip_center` (`[x, y]`), `lip_contour` (`[[x, y], ...]`), and ear coordinates. Any frontend client expecting an array for `hands` or `{x, y}` objects for face coordinates will experience fatal runtime exceptions.

---

### 3.5. `GET /api/camera/stream`
MJPEG multipart stream for low-latency live camera overlay.

- **Request:** `GET http://127.0.0.1:8765/api/camera/stream`
- **Response Headers:** `Content-Type: multipart/x-mixed-replace; boundary=frame`
- **Frame Rate:** Throttled to ~15 FPS (`0.066s` sleep) to eliminate CV engine overhead.
- **Image Format:** JPEG, max width 480px, quality 55%.

---

### 3.6. `GET /api/camera/frame`
Single instantaneous JPEG frame snapshot.

- **Request:** `GET http://127.0.0.1:8765/api/camera/frame`
- **Response Headers:** `Content-Type: image/jpeg`

---

### 3.7. `GET /api/events` (Server-Sent Events)
Live push event stream for zero-polling notifications.

- **Request:** `GET http://127.0.0.1:8765/api/events`
- **Response Headers:** `Content-Type: text/event-stream; Cache-Control: no-cache; Connection: keep-alive`
- **Stream Lifecycle:**
  1. Connection handshake: `: connected\ndata: {"event": "connected", "status": "ok"}\n\n`
  2. Heartbeat (every 10s if queue empty): `: ping\n\n`
  3. Real-time event push: `data: {"event": "gesture", "action": "Screenshot saved", "time": "22:54:10"}\n\n`

---

## 4. Unsupported / Non-Existent Endpoints

The following endpoints **DO NOT EXIST** in the Python control server. Frontend code must not attempt to call them:

1. **`POST /api/volume` (DOES NOT EXIST):**
   - The Python backend reads and broadcasts master volume via pycaw / CoreAudio, but does not provide an HTTP mutation endpoint.
   - Any volume sliders in the React UI must be clearly marked as **Illustrative / Preview Mode** or local feedback simulators.
2. **`POST /api/reset` (DOES NOT EXIST):**
   - To reset cursor parameters, the frontend must issue a standard `POST /api/settings` payload containing the known defaults:
     `{"sensitivity": 0.85, "smoothing": 65}`.

---

## 5. Verification Sign-Off

- **Inspection Date:** 2026-10-15
- **Verified Files:** `core/control_server.py`, `main.py`, `config.py`
- **Status:** Complete & verified. All client implementations must adhere to this document.
