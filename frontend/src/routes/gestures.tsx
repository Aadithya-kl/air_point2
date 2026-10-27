import React, { useEffect, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  Hand,
  Lock,
  MousePointer,
  Volume2,
  VolumeX,
} from "lucide-react";
import { useAirPointEngine } from "@/components/air-point/engine";
import {
  MutationFeedbackBanner,
  SettingSlider,
} from "@/components/air-point/common";
import { GestureDiagram } from "@/components/air-point/illustrations";
import { GestureTutorial } from "@/components/air-point/gesture-tutorial";
import { GestureVideoPlayer } from "@/components/air-point/gesture-video-player";
import { WakandaSimulationDeck } from "@/components/air-point/wakanda-simulation-deck";
import {
  GESTURE_SPECS,
  HOLD_DURATION_LIMITS,
  type GestureId,
  type GestureSpec,
} from "@/lib/air-point-model";

const GESTURE_ICONS: Record<GestureId, React.ReactNode> = {
  pointer: <MousePointer className="w-4 h-4" />,
  drag: <Hand className="w-4 h-4" />,
  screenshot: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="3" width="18" height="13" rx="2" />
      <path d="M8 21h8m-4-5v5" />
    </svg>
  ),
  whatsapp: (
    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M20 11.5a8 8 0 0 1-11.8 7L4 20l1.4-4A8 8 0 1 1 20 11.5Z" />
      <path d="M9 8.5c.5 2 2 3.5 4.5 4.5l1-1 2 1c-.4 1.5-1.7 2-3 1.5-3.5-1-5.5-3-6-5-.2-1.2.5-2 1.5-2Z" />
    </svg>
  ),
  mute: <VolumeX className="w-4 h-4" />,
  "volume-up": <Volume2 className="w-4 h-4" />,
  "volume-down": <Volume2 className="w-4 h-4" />,
  "wakanda-forever": <Lock className="w-4 h-4" />,
};

const FALLBACK_GESTURE: GestureSpec = GESTURE_SPECS[0]!;

