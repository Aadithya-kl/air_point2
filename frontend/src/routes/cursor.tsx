import React, { useEffect, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Crosshair, RotateCcw, Sliders } from "lucide-react";
import { useAirPointEngine } from "@/components/air-point/engine";
import { MutationFeedbackBanner } from "@/components/air-point/common";
import {
  CURSOR_PRESETS,
  SENSITIVITY_LIMITS,
  SMOOTHING_LIMITS,
} from "@/lib/air-point-model";

export const CursorControlsPage: React.FC = () => {
  const engine = useAirPointEngine();
  const [confirmingReset, setConfirmingReset] = useState<boolean>(false);

  // Cursor playground browser simulation
  const padRef = useRef<HTMLDivElement | null>(null);
  const [rawPos, setRawPos] = useState<{ x: number; y: number }>({
    x: 240,
    y: 120,
  });
  const [smoothedPos, setSmoothedPos] = useState<{ x: number; y: number }>({
    x: 240,
    y: 120,
  });

  useEffect(() => {
    let rafId: number;
    const alpha = Math.max(0.06, 1 - engine.smoothing / 108);
    const animate = () => {
      setSmoothedPos((prev) => ({
        x: prev.x + (rawPos.x - prev.x) * alpha,
        y: prev.y + (rawPos.y - prev.y) * alpha,
      }));
      rafId = requestAnimationFrame(animate);
    };
    rafId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafId);
  }, [rawPos, engine.smoothing]);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = padRef.current?.getBoundingClientRect();
    if (!rect) return;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const offsetX = (e.clientX - rect.left - centerX) * engine.sensitivity;
    const offsetY = (e.clientY - rect.top - centerY) * engine.sensitivity;
    setRawPos({
      x: Math.min(rect.width - 16, Math.max(16, centerX + offsetX)),
      y: Math.min(rect.height - 16, Math.max(16, centerY + offsetY)),
    });
  };

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <div className="page-head">
        <div>
          <h1 className="page-title">Cursor & Controls</h1>
          <p className="page-sub">Tune pointer response and smoothing.</p>
        </div>

        <div className="flex items-center gap-2">
          {!confirmingReset ? (
            <button
              type="button"
              onClick={() => setConfirmingReset(true)}
              className="btn"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reset defaults</span>
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={async () => {
                  await engine.resetCursorDefaults();
                  setConfirmingReset(false);
                }}
                className="btn primary"
              >
                Confirm reset (0.85× / 65%)
              </button>
              <button
                type="button"
                onClick={() => setConfirmingReset(false)}
                className="btn"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      <MutationFeedbackBanner
        pending={engine.pendingMutation}
        error={engine.lastMutationError}
        success={engine.lastMutationSuccess}
        onDismiss={engine.clearMutationFeedback}
      />

      {/* 2 Setting Cards: Sensitivity & Smoothing */}
      <div className="control-grid">
        <section className="glass setting-card p-5 rounded-[22px]">
          <div className="flex items-center justify-between font-bold text-xs mb-1">
            <span>Cursor sensitivity</span>
            <span className="value-pill" id="sens-value">
              {engine.sensitivity.toFixed(2)}×
            </span>
          </div>
          <p className="text-[11px] text-[var(--muted)] m-0 mb-4 leading-relaxed">
            How far the Windows pointer moves relative to your hand displacement.
          </p>

          <input
            id="cursor-sensitivity-slider"
            type="range"
            min={SENSITIVITY_LIMITS.uiMin}
            max={SENSITIVITY_LIMITS.uiMax}
            step={SENSITIVITY_LIMITS.step}
            value={engine.sensitivity}
            onChange={(e) => engine.setSensitivity(parseFloat(e.target.value))}
            className="w-full accent-[var(--accent)] cursor-pointer"
          />

          <div className="range-labels mt-2">
            <span>0.5× · Precise</span>
            <span>2.5× · Fast</span>
          </div>
        </section>

        <section className="glass setting-card p-5 rounded-[22px]">
          <div className="flex items-center justify-between font-bold text-xs mb-1">
            <span>Cursor smoothing</span>
            <span className="value-pill" id="smooth-value">
              {Math.round(engine.smoothing)}%
            </span>
          </div>
          <p className="text-[11px] text-[var(--muted)] m-0 mb-4 leading-relaxed">
            Reduces jitter from small hand movements via the One Euro Filter.
          </p>

          <input
            id="cursor-smoothing-slider"
            type="range"
            min={SMOOTHING_LIMITS.uiMin}
            max={SMOOTHING_LIMITS.uiMax}
            step={SMOOTHING_LIMITS.step}
            value={engine.smoothing}
            onChange={(e) => engine.setSmoothing(parseFloat(e.target.value))}
            className="w-full accent-[var(--accent)] cursor-pointer"
          />

          <div className="range-labels mt-2">
            <span>10% · Responsive</span>
            <span>100% · Smooth</span>
          </div>
        </section>
      </div>

      {/* Calibration Presets Card */}
      <section className="glass setting-card p-5 rounded-[22px]">
        <div className="flex items-center justify-between gap-3 mb-4 pb-2.5 border-b border-[var(--line)]">
          <div>
            <h2 className="text-sm font-bold m-0 tracking-tight">Calibration presets</h2>
            <p className="text-[10px] text-[var(--muted)] m-0 mt-0.5">
              Verified response profiles for precision targeting or fast sweeps.
            </p>
          </div>
          <span className="badge">
            <Sliders className="w-3 h-3 text-[var(--accent)]" />
            <span>ACTIVE: {engine.activePreset.toUpperCase()}</span>
          </span>
        </div>

        <div className="gesture-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
          {CURSOR_PRESETS.map((preset) => {
            const isSelected = engine.activePreset === preset.id;
            return (
              <button
                key={preset.id}
                type="button"
                data-testid={`preset-${preset.id}`}
                aria-pressed={isSelected}
                onClick={() => engine.applyCursorPreset(preset.id)}
                className={`gesture-tile text-left cursor-pointer transition-all ${
                  isSelected ? "border-[var(--accent)] bg-[var(--surface-strong)]" : ""
                }`}
              >
                <div className="tile-top">
                  <span className="tile-icon font-mono font-bold text-xs">
                    {preset.id === "precision" ? "◎" : preset.id === "balanced" ? "◉" : "↗"}
                  </span>
                  {isSelected && (
                    <span className="badge text-[10px] uppercase font-bold text-[var(--accent)]">
                      SELECTED
                    </span>
                  )}
                </div>

                <div className="tile-name">{preset.label}</div>
                <div className="tile-desc">{preset.summary}</div>

                <div className="tile-footer">
                  <i></i>
                  <span>
                    {preset.sensitivity.toFixed(2)}× · {preset.smoothing}%
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Illustrative Cursor Playground Sandbox */}
      <section className="playground">
        <div className="flex items-center justify-between gap-3 mb-3">
          <div>
            <h2 className="text-sm font-bold m-0 tracking-tight">Cursor playground</h2>
            <p className="text-[10px] text-[var(--muted)] m-0 mt-0.5">
              Interactive sandbox · Move your mouse inside to test filter response.
            </p>
          </div>
          <span
            data-testid="cursor-playground-disclaimer"
            className="badge demo"
          >
            SIMULATION ONLY
          </span>
        </div>

        <div
          ref={padRef}
          onMouseMove={handleMouseMove}
          className="relative h-64 w-full rounded-xl bg-[var(--bg-viewport)] border border-[var(--line)] overflow-hidden cursor-crosshair select-none"
        >
          {/* Centered Reticle */}
          <div className="crosshair" />

          {/* Raw Position Indicator (Unsmoothed) */}
          <div
            style={{
              transform: `translate(${rawPos.x - 6}px, ${rawPos.y - 6}px)`,
            }}
            className="w-3 h-3 rounded-full border border-slate-400 absolute top-0 left-0 pointer-events-none transition-none"
          />

          {/* Smoothed Cursor Output */}
          <div
            style={{
              transform: `translate(${smoothedPos.x - 8}px, ${smoothedPos.y - 8}px)`,
            }}
            className="w-4 h-4 rounded-full bg-[var(--accent)] shadow-md absolute top-0 left-0 pointer-events-none flex items-center justify-center transition-none"
          >
            <div className="w-1.5 h-1.5 rounded-full bg-white" />
          </div>

          <div
            style={{ position: "absolute", bottom: "12px", left: "14px" }}
            className="ap-label-tech text-[10px] opacity-80"
          >
            RAW POSITION ○ &nbsp; SMOOTHED CURSOR ●
          </div>
        </div>
      </section>
    </div>
  );
};

export const Route = createFileRoute("/cursor")({
  component: CursorControlsPage,
});
