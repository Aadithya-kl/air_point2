export type GestureId =
  | "pointer"
  | "drag"
  | "screenshot"
  | "whatsapp"
  | "mute"
  | "volume-up"
  | "volume-down"
  | "wakanda-forever";

export type GestureCategory =
  | "Navigation & Selection"
  | "System Actions"
  | "Head & Facial Anchors";

export type PointerOwner = "RIGHT" | "LEFT" | "NONE";

export type ThemeMode = "obsidian" | "titanium" | "oled" | "slate";
export type AccentColor = "sage" | "cyan" | "amber" | "violet";
export type DensityMode = "comfortable" | "compact";
export type CursorPresetId = "precision" | "balanced" | "fast" | "custom";

export type DynamicIslandState =
  | "idle"
  | "screenshot"
  | "screenshot-hold"
  | "muted"
  | "unmuted"
  | "whatsapp"
  | "reacquired"
  | "lost"
  | "volume-up"
  | "volume-down"
  | "wakanda-forever"
  | "wakanda-hold"
  | "normal"
  | "power-save-waiting"
  | "power-save-countdown"
  | "power-save-complete"
  | "power-save-wake";

export interface GestureSpec {
  id: GestureId;
  name: string;
  shortSummary: string;
  category: GestureCategory;
  anatomicalAnchor: string;
  landmarksUsed: string[];
  triggerCondition: string;
  windowsAction: string;
  configurableKey?: "hold" | "sensitivity" | "smoothing";
  engineNotes: string;
}

export type DyneEventPriority = "low" | "normal" | "high" | "critical";

/**
 * One Dyne event as published by the Python engine (backend/core/events.py).
 * `id` is the stable client key (`${session}:${sequence}`); the legacy
 * `event` / `action` / `time` fields are kept because older bridge payloads
 * only carried those.
 */
export interface AirPointEvent {
  id: string;
  event: string;
  action: string;
  time: string;
  type?: string;
  sequence?: number;
  session?: string;
  timestamp?: number;
  source?: string;
  title?: string;
  message?: string;
  priority?: DyneEventPriority;
  durationS?: number;
  metadata?: Record<string, unknown>;
}

export const EVENT_HISTORY_LIMIT = 50;
const VALID_PRIORITIES = new Set<DyneEventPriority>(["low", "normal", "high", "critical"]);

/** Parses one bridge event payload (unified schema or legacy) into an AirPointEvent. */
export function parseDyneEvent(raw: unknown, fallbackIndex = 0): AirPointEvent | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const message =
    typeof r["message"] === "string"
      ? (r["message"] as string)
      : typeof r["action"] === "string"
        ? (r["action"] as string)
        : null;
  if (message === null) return null;
  const sequence = typeof r["id"] === "number" && Number.isFinite(r["id"]) ? (r["id"] as number) : undefined;
  const session = typeof r["session"] === "string" ? (r["session"] as string) : undefined;
  const time =
    typeof r["time"] === "string"
      ? (r["time"] as string)
      : new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const type =
    typeof r["event_type"] === "string"
      ? (r["event_type"] as string)
      : typeof r["type"] === "string" && (r["type"] as string).includes(".")
        ? (r["type"] as string)
        : undefined;
  const kind =
    typeof r["event"] === "string"
      ? (r["event"] as string)
      : typeof r["type"] === "string"
        ? (r["type"] as string)
        : "info";
  const id =
    sequence !== undefined
      ? `${session ?? "local"}:${sequence}`
      : `${time}-${message}-${fallbackIndex}`;
  const priorityRaw = r["priority"];
  const priority = VALID_PRIORITIES.has(priorityRaw as DyneEventPriority)
    ? (priorityRaw as DyneEventPriority)
    : undefined;
  const metadata =
    r["metadata"] && typeof r["metadata"] === "object"
      ? (r["metadata"] as Record<string, unknown>)
      : undefined;
  return {
    id,
    event: kind,
    action: message,
    time,
    ...(type !== undefined ? { type } : {}),
    ...(sequence !== undefined ? { sequence } : {}),
    ...(session !== undefined ? { session } : {}),
    ...(typeof r["timestamp"] === "number" ? { timestamp: r["timestamp"] as number } : {}),
    ...(typeof r["source"] === "string" ? { source: r["source"] as string } : {}),
    ...(typeof r["title"] === "string" ? { title: r["title"] as string } : {}),
    message,
    ...(priority !== undefined ? { priority } : {}),
    ...(typeof r["duration_s"] === "number" ? { durationS: r["duration_s"] as number } : {}),
    ...(metadata !== undefined ? { metadata } : {}),
  };
}

