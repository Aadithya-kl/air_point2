import React from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Activity,
  Camera,
  ChevronRight,
  Cpu,
  Eye,
  Gauge,
  Hand,
  Lock,
  Maximize2,
  MousePointer,
  Radio,
  Volume2,
  VolumeX,
  Zap,
} from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { useAirPointEngine } from "@/components/air-point/engine";
import { MutationFeedbackBanner } from "@/components/air-point/common";
import { LiveTrackingCanvas } from "@/components/air-point/live-tracking-canvas";
import { GESTURE_SPECS, type GestureId } from "@/lib/air-point-model";

const GESTURE_ICONS: Record<GestureId, React.ReactNode> = {
  pointer: <MousePointer className="w-3.5 h-3.5" />,
  drag: <Hand className="w-3.5 h-3.5" />,
  screenshot: (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="3" width="18" height="13" rx="2" />
      <path d="M8 21h8m-4-5v5" />
    </svg>
  ),
  whatsapp: (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M20 11.5a8 8 0 0 1-11.8 7L4 20l1.4-4A8 8 0 1 1 20 11.5Z" />
      <path d="M9 8.5c.5 2 2 3.5 4.5 4.5l1-1 2 1c-.4 1.5-1.7 2-3 1.5-3.5-1-5.5-3-6-5-.2-1.2.5-2 1.5-2Z" />
    </svg>
  ),
  mute: <VolumeX className="w-3.5 h-3.5" />,
  "volume-up": <Volume2 className="w-3.5 h-3.5" />,
  "volume-down": <Volume2 className="w-3.5 h-3.5" />,
  "wakanda-forever": <Lock className="w-3.5 h-3.5" />,
};

