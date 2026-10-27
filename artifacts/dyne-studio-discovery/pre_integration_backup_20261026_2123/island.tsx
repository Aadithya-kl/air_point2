import React, { useEffect, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  Clock,
  Eye,
  Hand,
  Info,
  Leaf,
  Monitor,
  Play,
  PlayCircle,
  RotateCcw,
  Sparkles,
  Timer,
  Zap,
} from "lucide-react";
import { useAirPointEngine } from "@/components/air-point/engine";
import { DynamicIslandPreview } from "@/components/air-point/dynamic-island";
import { CapsuleStage, type CapsuleState } from "@/components/air-point/capsule";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import {
  type DynamicIslandState,
  ISLAND_HUD_DURATION_LIMITS,
} from "@/lib/air-point-model";

const mapIslandStateToCapsuleState = (state: DynamicIslandState): CapsuleState => {
  switch (state) {
    case "power-save-countdown":
      return "COUNTDOWN";
    case "power-save-waiting":
    case "screenshot-hold":
    case "wakanda-hold":
      return "ARMED";
    case "power-save-complete":
      return "POWER_SAVE";
    case "power-save-wake":
    case "reacquired":
      return "WAKE";
    case "screenshot":
    case "muted":
    case "unmuted":
    case "whatsapp":
    case "volume-up":
    case "volume-down":
    case "wakanda-forever":
      return "ACTIVE";
    case "normal":
    case "idle":
    case "lost":
    default:
      return "IDLE";
  }
};

export const Route = createFileRoute("/island")({
  component: DynamicIslandPage,
});