/**
 * Merges incoming events into the existing list: newest first, no duplicate
 * ids, bounded. Events with a sequence number order by sequence (within a
 * session); anything else falls back to timestamp / arrival order.
 */
export function mergeEvents(
  existing: AirPointEvent[],
  incoming: AirPointEvent[],
  limit: number = EVENT_HISTORY_LIMIT,
): AirPointEvent[] {
  const byId = new Map<string, AirPointEvent>();
  for (const ev of [...incoming, ...existing]) {
    if (!byId.has(ev.id)) byId.set(ev.id, ev);
  }
  const merged = Array.from(byId.values());
  const rank = (ev: AirPointEvent): number => {
    if (typeof ev.timestamp === "number") return ev.timestamp * 1000 + (ev.sequence ?? 0) / 1_000_000;
    if (typeof ev.sequence === "number") return ev.sequence;
    return 0;
  };
  merged.sort((a, b) => rank(b) - rank(a));
  return merged.slice(0, limit);
}

/** Dyne island position persisted by the engine and shared with the desktop overlay. */
export type DyneIslandPosition = "top-center" | "top-left" | "top-right" | "bottom-center";
export const DYNE_ISLAND_POSITIONS: readonly DyneIslandPosition[] = [
  "top-center",
  "top-left",
  "top-right",
  "bottom-center",
];
export const DEFAULT_DYNE_ISLAND_POSITION: DyneIslandPosition = "top-center";

export function sanitizeDynePosition(raw: unknown): DyneIslandPosition | null {
  return typeof raw === "string" && (DYNE_ISLAND_POSITIONS as readonly string[]).includes(raw)
    ? (raw as DyneIslandPosition)
    : null;
}

/** Dyne appearance (the Studio's capsule look) persisted by the engine. */
export interface DyneAppearance {
  accent: string;
  texture: string;
  font: string;
  fontSize: number;
  weight: number;
  intensity: number;
  matteIntensity: number;
  translucentIntensity: number;
  roundness: number;
  style: string;
  customRgb: { r: number; g: number; b: number };
}

export const DEFAULT_DYNE_APPEARANCE: DyneAppearance = {
  accent: "Gold",
  texture: "Glass",
  font: "System",
  fontSize: 23,
  weight: 400,
  intensity: 50,
  matteIntensity: 50,
  translucentIntensity: 50,
  roundness: 56,
  style: "Balanced",
  customRgb: { r: 140, g: 80, b: 255 },
};

const DYNE_COLOUR_HEX: Record<string, string> = {
  Brown: "#a7784c", Red: "#ef505c", Blue: "#348cff", Neon: "#b1ed4e", Green: "#3cd6a0",
  White: "#edf5ff", Grey: "#8794a1", Gold: "#f4c75b", Purple: "#b37bea", Orange: "#f7a34e",
  Cyan: "#48D8E8", Teal: "#159E98", Mint: "#91E7C0", Lime: "#C4EE52", Yellow: "#F4DB55",
  Amber: "#ED9D42", Coral: "#FF8075", Crimson: "#BD334E", Rose: "#F18BB3", Magenta: "#DC5BD8",
};

function clampInt(value: unknown, lo: number, hi: number, fallback: number): number {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(hi, Math.max(lo, Math.round(n)));
}