export const OverviewPage: React.FC = () => {
  const engine = useAirPointEngine();

  const armedCount = Object.values(engine.enabled).filter(Boolean).length;

  const cameraValue = engine.connected
    ? engine.cameraStreamAvailable
      ? "Active"
      : "Standby"
    : "Unavailable";

  const cameraSublabel = engine.connected
    ? engine.cameraStreamAvailable
      ? "MJPEG stream active · Resolution not reported"
      : "Waiting for camera stream"
    : "No live camera feed";

  // Section 7 Requirement: Show at most the three most recent events, newest first.
  // Group consecutive identical events (such as repeated volume triggers) to eliminate clutter.
  const displayRecentEvents = React.useMemo(() => {
    if (!engine.events || engine.events.length === 0) return [];
    const grouped: (typeof engine.events[0] & { count: number })[] = [];
    for (const ev of engine.events) {
      const prev = grouped[grouped.length - 1];
      if (prev && prev.action === ev.action && prev.event === ev.event) {
        prev.count += 1;
      } else {
        grouped.push({ ...ev, count: 1 });
      }
      if (grouped.length >= 3) break;
    }
    return grouped.slice(0, 3);
  }, [engine.events]);

  return (
    <div className="space-y-6">
      {/* Overview Page Header */}
      <div className="overview-header">
        <div>
          <h1 className="overview-title">Overview</h1>
          <p className="overview-sub">Camera, tracking and gesture status.</p>
        </div>

        <div className="nothing-quote-block hidden md:block">
          <div>YOUR HANDS. YOUR SHORTCUTS. YOUR WORLD.</div>
          <div className="opacity-70 mt-0.5">AIR POINT v1.0.0</div>
        </div>
      </div>

      <MutationFeedbackBanner
        pending={engine.pendingMutation}
        error={engine.lastMutationError}
        success={engine.lastMutationSuccess}
        onDismiss={engine.clearMutationFeedback}
      />

      {/* Primary Grid: Spatial Tracking Viewport + 2x2 Telemetry Cards */}
      <div className="overview-primary-grid">
        {/* Left: Spatial Tracking Viewport Card */}
        <section className="spatial-viewport-card" aria-label="Spatial tracking viewport">
          <div className="viewport-top-bar">
            <div className={`viewport-status-indicator ${engine.connected ? "connected" : ""}`}>
              <span className="dot" />
              <span>{engine.connected ? "LIVE TRACKING" : "DEMO MODE"}</span>
            </div>
            <div className="flex items-center gap-3">
              <span>{engine.connected ? "20 HZ POLLING" : "640 × 480"}</span>
            </div>
          </div>

          {/* Canvas Wrapper */}
          <div className="relative flex-1 min-h-[360px] bg-[#0c0c0e]">
            <LiveTrackingCanvas
              connected={engine.connected}
              running={engine.running}
              trackingStatus={engine.trackingStatus}
              pointerOwner={engine.pointerOwner}
              bridgeUrl={engine.bridgeUrl}
              onStreamStatusChange={engine.setCameraStreamAvailable}
              reducedMotion={engine.preferences.reducedMotion}
            />
          </div>
        </section>

        {/* Right: 2x2 Telemetry Glass Cards Stack */}
        <section className="telemetry-stack-2x2" aria-label="System telemetry metrics">
          {/* 1. Engine State */}
          <div className="telemetry-glass-card">
            <div className="telemetry-header">
              <span>ENGINE STATE</span>
              <Cpu className="w-3.5 h-3.5 text-[var(--muted2)]" />
            </div>
            <div className="telemetry-body">
              <div className="telemetry-main-value">
                {engine.connected
                  ? engine.running
                    ? "Active"
                    : "Paused"
                  : "Offline"}
              </div>
              <div className="telemetry-note">
                {engine.connected
                  ? `Bridge linked · ${engine.trackingStatus}`
                  : "Python engine not connected"}
              </div>
            </div>
          </div>

          {/* 2. Camera Input */}
          <div className="telemetry-glass-card">
            <div className="telemetry-header">
              <span>CAMERA INPUT</span>
              <Camera className="w-3.5 h-3.5 text-[var(--muted2)]" />
            </div>
            <div className="telemetry-body">
              <div className="telemetry-main-value">
                {cameraValue}
              </div>
              <div className="telemetry-note">{cameraSublabel}</div>
            </div>
          </div>

          {/* 3. Processing FPS with Vertical Sparkline Bars */}
          <div className="telemetry-glass-card">
            <div className="telemetry-header">
              <span>PROCESSING FPS</span>
              <Gauge className="w-3.5 h-3.5 text-[var(--muted2)]" />
            </div>
            <div className="telemetry-body">
              <div className="flex items-baseline justify-between">
                <div className="telemetry-main-value">
                  {engine.connected && engine.fps > 0 ? `${engine.fps} FPS` : "—"}
                </div>
                <div className="sparkline-bars" aria-hidden="true">
                  <span style={{ height: "40%" }} />
                  <span style={{ height: "70%" }} />
                  <span style={{ height: "55%" }} />
                  <span style={{ height: "90%" }} />
                  <span style={{ height: "65%" }} />
                  <span style={{ height: "85%" }} />
                  <span style={{ height: "100%" }} />
                </div>
              </div>
              <div className="telemetry-note">
                {engine.connected && engine.fps > 0
                  ? "Real-time MediaPipe inference"
                  : "Waiting for real engine data"}
              </div>
            </div>
          </div>

          {/* 4. Cursor Hand */}
          <div className="telemetry-glass-card">
            <div className="telemetry-header">
              <span>CURSOR HAND</span>
              <Hand className="w-3.5 h-3.5 text-[var(--muted2)]" />
            </div>
            <div className="telemetry-body">
              <div className="telemetry-main-value">
                {engine.pointerOwner === "NONE"
                  ? "None"
                  : `${engine.pointerOwner} Hand`}
              </div>
              <div className="telemetry-note">
                {engine.pointerOwner === "NONE"
                  ? "No live pointer owner"
                  : "Active Win32 pointer owner"}
              </div>
            </div>
          </div>

          {/* 5. Power Management */}
          <div className="telemetry-glass-card col-span-2">
            <div className="telemetry-header">
              <span>POWER MANAGEMENT</span>
              <Zap className={`w-3.5 h-3.5 ${engine.powerSave ? "text-amber-400" : "text-[var(--muted2)]"}`} />
            </div>
            <div className="telemetry-body">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="telemetry-main-value text-base">
                      {engine.powerSave ? "Power Saver Active" : "Normal Mode"}
                    </span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold uppercase tracking-wider ${
                        engine.powerState === "POWER_SAVE"
                          ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                          : "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                      }`}
                    >
                      {engine.powerState === "POWER_SAVE" ? "Idle Cadence (2 Hz)" : "Full Rate (30 Hz)"}
                    </span>
                  </div>
                  <div className="telemetry-note mt-1">
                    {engine.powerSave
                      ? "Automatically drops to 2 Hz probe cadence after inactivity. Deliberate sweep wakes to full rate."
                      : "Continuous full-rate MediaPipe inference and immediate gesture responsiveness."}
                  </div>
                </div>
                <div className="pl-4">
                  <Switch
                    checked={engine.powerSave}
                    onCheckedChange={(checked) => engine.setPowerSave(checked)}
                    disabled={!engine.connected || !engine.running || Boolean(engine.pendingMutation)}
                    aria-label="Toggle Power Saver mode"
                  />
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* Gesture Controls Row (8 Horizontal Tiles) */}
      <section className="mt-8">
        <div className="gesture-section-head">
          <div className="gesture-section-title-wrap">
            <div className="gesture-section-icon" aria-hidden="true">
              <Hand className="w-4 h-4" />
            </div>
            <div>
              <h2 className="gesture-section-title">Gesture Controls</h2>
              <p className="gesture-section-sub">
                Your hands. Your shortcuts. Your world. · {armedCount} of {GESTURE_SPECS.length} armed
              </p>
            </div>
          </div>

          <Link to="/gestures" className="manage-gestures-btn">
            <span>Manage gestures</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="gesture-cards-grid">
          {GESTURE_SPECS.map((gesture) => {
            const isEnabled = Boolean(engine.enabled[gesture.id]);

            return (
              <article key={gesture.id} className="gesture-glass-tile">
                <div className="tile-icon-switch-row">
                  <span className="tile-symbol" aria-hidden="true">
                    {GESTURE_ICONS[gesture.id] ?? <Hand className="w-3.5 h-3.5" />}
                  </span>

                  <button
                    type="button"
                    role="switch"
                    aria-checked={isEnabled}
                    aria-label={`Toggle ${gesture.name}`}
                    onClick={() =>
                      engine.setGestureEnabled(gesture.id, !isEnabled)
                    }
                    className="toggle"
                  >
                    <span />
                  </button>
                </div>

                <div className="tile-body">
                  <div className="tile-title">{gesture.name}</div>
                  <div className="tile-description">{gesture.shortSummary}</div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {/* Recent Activity Section (DEF-04 verified: Empty initial state, zero fabricated events) */}
      <section className="activity-glass-section">
        <div className="activity-head-row">
          <div className="activity-title-wrap">
            <Radio className="w-4 h-4 text-[var(--accent)]" />
            <h2 className="activity-title">Recent Activity</h2>
            <span className="activity-sub">Live gesture triggers</span>
          </div>
          <span className="font-mono text-[10px] tracking-wider text-[var(--muted)]">
            {engine.connected ? `${engine.events.length} EVENTS` : "LIVE EVENTS UNAVAILABLE"}
          </span>
        </div>

        {engine.events.length === 0 ? (
          <div
            data-testid="empty-recent-activity"
            className="py-6 px-4 rounded-xl border border-dashed border-[var(--line-strong)] text-center text-xs text-[var(--muted)] space-y-1"
          >
            <div className="font-semibold text-[var(--text)]">Nothing to report yet</div>
            <p>
              {engine.connected
                ? "Listening on GET /api/events. Perform an armed gesture to populate this timeline."
                : "Connect the Python engine to populate this timeline with real gesture events."}
            </p>
          </div>
        ) : (
          <div className="activity-cards-row" data-testid="recent-activity-list">
            {displayRecentEvents.map((item) => (
              <div
                key={item.id}
                data-testid="recent-activity-item"
                className="activity-mini-pill"
              >
                <div className="activity-mini-icon">
                  <span className="w-2 h-2 rounded-full bg-[var(--accent)]" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-xs truncate flex items-center gap-1.5">
                    <span>{item.action}</span>
                    {item.count > 1 && (
                      <span className="badge text-[10px] py-0 px-1 font-mono">
                        ×{item.count}
                      </span>
                    )}
                  </div>
                  <div className="font-mono text-[10px] text-[var(--muted)]">{item.time}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export const Route = createFileRoute("/")({
  component: OverviewPage,
});