export function DynamicIslandPage() {
  const engine = useAirPointEngine();
  const {
    islandSettings,
    setIslandSettings,
    testDesktopCountdown,
    lastMutationSuccess,
    lastMutationError,
  } = engine;

  // In-app preview simulation state
  const [previewState, setPreviewState] = useState<DynamicIslandState>("normal");
  const [simulatedCountdown, setSimulatedCountdown] = useState<number | null>(null);
  const [isDemoRunning, setIsDemoRunning] = useState<boolean>(false);
  const [isTestingDesktop, setIsTestingDesktop] = useState<boolean>(false);
  const demoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear demo timer on unmount
  useEffect(() => {
    return () => {
      if (demoTimerRef.current) {
        clearTimeout(demoTimerRef.current);
      }
    };
  }, []);

  // Handle countdown simulation ticking
  useEffect(() => {
    if (previewState !== "power-save-countdown" || simulatedCountdown === null) {
      return;
    }
    if (simulatedCountdown <= 0) {
      setPreviewState("power-save-complete");
      setSimulatedCountdown(null);
      return;
    }
    const timer = setTimeout(() => {
      setSimulatedCountdown((prev) => (prev !== null && prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearTimeout(timer);
  }, [previewState, simulatedCountdown]);

  const handleSimulate = (state: DynamicIslandState) => {
    if (demoTimerRef.current) {
      clearTimeout(demoTimerRef.current);
      demoTimerRef.current = null;
    }
    setIsDemoRunning(false);
    setPreviewState(state);
    if (state === "power-save-countdown") {
      setSimulatedCountdown(islandSettings.hudDurationS);
    } else {
      setSimulatedCountdown(null);
    }
  };

  const runFullLifecycleDemo = () => {
    if (demoTimerRef.current) {
      clearTimeout(demoTimerRef.current);
    }
    setIsDemoRunning(true);

    // Step 1: Normal Mode
    setPreviewState("normal");
    setSimulatedCountdown(null);

    // Step 2: Waiting for inactivity
    demoTimerRef.current = setTimeout(() => {
      setPreviewState("power-save-waiting");

      // Step 3: Inactivity reached -> Power Saver Mode with countdown
      demoTimerRef.current = setTimeout(() => {
        setPreviewState("power-save-countdown");
        setSimulatedCountdown(3);

        // Step 4: Countdown finishes -> Completion Message
        demoTimerRef.current = setTimeout(() => {
          setPreviewState("power-save-complete");
          setSimulatedCountdown(null);

          // Step 5: Hand detected -> Wake confirmation
          demoTimerRef.current = setTimeout(() => {
            setPreviewState("power-save-wake");

            // Step 6: Return to normal
            demoTimerRef.current = setTimeout(() => {
              setPreviewState("normal");
              setIsDemoRunning(false);
            }, 2500);
          }, 2500);
        }, 3200);
      }, 2500);
    }, 2000);
  };

  const handleTestDesktopCountdown = async () => {
    setIsTestingDesktop(true);
    try {
      await testDesktopCountdown(5.0);
    } finally {
      setTimeout(() => setIsTestingDesktop(false), 2000);
    }
  };

  const formatDurationLabel = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins > 0 && secs === 0) {
      return `${mins} min`;
    }
    if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  };

  return (
    <div className="space-y-6 pb-12" data-testid="dynamic-island-page">
      {/* Page Header */}
      <div>
        <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[var(--accent-primary)] mb-1">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Desktop HUD & Capsule Feedback</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
          Dynamic Island
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1 max-w-2xl">
          Configure on-screen capsule feedback, smart Power Saver countdowns,
          and preview live visual transitions before they appear on your desktop.
        </p>
      </div>

      {/* Main Grid: Live Preview Stage + Live Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Section A (2 cols): Live Preview */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-2xl border border-white/10 bg-[#0c0e14]/90 backdrop-blur-md p-6 relative overflow-hidden shadow-2xl">
            {/* Stage Ambient Glow */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-96 h-32 bg-[var(--accent-primary)]/10 blur-3xl pointer-events-none" />

            {/* Stage Header */}
            <div className="flex items-center justify-between mb-6 pb-4 border-b border-white/5 relative z-10">
              <div className="flex items-center gap-2">
                <Eye className="w-4 h-4 text-[var(--accent-primary)]" />
                <span className="text-xs font-mono font-semibold tracking-wider uppercase text-[var(--text-secondary)]">
                  Dynamic Island Preview
                </span>
              </div>
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[11px] font-mono font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                <span>PREVIEW SIMULATION (In-App Only)</span>
              </div>
            </div>

            {/* Futuristic 3D Interactive Capsule Stage (Phase 2 Foundation) */}
            <div className="mb-6 space-y-2">
              <div className="flex items-center justify-between px-1">
                <span className="text-xs font-mono font-semibold tracking-wider uppercase text-cyan-400 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                  Futuristic 3D Capsule (V3 Foundation)
                </span>
                <span className="text-[11px] font-mono text-white/40">
                  PERSPECTIVE VIEWPORT
                </span>
              </div>
              <CapsuleStage
                state={mapIslandStateToCapsuleState(previewState)}
                sublabel={
                  simulatedCountdown !== null
                    ? `${simulatedCountdown}s remaining · Sequence active`
                    : undefined
                }
              />
            </div>

            {/* Simulated Desktop Notch & Classic Capsule Stage */}
            <div className="py-6 px-4 flex flex-col items-center justify-center min-h-[140px] bg-black/40 rounded-xl border border-white/5 relative">
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-3">
                Classic 2D Desktop HUD Pill
              </div>
              {/* Virtual Top Edge Bar */}
              <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-transparent via-white/15 to-transparent" />

              {/* The Dynamic Island Preview */}
              <div className="transform scale-110 sm:scale-125 transition-all duration-300">
                <DynamicIslandPreview
                  state={previewState}
                  volume={68}
                  countdownSeconds={simulatedCountdown}
                />
              </div>

              {/* Operating State Caption */}
              <div className="mt-6 text-center text-xs font-mono text-[var(--text-secondary)]">
                Active state:{" "}
                <span className="text-[var(--text-primary)] font-semibold">
                  {previewState.toUpperCase().replace(/-/g, " ")}
                </span>
                {simulatedCountdown !== null && (
                  <span className="text-[var(--accent-primary)] ml-2">
                    ({simulatedCountdown}s remaining)
                  </span>
                )}
              </div>
            </div>

            {/* Simulation Preview Buttons */}
            <div className="mt-6 pt-4 border-t border-white/5 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono uppercase tracking-wider text-[var(--text-secondary)]">
                  Preview Visual State
                </span>
                {isDemoRunning && (
                  <span className="text-[11px] font-mono text-emerald-400 animate-pulse">
                    Lifecycle walkthrough running...
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => handleSimulate("normal")}
                  className={`px-3 py-2 rounded-lg text-xs font-mono border transition-all text-left flex items-center gap-2 ${
                    previewState === "normal"
                      ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300"
                      : "border-white/10 bg-white/5 text-[var(--text-secondary)] hover:text-white hover:bg-white/10"
                  }`}
                >
                  <Play className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Normal Mode</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleSimulate("power-save-waiting")}
                  className={`px-3 py-2 rounded-lg text-xs font-mono border transition-all text-left flex items-center gap-2 ${
                    previewState === "power-save-waiting"
                      ? "border-amber-500/50 bg-amber-500/10 text-amber-300"
                      : "border-white/10 bg-white/5 text-[var(--text-secondary)] hover:text-white hover:bg-white/10"
                  }`}
                >
                  <Clock className="w-3.5 h-3.5 text-amber-400" />
                  <span>Waiting for Inactivity</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleSimulate("power-save-countdown")}
                  className={`px-3 py-2 rounded-lg text-xs font-mono border transition-all text-left flex items-center gap-2 ${
                    previewState === "power-save-countdown"
                      ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300"
                      : "border-white/10 bg-white/5 text-[var(--text-secondary)] hover:text-white hover:bg-white/10"
                  }`}
                >
                  <Leaf className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Power Saver Mode</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleSimulate("power-save-complete")}
                  className={`px-3 py-2 rounded-lg text-xs font-mono border transition-all text-left flex items-center gap-2 ${
                    previewState === "power-save-complete"
                      ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-300"
                      : "border-white/10 bg-white/5 text-[var(--text-secondary)] hover:text-white hover:bg-white/10"
                  }`}
                >
                  <Timer className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Countdown Complete</span>
                </button>

                <button
                  type="button"
                  onClick={() => handleSimulate("power-save-wake")}
                  className={`px-3 py-2 rounded-lg text-xs font-mono border transition-all text-left flex items-center gap-2 ${
                    previewState === "power-save-wake"
                      ? "border-sky-500/50 bg-sky-500/10 text-sky-300"
                      : "border-white/10 bg-white/5 text-[var(--text-secondary)] hover:text-white hover:bg-white/10"
                  }`}
                >
                  <Hand className="w-3.5 h-3.5 text-sky-400" />
                  <span>Hand Detected / Wake</span>
                </button>

                <button
                  type="button"
                  onClick={runFullLifecycleDemo}
                  disabled={isDemoRunning}
                  className="px-3 py-2 rounded-lg text-xs font-mono border border-[var(--accent-primary)]/40 bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                  title="Run automated walkthrough of all power transitions"
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>Full Lifecycle Demo</span>
                </button>
              </div>

              {/* Dedicated Safe Desktop Overlay Test Trigger */}
              <div className="pt-3 border-t border-white/5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold text-[var(--text-primary)] flex items-center gap-1.5">
                    <PlayCircle className="w-4 h-4 text-emerald-400" />
                    <span>Real Desktop Overlay Test</span>
                  </div>
                  <p className="text-[11px] text-[var(--text-secondary)] mt-0.5">
                    Triggers a safe 5-second countdown on the physical desktop overlay without changing power state.
                  </p>
                </div>
                <button
                  type="button"
                  data-testid="test-countdown-btn"
                  onClick={handleTestDesktopCountdown}
                  disabled={isTestingDesktop || !islandSettings.enabled}
                  className="px-3.5 py-2 rounded-xl text-xs font-mono font-semibold border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 transition-all flex items-center justify-center gap-2 disabled:opacity-40 shrink-0"
                >
                  <Timer className="w-3.5 h-3.5" />
                  <span>{isTestingDesktop ? "Triggering 5s Test..." : "Test 5s Countdown"}</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Section C (1 col): Live Status */}
        <div className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-[#0c0e14]/90 backdrop-blur-md p-6 space-y-4 shadow-xl">
            <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[var(--text-secondary)]">
              <Monitor className="w-4 h-4 text-[var(--accent-primary)]" />
              <span>Real Desktop Overlay Status</span>
            </div>

            <div className="p-4 rounded-xl bg-black/40 border border-white/5 space-y-3 text-xs font-mono">
              <div className="flex items-center justify-between">
                <span className="text-[var(--text-secondary)]">HUD Overlay:</span>
                <span
                  className={
                    islandSettings.enabled
                      ? "text-emerald-400 font-semibold"
                      : "text-rose-400 font-semibold"
                  }
                >
                  {islandSettings.enabled ? "ACTIVE (Win32)" : "DISABLED"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-[var(--text-secondary)]">Bridge:</span>
                <span
                  className={
                    engine.connected
                      ? "text-emerald-400 font-semibold"
                      : "text-amber-400 font-semibold"
                  }
                >
                  {engine.connected ? "ONLINE (8765)" : "OFFLINE"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-[var(--text-secondary)]">Engine State:</span>
                <span
                  className={
                    engine.powerState === "POWER_SAVE"
                      ? "text-emerald-400 font-semibold"
                      : "text-[var(--text-primary)] font-semibold"
                  }
                >
                  {engine.powerState === "POWER_SAVE" ? "POWER SAVE" : "NORMAL"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-[var(--text-secondary)]">Power Saver:</span>
                <span
                  className={
                    engine.powerSave
                      ? "text-emerald-400 font-semibold"
                      : "text-[var(--text-secondary)] font-semibold"
                  }
                >
                  {engine.powerSave ? "ENABLED" : "OFF"}
                </span>
              </div>
            </div>

            <div className="text-[11.5px] text-[var(--text-secondary)] leading-relaxed flex items-start gap-2 p-3 rounded-lg bg-white/5 border border-white/5">
              <Info className="w-4 h-4 text-[var(--accent-primary)] shrink-0 mt-0.5" />
              <span>
                Settings synchronize live to the native Win32/Tkinter overlay capsule at the top of your desktop screen.
              </span>
            </div>

            {lastMutationSuccess && (
              <div className="text-[11.5px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 p-2.5 rounded-lg font-mono">
                {lastMutationSuccess}
              </div>
            )}
            {lastMutationError && (
              <div className="text-[11.5px] text-rose-400 bg-rose-500/10 border border-rose-500/20 p-2.5 rounded-lg font-mono">
                {lastMutationError}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Section B: Settings */}
      <div className="rounded-2xl border border-white/10 bg-[#0c0e14]/90 backdrop-blur-md p-6 space-y-6 shadow-xl">
        <div className="flex items-center justify-between pb-4 border-b border-white/5">
          <div>
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              Dynamic Island Settings
            </h2>
            <p className="text-xs text-[var(--text-secondary)] mt-0.5">
              Control HUD visibility, notifications, countdown display, and dismissal timers.
            </p>
          </div>
          <button
            type="button"
            onClick={() =>
              setIslandSettings({
                enabled: true,
                notificationsEnabled: true,
                timerEnabled: true,
                autohideEnabled: true,
                hudDurationS: 120,
                completionDurationS: 2.0,
              })
            }
            className="px-3 py-1.5 rounded-lg text-xs font-mono border border-white/10 hover:border-white/20 hover:bg-white/5 text-[var(--text-secondary)] hover:text-white transition-all flex items-center gap-1.5"
            title="Reset Dynamic Island settings to defaults"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset Defaults</span>
          </button>
        </div>

        {/* Compact Toggles Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Toggle 1: Show HUD */}
          <div className="p-4 rounded-xl bg-black/40 border border-white/5 flex items-center justify-between gap-3">
            <div className="space-y-0.5 min-w-0">
              <label
                htmlFor="toggle-island-enabled"
                className="text-sm font-medium text-[var(--text-primary)] cursor-pointer block truncate"
              >
                Show HUD
              </label>
              <p className="text-[11px] text-[var(--text-secondary)] truncate">
                Desktop capsule overlay
              </p>
            </div>
            <Switch
              id="toggle-island-enabled"
              data-testid="toggle-island-enabled"
              checked={islandSettings.enabled}
              onCheckedChange={(checked) => setIslandSettings({ enabled: checked })}
            />
          </div>

          {/* Toggle 2: Notifications */}
          <div className="p-4 rounded-xl bg-black/40 border border-white/5 flex items-center justify-between gap-3">
            <div className="space-y-0.5 min-w-0">
              <label
                htmlFor="toggle-island-notifications"
                className="text-sm font-medium text-[var(--text-primary)] cursor-pointer block truncate"
              >
                Notifications
              </label>
              <p className="text-[11px] text-[var(--text-secondary)] truncate">
                Mode transition toasts
              </p>
            </div>
            <Switch
              id="toggle-island-notifications"
              data-testid="toggle-island-notifications"
              checked={islandSettings.notificationsEnabled}
              onCheckedChange={(checked) =>
                setIslandSettings({ notificationsEnabled: checked })
              }
              disabled={!islandSettings.enabled}
            />
          </div>

          {/* Toggle 3: Countdown */}
          <div className="p-4 rounded-xl bg-black/40 border border-white/5 flex items-center justify-between gap-3">
            <div className="space-y-0.5 min-w-0">
              <label
                htmlFor="toggle-island-timer"
                className="text-sm font-medium text-[var(--text-primary)] cursor-pointer block truncate"
              >
                Countdown
              </label>
              <p className="text-[11px] text-[var(--text-secondary)] truncate">
                Live MM:SS badge
              </p>
            </div>
            <Switch
              id="toggle-island-timer"
              data-testid="toggle-island-timer"
              checked={islandSettings.timerEnabled}
              onCheckedChange={(checked) =>
                setIslandSettings({ timerEnabled: checked })
              }
              disabled={!islandSettings.enabled}
            />
          </div>

          {/* Toggle 4: Auto-hide */}
          <div className="p-4 rounded-xl bg-black/40 border border-white/5 flex items-center justify-between gap-3">
            <div className="space-y-0.5 min-w-0">
              <label
                htmlFor="toggle-island-autohide"
                className="text-sm font-medium text-[var(--text-primary)] cursor-pointer block truncate"
              >
                Auto-hide
              </label>
              <p className="text-[11px] text-[var(--text-secondary)] truncate">
                Retract after timeout
              </p>
            </div>
            <Switch
              id="toggle-island-autohide"
              data-testid="toggle-island-autohide"
              checked={islandSettings.autohideEnabled}
              onCheckedChange={(checked) =>
                setIslandSettings({ autohideEnabled: checked })
              }
              disabled={!islandSettings.enabled}
            />
          </div>
        </div>

        {/* HUD Duration Control Section */}
        <div className="p-5 rounded-xl bg-black/40 border border-white/5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div>
              <div className="text-sm font-medium text-[var(--text-primary)] flex items-center gap-2">
                <Timer className="w-4 h-4 text-[var(--accent-primary)]" />
                <span>HUD duration</span>
              </div>
              <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                Visibility duration before smooth collapse during Power Saver mode.
              </p>
            </div>

            <div className="flex items-center gap-2 font-mono">
              <span
                data-testid="hud-duration-label"
                className="px-3 py-1 rounded-lg bg-white/5 border border-white/10 text-sm font-bold text-[var(--accent-primary)] tabular-nums"
              >
                {formatDurationLabel(islandSettings.hudDurationS)} ({islandSettings.hudDurationS}s)
              </span>
            </div>
          </div>

          {/* Duration Slider */}
          <div className="pt-2">
            <Slider
              data-testid="hud-duration-slider"
              value={[islandSettings.hudDurationS]}
              min={ISLAND_HUD_DURATION_LIMITS.min}
              max={ISLAND_HUD_DURATION_LIMITS.max}
              step={ISLAND_HUD_DURATION_LIMITS.step}
              onValueChange={([val]) => setIslandSettings({ hudDurationS: val })}
              disabled={!islandSettings.enabled}
              className="py-2"
            />
            <div className="flex justify-between text-[11px] font-mono text-[var(--text-secondary)] mt-1">
              <span>10s</span>
              <span>1 min</span>
              <span>2 min (Default)</span>
              <span>5 min</span>
              <span>15 min</span>
              <span>30 min</span>
            </div>
          </div>

          {/* Quick Preset Buttons */}
          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-white/5">
            <span className="text-xs font-mono text-[var(--text-secondary)] mr-1">
              Presets:
            </span>
            {[
              { label: "30s", val: 30 },
              { label: "1 min", val: 60 },
              { label: "2 min (Default)", val: 120 },
              { label: "5 min", val: 300 },
              { label: "10 min", val: 600 },
            ].map((preset) => (
              <button
                key={preset.val}
                type="button"
                onClick={() => setIslandSettings({ hudDurationS: preset.val })}
                disabled={!islandSettings.enabled}
                className={`px-2.5 py-1 rounded text-xs font-mono border transition-all ${
                  islandSettings.hudDurationS === preset.val
                    ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/15 text-[var(--accent-primary)] font-semibold"
                    : "border-white/10 bg-white/5 text-[var(--text-secondary)] hover:text-white hover:bg-white/10"
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        {/* Completion Message Duration Section */}
        <div className="p-4 rounded-xl bg-black/40 border border-white/5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-0.5">
            <div className="text-sm font-medium text-[var(--text-primary)]">
              Completion message duration
            </div>
            <p className="text-xs text-[var(--text-secondary)]">
              How long "POWER SAVER · HIDING" remains visible before retracting (~2s default).
            </p>
          </div>

          <div className="flex items-center gap-2">
            {[1.0, 1.5, 2.0, 3.0, 5.0].map((dur) => (
              <button
                key={dur}
                type="button"
                onClick={() => setIslandSettings({ completionDurationS: dur })}
                disabled={!islandSettings.enabled}
                className={`px-2.5 py-1 rounded text-xs font-mono border transition-all ${
                  islandSettings.completionDurationS === dur
                    ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/15 text-[var(--accent-primary)] font-semibold"
                    : "border-white/10 bg-white/5 text-[var(--text-secondary)] hover:text-white hover:bg-white/10"
                }`}
              >
                {dur.toFixed(1)}s
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