export function sanitizeDyneAppearance(raw: unknown, base: DyneAppearance = DEFAULT_DYNE_APPEARANCE): DyneAppearance {
  const current: DyneAppearance = { ...base, customRgb: { ...base.customRgb } };
  if (!raw || typeof raw !== "object") return current;
  const r = raw as Record<string, unknown>;
  const accent = r["accent"];
  if (typeof accent === "string" && (accent === "Custom" || accent in DYNE_COLOUR_HEX)) current.accent = accent;
  const texture = r["texture"];
  if (texture === "Matte" || texture === "Glass" || texture === "Translucent") current.texture = texture;
  const style = r["style"];
  if (style === "Luminous" || style === "Balanced" || style === "Quiet") current.style = style;
  const font = r["font"];
  if (font === "System" || font === "Mono" || font === "Humanist") current.font = font;
  current.fontSize = clampInt(r["fontSize"] ?? current.fontSize, 18, 28, current.fontSize);
  current.weight = clampInt(r["weight"] ?? current.weight, 300, 800, current.weight);
  current.intensity = clampInt(r["intensity"] ?? current.intensity, 0, 100, current.intensity);
  current.matteIntensity = clampInt(r["matteIntensity"] ?? current.matteIntensity, 0, 100, current.matteIntensity);
  current.translucentIntensity = clampInt(
    r["translucentIntensity"] ?? current.translucentIntensity, 0, 100, current.translucentIntensity,
  );
  current.roundness = clampInt(r["roundness"] ?? current.roundness, 28, 56, current.roundness);
  const rgb = r["customRgb"];
  if (rgb && typeof rgb === "object") {
    const c = rgb as Record<string, unknown>;
    current.customRgb = {
      r: clampInt(c["r"] ?? current.customRgb.r, 0, 255, current.customRgb.r),
      g: clampInt(c["g"] ?? current.customRgb.g, 0, 255, current.customRgb.g),
      b: clampInt(c["b"] ?? current.customRgb.b, 0, 255, current.customRgb.b),
    };
  }
  return current;
}