export const GesturesPage: React.FC = () => {
  const engine = useAirPointEngine();
  const [selectedId, setSelectedId] = useState<GestureId>(() => {
    if (typeof window !== "undefined") {
      const param = new URLSearchParams(window.location.search).get("gesture") as GestureId | null;
      if (param && GESTURE_SPECS.some((g) => g.id === param)) {
        return param;
      }
    }
    return "pointer";
  });

  useEffect(() => {
    if (typeof window !== "undefined") {
      const param = new URLSearchParams(window.location.search).get("gesture") as GestureId | null;
      if (param && GESTURE_SPECS.some((g) => g.id === param)) {
        setSelectedId(param);
      }
    }
  }, []);

  const selectedGesture: GestureSpec =
    GESTURE_SPECS.find((g) => g.id === selectedId) ?? FALLBACK_GESTURE;
  const isSelectedEnabled = Boolean(engine.enabled[selectedGesture.id]);

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <div className="page-head">
        <div>
          <h1 className="page-title">Gestures</h1>
          <p className="page-sub">Configure your gesture controls.</p>
        </div>

        <div className="flex items-center gap-2">
          <span className="badge">
            <i className="dot" />
            <span>
              {engine.connected
                ? "Verified engine sync"
                : "Local preview mode"}
            </span>
          </span>
        </div>
      </div>

      <MutationFeedbackBanner
        pending={engine.pendingMutation}
        error={engine.lastMutationError}
        success={engine.lastMutationSuccess}
        onDismiss={engine.clearMutationFeedback}
      />

      {/* Master-Detail Gesture Workspace */}
      <div className="gesture-layout">
        {/* Left: Gesture Library List */}
        <section
          className="glass page-panel gesture-library-panel p-5 rounded-[22px]"
          aria-label="Gesture library"
        >
          <div className="gesture-library-head">
            <div className="gesture-library-head-titles">
              <h2 className="text-sm font-bold m-0 tracking-tight">Gesture library</h2>
              <p className="text-[10px] text-[var(--muted)] m-0 mt-0.5">
                {engine.connected ? "Real-time recognizers" : "Preview controls"}
              </p>
            </div>
            <span className="ap-label-tech shrink-0">08 GESTURES</span>
          </div>

          <div className="gesture-list">
            {GESTURE_SPECS.map((gesture) => {
              const active = gesture.id === selectedGesture.id;
              const isArmed = Boolean(engine.enabled[gesture.id]);

              return (
                <button
                  key={gesture.id}
                  type="button"
                  onClick={() => setSelectedId(gesture.id)}
                  className={`gesture-row ${active ? "active" : ""}`}
                >
                  <span className="tile-icon" aria-hidden="true">
                    {GESTURE_ICONS[gesture.id] ?? <Hand className="w-4 h-4" />}
                  </span>

                  <span className="grow min-w-0">
                    <strong className="truncate">{gesture.name}</strong>
                    <small className="truncate">{gesture.shortSummary}</small>
                  </span>

                  <span className={`row-status-text ${isArmed ? "text-[var(--accent)]" : "text-[var(--muted)]"}`}>
                    {isArmed ? "ON" : "OFF"}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        {/* Right: Gesture Inspector */}
        <section className="glass inspector p-6 rounded-[22px]" aria-label="Gesture inspector">
          {/* Anatomical Gesture Illustration Stage / Animated Tutorial / Video Player */}
          {selectedGesture.id === "mute" ? (
            <GestureTutorial
              gestureId="mute"
              reducedMotion={engine.preferences.reducedMotion}
            />
          ) : (
            <GestureVideoPlayer
              gestureId={selectedGesture.id}
              reducedMotion={engine.preferences.reducedMotion}
            />
          )}

          <span className="ap-label-tech">SELECTED GESTURE</span>
          <h2 className="text-xl font-bold mt-1 mb-2 tracking-tight">
            {selectedGesture.name}
          </h2>
          <p className="text-xs text-[var(--muted)] leading-relaxed mb-4">
            {selectedGesture.triggerCondition}
          </p>

          <div className="flex items-center justify-between p-3.5 rounded-xl border border-[var(--line-divider)] bg-[var(--surface-soft)] my-4">
            <div>
              <strong className="text-xs font-semibold block">
                Enabled in preview
              </strong>
              <span className="text-[10px] text-[var(--muted)] font-mono">
                {engine.connected ? "Active Win32 recognizer" : "Local demo state only"}
              </span>
            </div>

            <button
              type="button"
              role="switch"
              aria-checked={isSelectedEnabled}
              aria-label={`Enable ${selectedGesture.name}`}
              onClick={() =>
                engine.setGestureEnabled(selectedGesture.id, !isSelectedEnabled)
              }
              className="toggle"
            >
              <span />
            </button>
          </div>

          {/* Anatomical Landmark Details */}
          <div className="p-3.5 rounded-xl border border-[var(--line-divider)] bg-[var(--surface-soft)] space-y-2.5 text-xs">
            <div className="flex justify-between items-center py-1 border-b border-[var(--line-divider)]">
              <span className="text-[var(--muted)]">Anatomical anchor</span>
              <span className="font-mono font-medium text-right">
                {selectedGesture.anatomicalAnchor}
              </span>
            </div>

            <div className="flex justify-between items-center py-1 border-b border-[var(--line-divider)]">
              <span className="text-[var(--muted)]">Windows action</span>
              <span className="font-mono font-medium text-right">
                {selectedGesture.windowsAction}
              </span>
            </div>

            <div className="flex justify-between items-center py-1">
              <span className="text-[var(--muted)]">Engine filter</span>
              <span className="font-mono font-medium text-right">
                {selectedGesture.engineNotes}
              </span>
            </div>
          </div>

          {/* Specialized Interactive Deck for Wakanda Forever */}
          {selectedGesture.id === "wakanda-forever" && (
            <div className="mt-6 pt-4 border-t border-[var(--line)]">
              <WakandaSimulationDeck
                isArmed={isSelectedEnabled}
                onToggleArm={() =>
                  engine.setGestureEnabled(
                    "wakanda-forever",
                    !isSelectedEnabled
                  )
                }
                reducedMotion={engine.preferences.reducedMotion}
              />
            </div>
          )}

          {/* Screenshot Palm Hold Duration Slider */}
          {selectedGesture.id === "screenshot" && (
            <div className="mt-6 pt-4 border-t border-[var(--line)]">
              <SettingSlider
                id="screenshot-hold-slider"
                label="Screenshot palm hold duration"
                description="Number of seconds both open palms must remain stationary to capture the screen (Default: 3.0s)."
                value={engine.holdDuration}
                min={HOLD_DURATION_LIMITS.min}
                max={HOLD_DURATION_LIMITS.max}
                step={HOLD_DURATION_LIMITS.step}
                unit="s"
                formatValue={(v) => `${v.toFixed(1)}s`}
                minLabel={`${HOLD_DURATION_LIMITS.min}s (Fast)`}
                maxLabel={`${HOLD_DURATION_LIMITS.max}s (Deliberate)`}
                onChange={(val) => engine.setHoldDuration(val)}
              />
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export const Route = createFileRoute("/gestures")({
  component: GesturesPage,
});
