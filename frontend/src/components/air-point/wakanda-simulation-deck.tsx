import React, { useEffect, useRef, useState } from "react";
import { RotateCcw, ShieldCheck, Sparkles } from "lucide-react";
import { WakandaCapsule, type CapsulePhase } from "./wakanda-capsule";

const HOLD_DURATION_MS = 2000;

export interface WakandaSimulationDeckProps {
  isArmed: boolean;
  onToggleArm: () => void;
  reducedMotion?: boolean;
}

export const WakandaSimulationDeck: React.FC<WakandaSimulationDeckProps> = ({
  isArmed,
  onToggleArm,
  reducedMotion = false,
}) => {
  const [phase, setPhase] = useState<CapsulePhase>(isArmed ? "armed" : "disarmed");
  const [phaseLabel, setPhaseLabel] = useState<string>(isArmed ? "ARMED" : "DISARMED");
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState(
    isArmed
      ? "Feature armed. Ready for crossed-arm gesture or simulated preview."
      : "Enable the feature to preview its activation."
  );

  const intervalRef = useRef<number | null>(null);
  const completeRef = useRef<number | null>(null);
  const startRef = useRef(0);

  const clearTimers = () => {
    if (intervalRef.current !== null) window.clearInterval(intervalRef.current);
    if (completeRef.current !== null) window.clearTimeout(completeRef.current);
    intervalRef.current = null;
    completeRef.current = null;
  };

  // Sync state whenever external isArmed prop changes
  useEffect(() => {
    clearTimers();
    setProgress(0);
    if (isArmed) {
      setPhase("armed");
      setPhaseLabel("ARMED");
      setMessage("Feature armed. Ready for crossed-arm gesture or simulated preview.");
    } else {
      setPhase("disarmed");
      setPhaseLabel("DISARMED");
      setMessage("Feature disabled. Enable to activate crossed-arm workstation lock.");
    }
  }, [isArmed]);

  useEffect(() => () => clearTimers(), []);

  const handleSimulate = () => {
    if (!isArmed || phase === "holding") return;
    clearTimers();
    setPhase("holding");
    setPhaseLabel("HOLDING");
    setProgress(0);
    setMessage("Simulated hold in progress — 0.0 / 2.0 seconds.");

    startRef.current = performance.now();
    intervalRef.current = window.setInterval(() => {
      const elapsed = performance.now() - startRef.current;
      const next = Math.min(100, (elapsed / HOLD_DURATION_MS) * 100);
      setProgress(next);
      setMessage(
        `Simulated hold in progress — ${(
          Math.min(elapsed, HOLD_DURATION_MS) / 1000
        ).toFixed(1)} / 2.0 seconds.`
      );

      if (elapsed >= HOLD_DURATION_MS) {
        if (intervalRef.current !== null) window.clearInterval(intervalRef.current);
        intervalRef.current = null;
        setProgress(100);
        setPhase("complete");
        setPhaseLabel("LOCK PREVIEW");
        setMessage("Preview complete. No Windows lock was performed.");

        completeRef.current = window.setTimeout(() => {
          setPhase("armed");
          setPhaseLabel("ARMED");
          setProgress(0);
          setMessage("Feature armed. Ready for another preview.");
          completeRef.current = null;
        }, 1100);
      }
    }, 24);
  };

  const handleCancel = () => {
    clearTimers();
    setProgress(0);
    setPhase(isArmed ? "armed" : "disarmed");
    setPhaseLabel(isArmed ? "CANCELLED" : "DISARMED");
    setMessage(isArmed ? "Sequence cancelled. Capsule reset." : "Feature is disarmed.");
  };

  const handleReset = () => {
    clearTimers();
    setProgress(0);
    if (isArmed) {
      onToggleArm();
    }
    setPhase("disarmed");
    setPhaseLabel("DISARMED");
    setMessage("Preview reset. Feature is disarmed.");
  };

  return (
    <div
      className="space-y-4 rounded-xl border border-[var(--border-default)] bg-[var(--bg-elevated)] p-5"
      aria-label="Wakanda Forever interactive animation preview deck"
    >
      {/* Topline Header */}
      <div className="flex items-center justify-between pb-3 border-b border-[var(--border-subtle)]">
        <div>
          <span className="ap-label-tech flex items-center gap-1.5 text-purple-400">
            <Sparkles className="w-3.5 h-3.5" />
            V3 CAPSULE · INTERACTIVE LAB
          </span>
          <h4 className="text-base font-semibold mt-0.5">
            Wakanda Forever Activation Sequence
          </h4>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium border ${
            isArmed
              ? "bg-purple-950/40 text-purple-300 border-purple-500/40 shadow-[0_0_12px_rgba(168,85,247,0.2)]"
              : "bg-[var(--bg-surface)] text-[var(--text-muted)] border-[var(--border-subtle)]"
          }`}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              isArmed ? "bg-purple-400 shadow-[0_0_6px_#c084fc]" : "bg-zinc-600"
            }`}
          />
          {phaseLabel}
        </span>
      </div>

      {/* Pure Capsule Component */}
      <div className="py-2">
        <WakandaCapsule
          phase={phase}
          progress={progress}
          reducedMotion={reducedMotion}
        />
      </div>

      {/* Status Row */}
      <div
        className="flex items-center justify-between gap-3 text-xs font-mono text-[var(--text-secondary)] px-1"
        aria-live="polite"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`w-2 h-2 rounded-full shrink-0 ${
              isArmed ? "bg-purple-400 shadow-[0_0_8px_#c084fc]" : "bg-zinc-600"
            }`}
          />
          <span className="truncate">{message}</span>
        </div>
        <span className="shrink-0 text-purple-300 tabular-nums">
          {Math.round(progress)}%
        </span>
      </div>

      {/* Action Buttons Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
        <button
          type="button"
          onClick={onToggleArm}
          aria-pressed={isArmed}
          className={`min-h-[42px] px-4 rounded-lg font-mono text-xs font-semibold tracking-wider flex items-center justify-center gap-2 cursor-pointer transition-all border ${
            isArmed
              ? "bg-purple-950/50 text-purple-200 border-purple-500/50 hover:bg-purple-900/50 shadow-[0_4px_16px_rgba(147,51,234,0.15)]"
              : "bg-purple-600 hover:bg-purple-500 text-white border-transparent shadow-[0_4px_16px_rgba(147,51,234,0.3)]"
          }`}
        >
          <span>{isArmed ? "✓ DISARM FEATURE" : "＋ ARM FEATURE"}</span>
          <span className="text-[10px] opacity-75">{isArmed ? "· ON" : "· OFF"}</span>
        </button>

        <button
          type="button"
          onClick={handleSimulate}
          disabled={!isArmed || phase === "holding"}
          className="min-h-[42px] px-4 rounded-lg font-mono text-xs font-semibold tracking-wider flex items-center justify-center gap-2 cursor-pointer transition-all border border-[var(--border-default)] bg-[var(--bg-surface)] text-[var(--text-primary)] hover:border-purple-400/60 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <span>SIMULATE CROSSED-ARM GESTURE</span>
          <span className="text-purple-400">↗</span>
        </button>

        <button
          type="button"
          onClick={handleCancel}
          className="min-h-[38px] px-3 rounded-lg font-mono text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] transition-all cursor-pointer flex items-center justify-center gap-1.5"
        >
          <span>CANCEL SEQUENCE</span>
          <kbd className="px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[10px]">
            ESC
          </kbd>
        </button>

        <button
          type="button"
          onClick={handleReset}
          className="min-h-[38px] px-3 rounded-lg font-mono text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--border-default)] transition-all cursor-pointer flex items-center justify-center gap-1.5"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>RESET PREVIEW</span>
        </button>
      </div>

      {/* Safety Card Disclosure */}
      <div className="flex items-start gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3 text-xs text-[var(--text-secondary)]">
        <ShieldCheck className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
        <div className="space-y-0.5">
          <strong className="text-[var(--text-primary)] font-medium">
            Preview only — safe by design
          </strong>
          <p className="leading-relaxed">
            This standalone demo does not access your camera, recognize gestures, call the
            Python engine, or lock Windows. Real locking requires arming the feature and holding
            the crossed-arm pose in front of your camera.
          </p>
        </div>
      </div>
    </div>
  );
};