export function dyneAccentHex(appearance: DyneAppearance): string {
  if (appearance.accent === "Custom") {
    const { r, g, b } = appearance.customRgb;
    return `#${[r, g, b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;
  }
  return DYNE_COLOUR_HEX[appearance.accent] ?? DYNE_COLOUR_HEX["Gold"]!;
}

export function appearanceEquals(a: DyneAppearance | null | undefined, b: DyneAppearance | null | undefined): boolean {
  if (!a || !b) return false;
  return (
    a.accent === b.accent && a.texture === b.texture && a.font === b.font && a.fontSize === b.fontSize &&
    a.weight === b.weight && a.intensity === b.intensity && a.matteIntensity === b.matteIntensity &&
    a.translucentIntensity === b.translucentIntensity && a.roundness === b.roundness && a.style === b.style &&
    a.customRgb.r === b.customRgb.r && a.customRgb.g === b.customRgb.g && a.customRgb.b === b.customRgb.b
  );
}

export interface UIPreferences {
  theme: ThemeMode;
  lastDarkTheme?: "obsidian" | "oled" | "slate";
  accent: AccentColor;
  density: DensityMode;
  reducedMotion: boolean;
  feedbackDuration: number;
}

export interface CursorPreset {
  id: Exclude<CursorPresetId, "custom">;
  label: string;
  sensitivity: number;
  smoothing: number;
  summary: string;
}

export const UI_PREFERENCES_STORAGE_KEY = "air-point.ui-preferences.v1";
export const DEFAULT_BRIDGE_BASE_URL = "http://127.0.0.1:8765";

/**
 * Bridge discovery (F-10): the launcher reads backend/bridge_info.json after the
 * engine bound its port and passes the origin as VITE_AIRPOINT_BRIDGE_URL to the
 * dev server. Only loopback http origins are accepted; anything else falls back
 * to the default so a stray environment value can never point the Control
 * Center at a non-local host.
 */
export function resolveBridgeBaseUrl(candidate: unknown): string {
  if (typeof candidate !== "string") return DEFAULT_BRIDGE_BASE_URL;
  const trimmed = candidate.trim().replace(/\/+$/, "");
  const match = /^http:\/\/(127\.0\.0\.1|localhost|\[::1\])(?::(\d{1,5}))?$/i.exec(trimmed);
  if (!match) return DEFAULT_BRIDGE_BASE_URL;
  const port = match[2] !== undefined ? Number(match[2]) : 80;
  if (!Number.isInteger(port) || port < 1 || port > 65535) return DEFAULT_BRIDGE_BASE_URL;
  return `http://${match[1]!.toLowerCase()}${match[2] !== undefined ? `:${port}` : ""}`;
}

export const BRIDGE_BASE_URL: string = resolveBridgeBaseUrl(
  (import.meta.env as unknown as Record<string, unknown>)["VITE_AIRPOINT_BRIDGE_URL"],
);

/** Host:port shown in status pills, derived from the resolved bridge URL. */
export function bridgeHostLabel(bridgeUrl: string): string {
  return bridgeUrl.replace(/^https?:\/\//i, "");
}

export const DEFAULT_SENSITIVITY = 0.85;
export const DEFAULT_SMOOTHING = 65;
export const DEFAULT_HOLD_DURATION = 3.0;
export const DEFAULT_FEEDBACK_DURATION = 1.8;

export const SENSITIVITY_LIMITS = {
  uiMin: 0.5,
  uiMax: 2.5,
  backendMin: 0.2,
  backendMax: 4.0,
  step: 0.05,
} as const;

export const SMOOTHING_LIMITS = {
  uiMin: 10,
  uiMax: 100,
  backendMin: 10,
  backendMax: 100,
  step: 1,
} as const;

export const HOLD_DURATION_LIMITS = {
  min: 1.0,
  max: 5.0,
  step: 0.5,
} as const;

export interface DynamicIslandSettings {
  enabled: boolean;
  notificationsEnabled: boolean;
  timerEnabled: boolean;
  autohideEnabled: boolean;
  hudDurationS: number;
  completionDurationS: number;
}

export const DEFAULT_DYNAMIC_ISLAND_SETTINGS: DynamicIslandSettings = {
  enabled: true,
  notificationsEnabled: true,
  timerEnabled: true,
  autohideEnabled: true,
  hudDurationS: 120, // 2 minutes
  completionDurationS: 2.0,
};

export const ISLAND_HUD_DURATION_LIMITS = {
  min: 10,
  max: 1800,
  step: 10,
} as const;

export const ISLAND_COMPLETION_DURATION_LIMITS = {
  min: 1.0,
  max: 5.0,
  step: 0.5,
} as const;

export const DEFAULT_UI_PREFERENCES: UIPreferences = {
  theme: "obsidian",
  lastDarkTheme: "obsidian",
  accent: "sage",
  density: "comfortable",
  reducedMotion: false,
  feedbackDuration: DEFAULT_FEEDBACK_DURATION,
};

export const THEME_OPTIONS: ReadonlyArray<{
  id: ThemeMode;
  name: string;
  subtitle: string;
  canvasHex: string;
  surfaceHex: string;
  borderHex: string;
  textHex: string;
}> = [
  {
    id: "obsidian",
    name: "Obsidian Dark",
    subtitle: "Primary Aero Obsidian precision instrument deck",
    canvasHex: "#0b0d11",
    surfaceHex: "#11141b",
    borderHex: "#283040",
    textHex: "#f1f5f9",
  },
  {
    id: "titanium",
    name: "Titanium Light",
    subtitle: "High-contrast daylight lab utility",
    canvasHex: "#eef1f6",
    surfaceHex: "#ffffff",
    borderHex: "#cbd5e1",
    textHex: "#0f172a",
  },
  {
    id: "oled",
    name: "OLED Black",
    subtitle: "Zero-luminance true black canvas with crisp borders",
    canvasHex: "#000000",
    surfaceHex: "#060709",
    borderHex: "#27272a",
    textHex: "#ffffff",
  },
  {
    id: "slate",
    name: "Nordic Slate",
    subtitle: "Cool architectural slate-blue control surface",
    canvasHex: "#0c1322",
    surfaceHex: "#131d31",
    borderHex: "#2b3f61",
    textHex: "#f8fafc",
  },
];

export const ACCENT_OPTIONS: ReadonlyArray<{
  id: AccentColor;
  name: string;
  swatchHex: string;
  description: string;
}> = [
  {
    id: "sage",
    name: "Cyber Sage",
    swatchHex: "#10b981",
    description: "Signature Air Point spatial telemetry emerald",
  },
  {
    id: "cyan",
    name: "Hyper Cyan",
    swatchHex: "#06b6d4",
    description: "High-contrast optical reticle cyan",
  },
  {
    id: "amber",
    name: "Electric Amber",
    swatchHex: "#f59e0b",
    description: "Avionics-grade tactical amber readout",
  },
  {
    id: "violet",
    name: "Amethyst Violet",
    swatchHex: "#8b5cf6",
    description: "Deep-spectrum neural telemetry violet",
  },
];

export const CURSOR_PRESETS: ReadonlyArray<CursorPreset> = [
  {
    id: "precision",
    label: "Precision",
    sensitivity: 0.6,
    smoothing: 85,
    summary: "0.60× sensitivity · 85% smoothing for fine pixel targeting",
  },
  {
    id: "balanced",
    label: "Balanced",
    sensitivity: 0.85,
    smoothing: 65,
    summary: "0.85× sensitivity · 65% smoothing (Verified engine default)",
  },
  {
    id: "fast",
    label: "Fast",
    sensitivity: 1.5,
    smoothing: 35,
    summary: "1.50× sensitivity · 35% smoothing for rapid multi-monitor sweep",
  },
];

export const GESTURE_SPECS: ReadonlyArray<GestureSpec> = [
  {
    id: "pointer",
    name: "Pointer & click",
    shortSummary: "Right-hand navigation",
    category: "Navigation & Selection",
    anatomicalAnchor: "Right Hand · Index Tip (#8) & Thumb Tip (#4)",
    landmarksUsed: ["INDEX_FINGER_TIP (#8)", "THUMB_TIP (#4)", "WRIST (#0)"],
    triggerCondition:
      "Index fingertip steers the cursor. Bring the thumb and index finger together to click or double-pinch to double-click.",
    windowsAction: "Move the Windows cursor and perform a primary click or double-click via Win32 SendInput.",
    configurableKey: "sensitivity",
    engineNotes:
      "Filtered in real time by the Python OneEuroFilter using your active Cursor Sensitivity and Cursor Smoothing parameters.",
  },
  {
    id: "drag",
    name: "Drag & drop",
    shortSummary: "Left-hand selection",
    category: "Navigation & Selection",
    anatomicalAnchor: "Left Hand · Thumb Tip (#4) + Index Tip (#8) Pinch Hold",
    landmarksUsed: ["LEFT_THUMB_TIP (#4)", "LEFT_INDEX_FINGER_TIP (#8)"],
    triggerCondition:
      "Pinch left thumb and index finger together and hold while moving your hand across the frame; release pinch to drop.",
    windowsAction: "Holds Win32 left mouse button down, tracks cursor translation, and releases on unpinch.",
    configurableKey: "smoothing",
    engineNotes:
      "Uses hysteresis deadband inside the Python gesture state machine to prevent accidental drops during hand translation.",
  },
  {
    id: "screenshot",
    name: "Screenshot",
    shortSummary: "Two-hand open-palm hold",
    category: "System Actions",
    anatomicalAnchor: "Both Hands · Open Palms (Thumbs Inward)",
    landmarksUsed: ["LEFT_HAND (21 joints)", "RIGHT_HAND (21 joints)"],
    triggerCondition:
      "Raise both open palms facing the camera with thumbs oriented inward and hold steady for the configured hold threshold.",
    windowsAction: "Captures full Windows desktop screenshot and triggers the native Dynamic Island capture confirmation.",
    configurableKey: "hold",
    engineNotes:
      "Hold duration is live-configurable between 1.0s and 5.0s (default 3.0s) via POST /api/settings { hold }.",
  },
  {
    id: "whatsapp",
    name: "Open WhatsApp",
    shortSummary: "Two-hand W gesture",
    category: "System Actions",
    anatomicalAnchor: "Both Hands · Two-Hand 'W' Pose",
    landmarksUsed: ["LEFT_HAND_THUMB_INDEX", "RIGHT_HAND_THUMB_INDEX"],
    triggerCondition:
      "Form a 'W' silhouette by joining the inner thumbs and index fingers of both hands inside the tracking frame.",
    windowsAction: "Launches or focuses the Windows WhatsApp Desktop application with cooldown protection.",
    engineNotes:
      "Pose geometry tolerances and launch cooldown timers are managed deterministically by the Python recognizer.",
  },
  {
    id: "wakanda-forever",
    name: "Lock Screen",
    shortSummary: "Crossed-arm chest hold",
    category: "System Actions",
    anatomicalAnchor: "Both Forearms Crossed Over Chest (Fists Closed)",
    landmarksUsed: ["LEFT_WRIST (#0)", "RIGHT_WRIST (#0)", "FIST_JOINTS (#1-#20)"],
    triggerCondition:
      "Cross both forearms over your chest with closed fists and hold steady for 2.0 continuous seconds.",
    windowsAction: "Locks the Windows workstation immediately via Win32 LockWorkStation.",
    engineNotes:
      "Requires crossed arm geometry and a continuous 2.0s hold, then a 2.0s cooldown and release before it can fire again. Enabled by default; switch it off here if you do not want a lock gesture.",
  },
  {
    id: "mute",
    name: "Mute / unmute",
    shortSummary: "Index finger at lips",
    category: "Head & Facial Anchors",
    anatomicalAnchor: "Index Fingertip (#8) to Lip Center Anchor",
    landmarksUsed: ["INDEX_FINGER_TIP (#8)", "FACE_LIPS_CENTER (#13/#14)"],
    triggerCondition:
      "Bring your raised index fingertip onto the central lip landmark anchor and hold briefly to toggle system mute.",
    windowsAction: "Toggles Windows master audio mute state via CoreAudio / Pycaw.",
    engineNotes:
      "Requires both hand landmark #8 and MediaPipe FaceMesh lip anchor visibility within the normalized proximity radius.",
  },
  {
    id: "volume-up",
    name: "Volume up",
    shortSummary: "Index finger at right ear",
    category: "Head & Facial Anchors",
    anatomicalAnchor: "Index Fingertip (#8) to Right Ear Anchor",
    landmarksUsed: ["INDEX_FINGER_TIP (#8)", "FACE_RIGHT_EAR (#234)"],
    triggerCondition:
      "Touch or hold your index fingertip near the right ear facial landmark to step Windows master volume upward.",
    windowsAction: "Increments Windows master output volume while held at the right ear anchor.",
    engineNotes:
      "Step rate and proximity radius are governed by the Python facial-anchor recognizer.",
  },
  {
    id: "volume-down",
    name: "Volume down",
    shortSummary: "Index finger at left ear",
    category: "Head & Facial Anchors",
    anatomicalAnchor: "Index Fingertip (#8) to Left Ear Anchor",
    landmarksUsed: ["INDEX_FINGER_TIP (#8)", "FACE_LEFT_EAR (#454)"],
    triggerCondition:
      "Touch or hold your index fingertip near the left ear facial landmark to step Windows master volume downward.",
    windowsAction: "Decrements Windows master output volume while held at the left ear anchor.",
    engineNotes:
      "Step rate and proximity radius are governed by the Python facial-anchor recognizer.",
  },
];

export const DEFAULT_ENABLED_GESTURES: Record<GestureId, boolean> = {
  pointer: true,
  drag: true,
  screenshot: true,
  whatsapp: true,
  mute: true,
  "volume-up": true,
  "volume-down": true,
  "wakanda-forever": true,
};

export function clampSensitivity(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_SENSITIVITY;
  const clamped = Math.min(
    SENSITIVITY_LIMITS.backendMax,
    Math.max(SENSITIVITY_LIMITS.backendMin, value)
  );
  return Math.round(clamped * 100) / 100;
}

export function clampSmoothing(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_SMOOTHING;
  return Math.round(
    Math.min(SMOOTHING_LIMITS.backendMax, Math.max(SMOOTHING_LIMITS.backendMin, value))
  );
}

export function clampHoldDuration(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_HOLD_DURATION;
  const clamped = Math.min(
    HOLD_DURATION_LIMITS.max,
    Math.max(HOLD_DURATION_LIMITS.min, value)
  );
  return Math.round(clamped * 10) / 10;
}

export function resolveCursorPreset(
  sensitivity: number,
  smoothing: number
): CursorPresetId {
  const match = CURSOR_PRESETS.find(
    (p) =>
      Math.abs(p.sensitivity - sensitivity) < 0.02 &&
      Math.abs(p.smoothing - smoothing) <= 1
  );
  return match ? match.id : "custom";
}

const VALID_THEMES = new Set<ThemeMode>(["obsidian", "titanium", "oled", "slate"]);
const VALID_ACCENTS = new Set<AccentColor>(["sage", "cyan", "amber", "violet"]);
const VALID_DENSITIES = new Set<DensityMode>(["comfortable", "compact"]);

export function sanitizeUIPreferences(raw: unknown): UIPreferences {
  if (!raw || typeof raw !== "object") {
    return { ...DEFAULT_UI_PREFERENCES };
  }
  const candidate = raw as Record<string, unknown>;
  const rawTheme = candidate["theme"];
  let theme: ThemeMode = DEFAULT_UI_PREFERENCES.theme;
  if (rawTheme === "light") {
    theme = "titanium";
  } else if (rawTheme === "dark") {
    theme = "obsidian";
  } else if (typeof rawTheme === "string" && VALID_THEMES.has(rawTheme as ThemeMode)) {
    theme = rawTheme as ThemeMode;
  }

  const rawLastDark = candidate["lastDarkTheme"];
  let lastDarkTheme: "obsidian" | "oled" | "slate" =
    theme !== "titanium" ? (theme as "obsidian" | "oled" | "slate") : "obsidian";
  if (
    rawLastDark === "obsidian" ||
    rawLastDark === "oled" ||
    rawLastDark === "slate"
  ) {
    lastDarkTheme = rawLastDark;
  }

  const accentCandidate = candidate["accent"] as AccentColor;
  const accent = VALID_ACCENTS.has(accentCandidate)
    ? accentCandidate
    : DEFAULT_UI_PREFERENCES.accent;

  const densityCandidate = candidate["density"] as DensityMode;
  const density = VALID_DENSITIES.has(densityCandidate)
    ? densityCandidate
    : DEFAULT_UI_PREFERENCES.density;

  const reducedMotionCandidate = candidate["reducedMotion"];
  const reducedMotion =
    typeof reducedMotionCandidate === "boolean"
      ? reducedMotionCandidate
      : DEFAULT_UI_PREFERENCES.reducedMotion;

  const feedbackDurationCandidate = candidate["feedbackDuration"];
  const feedbackDuration =
    typeof feedbackDurationCandidate === "number" &&
    Number.isFinite(feedbackDurationCandidate)
      ? Math.min(4.0, Math.max(0.8, Math.round(feedbackDurationCandidate * 10) / 10))
      : DEFAULT_UI_PREFERENCES.feedbackDuration;

  return {
    theme,
    lastDarkTheme,
    accent,
    density,
    reducedMotion,
    feedbackDuration,
  };
}

export function loadUIPreferences(): UIPreferences {
  if (typeof window === "undefined") {
    return { ...DEFAULT_UI_PREFERENCES };
  }
  let base: UIPreferences = { ...DEFAULT_UI_PREFERENCES };
  if (window.localStorage) {
    try {
      const raw = window.localStorage.getItem(UI_PREFERENCES_STORAGE_KEY);
      if (raw) base = sanitizeUIPreferences(JSON.parse(raw));
    } catch {
      // ignore
    }
  }
  try {
    const params = new URLSearchParams(window.location.search);
    const themeParam = params.get("theme");
    const accentParam = params.get("accent");
    const densityParam = params.get("density");
    if (themeParam || accentParam || densityParam) {
      base = sanitizeUIPreferences({
        ...base,
        ...(themeParam ? { theme: themeParam } : {}),
        ...(accentParam ? { accent: accentParam } : {}),
        ...(densityParam ? { density: densityParam } : {}),
      });
    }
  } catch {
    // ignore
  }
  return base;
}

export function saveUIPreferences(prefs: UIPreferences): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(
      UI_PREFERENCES_STORAGE_KEY,
      JSON.stringify(sanitizeUIPreferences(prefs))
    );
  } catch {
    // Ignore quota or private-browsing storage errors
  }
}

