import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  type AccentColor,
  type AirPointEvent,
  type CursorPresetId,
  CURSOR_PRESETS,
  DEFAULT_BRIDGE_BASE_URL,
  DEFAULT_ENABLED_GESTURES,
  DEFAULT_HOLD_DURATION,
  DEFAULT_SENSITIVITY,
  DEFAULT_SMOOTHING,
  DEFAULT_UI_PREFERENCES,
  type DensityMode,
  type DynamicIslandState,
  type GestureId,
  type PointerOwner,
  type ThemeMode,
  type UIPreferences,
  buildDiagnosticsManifest,
  clampHoldDuration,
  clampSensitivity,
  clampSmoothing,
  loadUIPreferences,
  resolveCursorPreset,
  saveUIPreferences,
} from "@/lib/air-point-model";

export type BridgeConnectionState =
  | "connecting"
  | "connected"
  | "paused"
  | "offline"
  | "error";

export interface EngineContextValue {
  // Live Bridge & Engine Telemetry
  bridgeUrl: string;
  connected: boolean;
  connectionState: BridgeConnectionState;
  running: boolean;
  fps: number;
  pointerOwner: PointerOwner;
  trackingStatus: string;
  cameraStreamAvailable: boolean;
  setCameraStreamAvailable: (available: boolean) => void;
  lastHeartbeatAt: string | null;

  // Real Engine Settings (synced via POST /api/settings)
  enabled: Record<GestureId, boolean>;
  sensitivity: number;
  smoothing: number;
  holdDuration: number;
  activePreset: CursorPresetId;

  // Mutation Status & Error Reporting
  pendingMutation: string | null;
  lastMutationError: string | null;
  lastMutationSuccess: string | null;
  clearMutationFeedback: () => void;

  // Verified Engine Mutations
  shutdownEngine: () => Promise<boolean>;
  startEngine: () => Promise<boolean>;
  toggleRunning: () => Promise<boolean>;
  setGestureEnabled: (id: GestureId, value: boolean) => Promise<boolean>;
  setSensitivity: (value: number) => Promise<boolean>;
  setSmoothing: (value: number) => Promise<boolean>;
  applyCursorPreset: (presetId: "precision" | "balanced" | "fast") => Promise<boolean>;
  setHoldDuration: (value: number) => Promise<boolean>;
  resetCursorDefaults: () => Promise<boolean>;
  refreshStatusNow: () => Promise<void>;

  // Live SSE Events (initialized empty — fixes DEF-04)
  events: AirPointEvent[];

  // In-App Dynamic Island Preview & Simulation State (Explicitly separated from OS)
  island: DynamicIslandState;
  triggerIslandPreview: (state: DynamicIslandState) => void;
  previewVolume: number;
  setPreviewVolume: (val: number | ((prev: number) => number)) => void;

  // Persistent Frontend Personalization (fixes DEF-08)
  preferences: UIPreferences;
  setTheme: (theme: ThemeMode) => void;
  setAccent: (accent: AccentColor) => void;
  setDensity: (density: DensityMode) => void;
  setReducedMotion: (reduced: boolean) => void;
  setFeedbackDuration: (seconds: number) => void;

  // Truthful Diagnostics Builder (fixes DEF-01)
  getDiagnosticsReport: () => ReturnType<typeof buildDiagnosticsManifest>;
}

const EngineContext = createContext<EngineContextValue | null>(null);

export const AirPointEngineProvider: React.FC<{
  children: React.ReactNode;
  bridgeUrl?: string;
}> = ({ children, bridgeUrl = DEFAULT_BRIDGE_BASE_URL }) => {
  // Live Engine State
  const [connected, setConnected] = useState<boolean>(false);
  const [hasAttemptedInitialConnect, setHasAttemptedInitialConnect] =
    useState<boolean>(false);
  const [running, setRunning] = useState<boolean>(false);
  const [fps, setFps] = useState<number>(0);
  const [pointerOwner, setPointerOwner] = useState<PointerOwner>("NONE");
  const [trackingStatus, setTrackingStatus] = useState<string>("Engine offline");
  const [cameraStreamAvailable, setCameraStreamAvailable] =
    useState<boolean>(false);
  const [lastHeartbeatAt, setLastHeartbeatAt] = useState<string | null>(null);

  // Engine Settings
  const [enabled, setEnabled] = useState<Record<GestureId, boolean>>({
    ...DEFAULT_ENABLED_GESTURES,
  });
  const [sensitivity, setSensitivityState] =
    useState<number>(DEFAULT_SENSITIVITY);
  const [smoothing, setSmoothingState] = useState<number>(DEFAULT_SMOOTHING);
  const [holdDuration, setHoldDurationState] = useState<number>(
    DEFAULT_HOLD_DURATION
  );

  // Mutation Feedback
  const [pendingMutation, setPendingMutation] = useState<string | null>(null);
  const [lastMutationError, setLastMutationError] = useState<string | null>(
    null
  );
  const [lastMutationSuccess, setLastMutationSuccess] = useState<string | null>(
    null
  );

  // Live SSE Activity Feed — MUST initialize empty (DEF-04 fix)
  const [events, setEvents] = useState<AirPointEvent[]>([]);

  // Simulation-Only Preview State (DEF-02 fix)
  const [island, setIsland] = useState<DynamicIslandState>("idle");
  const [previewVolume, setPreviewVolumeState] = useState<number>(68);
  const islandTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bridgeTokenRef = useRef<string | null>(null);
  const lifecycleSequenceRef = useRef<number>(0);
  const lifecycleLockRef = useRef<boolean>(false);

  // UI Personalization Preferences (DEF-08 fix)
  const [preferences, setPreferences] = useState<UIPreferences>(
    DEFAULT_UI_PREFERENCES
  );

  // Hydrate preferences safely on client mount
  useEffect(() => {
    const loaded = loadUIPreferences();
    setPreferences(loaded);
  }, []);

  // Apply theme, accent, density, and reduced-motion attributes to <html>
  useEffect(() => {
    if (typeof document === "undefined") return;
    const root = document.documentElement;
    root.setAttribute("data-theme", preferences.theme);
    root.setAttribute("data-accent", preferences.accent);
    root.setAttribute("data-density", preferences.density);
    root.setAttribute(
      "data-reduced-motion",
      preferences.reducedMotion ? "true" : "false"
    );
    if (preferences.theme === "titanium") {
      root.classList.remove("dark");
      root.classList.add("light");
    } else {
      root.classList.add("dark");
      root.classList.remove("light");
    }
  }, [preferences]);

  const updatePreferences = useCallback(
    (patch: Partial<UIPreferences>) => {
      setPreferences((prev) => {
        const next = { ...prev, ...patch };
        saveUIPreferences(next);
        return next;
      });
    },
    []
  );

  const setTheme = useCallback(
    (theme: ThemeMode) =>
      updatePreferences({
        theme,
        ...(theme !== "titanium"
          ? { lastDarkTheme: theme as "obsidian" | "oled" | "slate" }
          : {}),
      }),
    [updatePreferences]
  );
  const setAccent = useCallback(
    (accent: AccentColor) => updatePreferences({ accent }),
    [updatePreferences]
  );
  const setDensity = useCallback(
    (density: DensityMode) => updatePreferences({ density }),
    [updatePreferences]
  );
  const setReducedMotion = useCallback(
    (reducedMotion: boolean) => updatePreferences({ reducedMotion }),
    [updatePreferences]
  );
  const setFeedbackDuration = useCallback(
    (feedbackDuration: number) => updatePreferences({ feedbackDuration }),
    [updatePreferences]
  );

  // Sync settings snapshot from backend payload
  const applySettingsPayload = useCallback((settings: Record<string, unknown>) => {
    if (!settings || typeof settings !== "object") return;
    const sensitivityVal = settings["sensitivity"];
    if (typeof sensitivityVal === "number") {
      setSensitivityState(clampSensitivity(sensitivityVal));
    }
    const smoothingVal = settings["smoothing"];
    if (typeof smoothingVal === "number") {
      setSmoothingState(clampSmoothing(smoothingVal));
    }
    const holdVal = settings["hold"];
    if (typeof holdVal === "number") {
      setHoldDurationState(clampHoldDuration(holdVal));
    }
    const enabledVal = settings["enabled"];
    if (enabledVal && typeof enabledVal === "object") {
      setEnabled((prev) => ({
        ...prev,
        ...(enabledVal as Partial<Record<GestureId, boolean>>),
      }));
    }
  }, []);

  // Poll GET /api/status every 1500ms
  const refreshStatusNow = useCallback(async () => {
    const pollSequence = lifecycleSequenceRef.current;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2000);
    try {
      const res = await fetch(`${bridgeUrl}/api/status`, {
        signal: controller.signal,
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setConnected(true);
      setHasAttemptedInitialConnect(true);

      // Stale response guard: only update running and trackingStatus if this poll
      // matches the current lifecycle sequence and no mutation is in flight
      if (pollSequence === lifecycleSequenceRef.current && !lifecycleLockRef.current) {
        setRunning(Boolean(data.running));
        setTrackingStatus(
          typeof data.tracking === "string"
            ? data.tracking
            : data.running
            ? "Active"
            : "Stopped"
        );
      }
      setFps(typeof data.fps === "number" ? Math.round(data.fps) : 0);
      const owner = String(data.owner ?? "NONE").toUpperCase();
      setPointerOwner(
        owner === "RIGHT" || owner === "LEFT" ? owner : "NONE"
      );
      setCameraStreamAvailable(Boolean(data.running));
      setLastHeartbeatAt(new Date().toISOString());
      if (typeof data.token === "string") {
        bridgeTokenRef.current = data.token;
      }

      if (data.settings && typeof data.settings === "object") {
        applySettingsPayload(data.settings as Record<string, unknown>);
      }
      if (Array.isArray(data.events) && data.events.length > 0) {
        setEvents((prev) => {
          const incoming: AirPointEvent[] = data.events.map(
            (ev: Record<string, unknown>, idx: number) => {
              const timeVal = ev["time"];
              const actionVal = ev["action"];
              const eventVal = ev["event"];
              return {
                id: `${timeVal ?? "t"}-${actionVal ?? idx}`,
                event: String(eventVal ?? "info"),
                action: String(actionVal ?? "System event"),
                time: String(timeVal ?? "Just now"),
              };
            }
          );
          return incoming.slice(0, 12);
        });
      }
    } catch {
      if (pollSequence === lifecycleSequenceRef.current && !lifecycleLockRef.current) {
        setConnected(false);
        setHasAttemptedInitialConnect(true);
        setRunning(false);
        setFps(0);
        setPointerOwner("NONE");
        setTrackingStatus("Engine offline");
        setCameraStreamAvailable(false);
      }
    } finally {
      clearTimeout(timer);
    }
  }, [bridgeUrl, applySettingsPayload]);

  useEffect(() => {
    refreshStatusNow();
    const interval = setInterval(refreshStatusNow, 1500);
    return () => clearInterval(interval);
  }, [refreshStatusNow]);

  // Subscribe to GET /api/events SSE stream
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    let es: EventSource | null = null;
    try {
      es = new EventSource(`${bridgeUrl}/api/events`);
      es.onmessage = (msg) => {
        try {
          const parsed = JSON.parse(msg.data);
          if (parsed && parsed.action) {
            const newEvent: AirPointEvent = {
              id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
              event: String(parsed.event ?? "gesture"),
              action: String(parsed.action),
              time: String(
                parsed.time ??
                  new Date().toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })
              ),
            };
            setEvents((prev) => [newEvent, ...prev].slice(0, 12));
          }
        } catch {
          // Ignore malformed SSE keepalive frames
        }
      };
    } catch {
      // EventSource connection failure handled via /api/status heartbeat
    }
    return () => {
      if (es) es.close();
    };
  }, [bridgeUrl]);

  // Helper for POST /api/settings
  const postSettingsMutation = useCallback(
    async (
      label: string,
      payload: Record<string, unknown>,
      onSuccessLocal: () => void
    ): Promise<boolean> => {
      setPendingMutation(label);
      setLastMutationError(null);
      setLastMutationSuccess(null);

      try {
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
        };
        if (bridgeTokenRef.current) {
          headers["X-AirPoint-Token"] = bridgeTokenRef.current;
        }
        const res = await fetch(`${bridgeUrl}/api/settings`, {
          method: "POST",
          headers,
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          throw new Error(`Engine returned HTTP ${res.status}`);
        }
        const data = await res.json().catch(() => ({}));
        onSuccessLocal();
        if (data && typeof data === "object") {
          applySettingsPayload(
            (data.settings as Record<string, unknown>) ?? data
          );
        }
        setLastMutationSuccess(`${label} synced to Python engine`);
        return true;
      } catch {
        setLastMutationError(
          `Cannot apply "${label}" while Python bridge (127.0.0.1:8765) is unreachable.`
        );
        return false;
      } finally {
        setPendingMutation(null);
      }
    },
    [bridgeUrl, applySettingsPayload]
  );

  const shutdownEngine = useCallback(async (): Promise<boolean> => {
    if (lifecycleLockRef.current) {
      return false;
    }
    lifecycleLockRef.current = true;
    setPendingMutation("Shutting down tracking");
    setLastMutationError(null);
    setLastMutationSuccess(null);
    lifecycleSequenceRef.current += 1;

    try {
      const headers: Record<string, string> = {};
      if (bridgeTokenRef.current) {
        headers["X-AirPoint-Token"] = bridgeTokenRef.current;
      }
      let res: Response | null = null;
      res = await fetch(`${bridgeUrl}/api/stop`, {
        method: "POST",
        headers,
      });

      if (res && res.status === 404) {
        res = await fetch(`${bridgeUrl}/api/toggle`, {
          method: "POST",
          headers,
        });
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const nextRunning = Boolean(data.running);
      setConnected(true);
      setRunning(nextRunning);
      setTrackingStatus(nextRunning ? "Active" : "Stopped");
      setLastMutationSuccess("Engine tracking shut down");
      return true;
    } catch {
      setLastMutationError(
        "Engine offline — start python main.py to manage tracking."
      );
      return false;
    } finally {
      setPendingMutation(null);
      lifecycleLockRef.current = false;
    }
  }, [bridgeUrl]);

  const startEngine = useCallback(async (): Promise<boolean> => {
    if (lifecycleLockRef.current) {
      return false;
    }
    lifecycleLockRef.current = true;
    setPendingMutation("Starting tracking");
    setLastMutationError(null);
    setLastMutationSuccess(null);
    lifecycleSequenceRef.current += 1;

    try {
      const headers: Record<string, string> = {};
      if (bridgeTokenRef.current) {
        headers["X-AirPoint-Token"] = bridgeTokenRef.current;
      }
      let res: Response | null = null;
      res = await fetch(`${bridgeUrl}/api/start`, {
        method: "POST",
        headers,
      });

      if (res && res.status === 404) {
        res = await fetch(`${bridgeUrl}/api/toggle`, {
          method: "POST",
          headers,
        });
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const nextRunning = Boolean(data.running);
      setConnected(true);
      setRunning(nextRunning);
      setTrackingStatus(nextRunning ? "Active" : "Stopped");
      setLastMutationSuccess("Engine tracking started");
      return true;
    } catch {
      setLastMutationError(
        "Engine offline — start python main.py to manage tracking."
      );
      return false;
    } finally {
      setPendingMutation(null);
      lifecycleLockRef.current = false;
    }
  }, [bridgeUrl]);

  const toggleRunning = useCallback(async (): Promise<boolean> => {
    if (running) {
      return shutdownEngine();
    } else {
      return startEngine();
    }
  }, [running, shutdownEngine, startEngine]);

  const setGestureEnabled = useCallback(
    async (id: GestureId, value: boolean): Promise<boolean> => {
      const nextEnabled = { ...enabled, [id]: value };
      return postSettingsMutation(
        `${id} ${value ? "enabled" : "disabled"}`,
        { enabled: nextEnabled },
        () => setEnabled(nextEnabled)
      );
    },
    [enabled, postSettingsMutation]
  );

  const setSensitivity = useCallback(
    async (value: number): Promise<boolean> => {
      const safe = clampSensitivity(value);
      return postSettingsMutation(
        `Sensitivity ${safe.toFixed(2)}×`,
        { sensitivity: safe },
        () => setSensitivityState(safe)
      );
    },
    [postSettingsMutation]
  );

  const setSmoothing = useCallback(
    async (value: number): Promise<boolean> => {
      const safe = clampSmoothing(value);
      return postSettingsMutation(
        `Smoothing ${safe}%`,
        { smoothing: safe },
        () => setSmoothingState(safe)
      );
    },
    [postSettingsMutation]
  );

  const applyCursorPreset = useCallback(
    async (presetId: "precision" | "balanced" | "fast"): Promise<boolean> => {
      const preset = CURSOR_PRESETS.find((p) => p.id === presetId);
      if (!preset) return false;
      return postSettingsMutation(
        `${preset.label} preset`,
        { sensitivity: preset.sensitivity, smoothing: preset.smoothing },
        () => {
          setSensitivityState(preset.sensitivity);
          setSmoothingState(preset.smoothing);
        }
      );
    },
    [postSettingsMutation]
  );

  const resetCursorDefaults = useCallback(async (): Promise<boolean> => {
    return postSettingsMutation(
      "Default cursor calibration",
      {
        sensitivity: DEFAULT_SENSITIVITY,
        smoothing: DEFAULT_SMOOTHING,
      },
      () => {
        setSensitivityState(DEFAULT_SENSITIVITY);
        setSmoothingState(DEFAULT_SMOOTHING);
      }
    );
  }, [postSettingsMutation]);

  const setHoldDuration = useCallback(
    async (value: number): Promise<boolean> => {
      const safe = clampHoldDuration(value);
      return postSettingsMutation(
        `Screenshot hold ${safe.toFixed(1)}s`,
        { hold: safe },
        () => setHoldDurationState(safe)
      );
    },
    [postSettingsMutation]
  );

  const triggerIslandPreview = useCallback(
    (state: DynamicIslandState) => {
      if (islandTimeoutRef.current) {
        clearTimeout(islandTimeoutRef.current);
      }
      setIsland(state);
      if (state !== "idle") {
        islandTimeoutRef.current = setTimeout(() => {
          setIsland("idle");
        }, preferences.feedbackDuration * 1000);
      }
    },
    [preferences.feedbackDuration]
  );

  const setPreviewVolume = useCallback(
    (val: number | ((prev: number) => number)) => {
      setPreviewVolumeState((prev) => {
        const computed = typeof val === "function" ? val(prev) : val;
        const clamped = Math.min(100, Math.max(0, Math.round(computed)));
        triggerIslandPreview(clamped >= prev ? "volume-up" : "volume-down");
        return clamped;
      });
    },
    [triggerIslandPreview]
  );

  const clearMutationFeedback = useCallback(() => {
    setLastMutationError(null);
    setLastMutationSuccess(null);
  }, []);

  const connectionState: BridgeConnectionState = useMemo(() => {
    if (!hasAttemptedInitialConnect) return "connecting";
    if (!connected) return "offline";
    if (!running) return "paused";
    return "connected";
  }, [hasAttemptedInitialConnect, connected, running]);

  const activePreset = useMemo(
    () => resolveCursorPreset(sensitivity, smoothing),
    [sensitivity, smoothing]
  );

  const getDiagnosticsReport = useCallback(() => {
    return buildDiagnosticsManifest({
      bridgeUrl,
      connected,
      connectionState,
      running,
      trackingStatus,
      fps,
      pointerOwner,
      cameraStreamAvailable,
      lastHeartbeatAt,
      sensitivity,
      smoothing,
      holdDuration,
      enabled,
      preferences,
      recentEventCount: events.length,
      lastError: lastMutationError,
    });
  }, [
    bridgeUrl,
    connected,
    connectionState,
    running,
    trackingStatus,
    fps,
    pointerOwner,
    cameraStreamAvailable,
    lastHeartbeatAt,
    sensitivity,
    smoothing,
    holdDuration,
    enabled,
    preferences,
    events.length,
    lastMutationError,
  ]);

  const value = useMemo<EngineContextValue>(
    () => ({
      bridgeUrl,
      connected,
      connectionState,
      running,
      fps,
      pointerOwner,
      trackingStatus,
      cameraStreamAvailable,
      setCameraStreamAvailable,
      lastHeartbeatAt,
      enabled,
      sensitivity,
      smoothing,
      holdDuration,
      activePreset,
      pendingMutation,
      lastMutationError,
      lastMutationSuccess,
      clearMutationFeedback,
      shutdownEngine,
      startEngine,
      toggleRunning,
      setGestureEnabled,
      setSensitivity,
      setSmoothing,
      applyCursorPreset,
      setHoldDuration,
      resetCursorDefaults,
      refreshStatusNow,
      events,
      island,
      triggerIslandPreview,
      previewVolume,
      setPreviewVolume,
      preferences,
      setTheme,
      setAccent,
      setDensity,
      setReducedMotion,
      setFeedbackDuration,
      getDiagnosticsReport,
    }),
    [
      bridgeUrl,
      connected,
      connectionState,
      running,
      fps,
      pointerOwner,
      trackingStatus,
      cameraStreamAvailable,
      lastHeartbeatAt,
      enabled,
      sensitivity,
      smoothing,
      holdDuration,
      activePreset,
      pendingMutation,
      lastMutationError,
      lastMutationSuccess,
      clearMutationFeedback,
      shutdownEngine,
      startEngine,
      toggleRunning,
      setGestureEnabled,
      setSensitivity,
      setSmoothing,
      applyCursorPreset,
      setHoldDuration,
      resetCursorDefaults,
      refreshStatusNow,
      events,
      island,
      triggerIslandPreview,
      previewVolume,
      setPreviewVolume,
      preferences,
      setTheme,
      setAccent,
      setDensity,
      setReducedMotion,
      setFeedbackDuration,
      getDiagnosticsReport,
    ]
  );

  return (
    <EngineContext.Provider value={value}>{children}</EngineContext.Provider>
  );
};

export function useAirPointEngine(): EngineContextValue {
  const ctx = useContext(EngineContext);
  if (!ctx) {
    throw new Error(
      "useAirPointEngine must be used within an AirPointEngineProvider"
    );
  }
  return ctx;
}