export interface DiagnosticsSnapshotInput {
  bridgeUrl: string;
  connected: boolean;
  connectionState: string;
  running: boolean;
  trackingStatus: string;
  fps: number;
  pointerOwner: PointerOwner;
  cameraStreamAvailable: boolean;
  lastHeartbeatAt: string | null;
  sensitivity: number;
  smoothing: number;
  holdDuration: number;
  enabled: Record<GestureId, boolean>;
  preferences: UIPreferences;
  recentEventCount: number;
  lastError: string | null;
  powerSave?: boolean;
  powerState?: string;
}

export function buildDiagnosticsManifest(input: DiagnosticsSnapshotInput) {
  const activeGestures = (Object.keys(input.enabled) as GestureId[]).filter(
    (k) => input.enabled[k]
  );

  return {
    schema: "air-point.diagnostics.v2",
    generatedAt: new Date().toISOString(),
    application: {
      name: "Air Point Control Center",
      designSystem: "Aero Obsidian",
      frontendStatus: "Running",
    },
    bridge: {
      baseUrl: input.bridgeUrl,
      reachable: input.connected,
      connectionState: input.connectionState,
      lastHeartbeatAt: input.lastHeartbeatAt ?? "Unavailable",
      lastError: input.lastError ?? "None",
    },
    engine: {
      running: input.connected ? input.running : "Unknown (Bridge Offline)",
      trackingState: input.connected ? input.trackingStatus : "Offline",
      processingFps: input.connected ? input.fps : "Unavailable",
      pointerOwner: input.connected ? input.pointerOwner : "Unavailable",
      operatingMode: input.connected ? (input.powerState ?? "NORMAL") : "Offline",
      cameraFeed: input.connected
        ? input.cameraStreamAvailable
          ? "Camera feed available (Resolution not reported by bridge)"
          : "Standby / Feed unavailable"
        : "Unavailable (Bridge Offline)",
    },
    settings: {
      cursorSensitivityMultiplier: input.sensitivity,
      cursorSmoothingPercent: input.smoothing,
      activePreset: resolveCursorPreset(input.sensitivity, input.smoothing),
      screenshotHoldSeconds: input.holdDuration,
      powerSaverEnabled: input.powerSave ?? false,
      armedGestureCount: `${activeGestures.length} / ${GESTURE_SPECS.length}`,
      armedGestures: activeGestures,
    },
    personalization: {
      theme: input.preferences.theme,
      accent: input.preferences.accent,
      density: input.preferences.density,
      reducedMotion: input.preferences.reducedMotion,
    },
    telemetrySession: {
      receivedSseEventsInSession: input.recentEventCount,
    },
  };
}
