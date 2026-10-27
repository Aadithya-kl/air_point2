import React, { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Check,
  Copy,
  ExternalLink,
  ShieldCheck,
  Terminal,
  ArrowRight,
  ChevronDown,
  Sparkles,
  Info,
  Monitor,
} from "lucide-react";
import { useAirPointEngine } from "@/components/air-point/engine";

export const AboutPage: React.FC = () => {
  const engine = useAirPointEngine();
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  const diagnostics = engine.getDiagnosticsReport();
  const diagnosticsJson = JSON.stringify(diagnostics, null, 2);

  const handleCopyDiagnostics = async () => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(diagnosticsJson);
        setCopyState("copied");
      } else {
        throw new Error("Clipboard API unavailable");
      }
    } catch {
      setCopyState("failed");
    }
    setTimeout(() => setCopyState("idle"), 3000);
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="page-head">
        <div>
          <div className="flex items-center gap-2.5 mb-1">
            <h1 className="page-title m-0">About Air Point</h1>
            <span className="badge" data-testid="version-badge">
              v1.0.0
            </span>
          </div>
          <p className="page-sub">Touchless webcam gesture control for Windows.</p>
        </div>
      </div>

      {/* User-facing Overview Card */}
      <section className="glass p-6 rounded-[22px] space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 pb-4 border-b border-[var(--line)]">
          <div className="space-y-1.5 max-w-xl">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[var(--accent)]" />
              <h2 className="text-base font-bold m-0 tracking-tight text-[var(--text)]">
                Air Point Control Center
              </h2>
            </div>
            <p className="text-xs text-[var(--muted)] leading-relaxed m-0">
              Air Point transforms any standard webcam into a touchless, high-precision Windows
              input device. Navigate smoothly, interact with desktop apps, and trigger everyday
              system shortcuts using natural hand gestures.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <span
              className={`badge ${engine.connected ? "active" : ""}`}
              data-testid="about-connection-badge"
            >
              <i className="dot" />
              <span>{engine.connected ? "ONLINE" : "OFFLINE PREVIEW"}</span>
            </span>
          </div>
        </div>

        {/* Truthful Connection & Runtime Status */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="p-3.5 rounded-xl border border-[var(--line)] bg-[var(--surface)] space-y-1">
            <span className="text-[10px] font-mono uppercase text-[var(--muted)]">
              Bridge Status
            </span>
            <div className="text-xs font-mono font-semibold text-[var(--text)] flex items-center gap-1.5">
              <span
                className={`w-2 h-2 rounded-full ${
                  engine.connected ? "bg-emerald-400" : "bg-zinc-500"
                }`}
              />
              <span>
                {engine.connected ? "Connected · 127.0.0.1:8765" : "Offline · Local preview mode"}
              </span>
            </div>
          </div>

          <div className="p-3.5 rounded-xl border border-[var(--line)] bg-[var(--surface)] space-y-1">
            <span className="text-[10px] font-mono uppercase text-[var(--muted)]">
              Vision Engine
            </span>
            <div className="text-xs font-mono font-semibold text-[var(--text)]">
              {engine.connected
                ? engine.running
                  ? `Active · ${engine.fps} FPS`
                  : "Paused"
                : "Ready to connect"}
            </div>
          </div>

          <div className="p-3.5 rounded-xl border border-[var(--line)] bg-[var(--surface)] space-y-1">
            <span className="text-[10px] font-mono uppercase text-[var(--muted)]">
              Active Gestures
            </span>
            <div className="text-xs font-mono font-semibold text-[var(--text)]">
              8 System Gestures Configured
            </div>
          </div>
        </div>

        {/* Helpful Guidance & Next Steps */}
        <div className="p-4 rounded-xl border border-[var(--line-divider)] bg-[var(--surface-soft)] space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-[var(--text)]">
            <Info className="w-3.5 h-3.5 text-[var(--accent)] shrink-0" />
            <span>Quick Setup & Best Practices</span>
          </div>
          <p className="text-[11px] text-[var(--muted)] leading-relaxed m-0">
            For optimal tracking, position your webcam at chest level, maintain good ambient
            lighting, and keep your hand 0.5 to 1.5 meters from the lens. Visit the Gesture Library
            to inspect visual tutorial videos and customize your controls.
          </p>
        </div>

        {/* Useful Links & Navigation */}
        <div className="pt-4 border-t border-[var(--line)] flex flex-wrap items-center justify-between gap-3 text-xs">
          <Link
            to="/gestures"
            className="btn primary inline-flex items-center gap-2 py-2 px-3.5 text-xs font-medium"
          >
            <span>Explore Gesture Library</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>

          <div className="flex items-center gap-4 text-[11px] text-[var(--muted)]">
            <span className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-[var(--accent)]" />
              <span>MIT License</span>
            </span>
            <a
              href="https://github.com/Aadithya-kl/air_point"
              target="_blank"
              rel="noreferrer"
              className="font-mono text-[var(--accent)] hover:underline inline-flex items-center gap-1"
            >
              <span>GitHub Repository</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </section>

      {/* Real Desktop Overlay Status Card (Relocated truthfully from /island) */}
      <section
        data-testid="desktop-overlay-status-card"
        className="glass p-6 rounded-[22px] space-y-4"
      >
        <div className="flex items-center justify-between text-xs font-mono uppercase tracking-wider text-[var(--muted)]">
          <div className="flex items-center gap-2">
            <Monitor className="w-4 h-4 text-[var(--accent)]" />
            <span className="font-bold text-[var(--text)]">Real Desktop Overlay Status</span>
          </div>
          <span
            className={`px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider uppercase ${
              engine.connected && engine.islandSettingsSynced
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
            }`}
          >
            {engine.connected && engine.islandSettingsSynced
              ? "HOST CONNECTED"
              : !engine.connected && !engine.islandSettingsSynced
                ? "HOST OFFLINE · SETTINGS UNSYNCED"
                : engine.connected
                  ? "HOST CONNECTED · UNSYNCED"
                  : "HOST OFFLINE"}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
          <div className="p-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] space-y-1">
            <span className="text-[10px] text-[var(--muted)] uppercase">HUD Overlay</span>
            <div
              className={`font-semibold ${
                !engine.connected || !engine.islandSettingsSynced
                  ? "text-amber-400"
                  : engine.islandSettings.enabled
                    ? "text-emerald-400"
                    : "text-rose-400"
              }`}
            >
              {!engine.islandSettingsSynced
                ? "UNSYNCED"
                : !engine.connected
                  ? engine.islandSettings.enabled
                    ? "LAST KNOWN: ENABLED"
                    : "LAST KNOWN: DISABLED"
                  : engine.islandSettings.enabled
                    ? "ENABLED (HOST SETTING)"
                    : "DISABLED (HOST SETTING)"}
            </div>
          </div>

          <div className="p-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] space-y-1">
            <span className="text-[10px] text-[var(--muted)] uppercase">Bridge</span>
            <div
              className={`font-semibold ${
                engine.connected ? "text-emerald-400" : "text-amber-400"
              }`}
            >
              {engine.connected ? "ONLINE (8765)" : "OFFLINE"}
            </div>
          </div>

          <div className="p-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] space-y-1">
            <span className="text-[10px] text-[var(--muted)] uppercase">Engine State</span>
            <div
              className={`font-semibold ${
                engine.powerState === "POWER_SAVE" ? "text-emerald-400" : "text-[var(--text)]"
              }`}
            >
              {!engine.connected
                ? "UNKNOWN (OFFLINE)"
                : engine.powerState === "POWER_SAVE"
                  ? "POWER SAVE"
                  : "NORMAL"}
            </div>
          </div>

          <div className="p-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] space-y-1">
            <span className="text-[10px] text-[var(--muted)] uppercase">Power Saver</span>
            <div
              className={`font-semibold ${
                engine.powerSave ? "text-emerald-400" : "text-[var(--muted)]"
              }`}
            >
              {!engine.connected ? "UNKNOWN (OFFLINE)" : engine.powerSave ? "ENABLED" : "OFF"}
            </div>
          </div>
        </div>

        <div className="text-[11.5px] text-[var(--muted)] leading-relaxed flex items-start gap-2 p-3 rounded-xl bg-[var(--surface-soft)] border border-[var(--line-divider)]">
          <Info className="w-4 h-4 text-[var(--accent)] shrink-0 mt-0.5" />
          <span>
            Desktop controls write only the six settings supported by the existing AirPoint bridge.
            Engine power state is shown separately from the HUD's presentation phase; Concept
            appearance changes stay local to Studio.
          </span>
        </div>

        {engine.lastMutationSuccess && (
          <div className="text-[11.5px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 p-2.5 rounded-lg font-mono">
            {engine.lastMutationSuccess}
          </div>
        )}
        {engine.lastMutationError && (
          <div className="text-[11.5px] text-rose-400 bg-rose-500/10 border border-rose-500/20 p-2.5 rounded-lg font-mono">
            {engine.lastMutationError}
          </div>
        )}
      </section>

      {/* Collapsed-by-default Advanced Diagnostics Disclosure */}
      <details
        className="glass p-5 rounded-[22px] group"
        data-testid="advanced-diagnostics-details"
      >
        <summary className="flex items-center justify-between cursor-pointer list-none select-none">
          <div className="flex items-center gap-2.5">
            <Terminal className="w-4 h-4 text-[var(--accent)] shrink-0" />
            <span className="text-sm font-bold tracking-tight text-[var(--text)]">
              Advanced Diagnostics & Technical Architecture
            </span>
            <span className="badge">DEVELOPER</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
            <span className="hidden sm:inline font-mono text-[10px]">Inspect runtime manifest</span>
            <ChevronDown className="w-4 h-4 transition-transform duration-200 group-open:rotate-180" />
          </div>
        </summary>

        <div className="mt-4 pt-4 border-t border-[var(--line)] space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <p className="text-xs text-[var(--muted)] m-0">
              Raw bridge telemetry and system parameters. Zero fabricated counters.
            </p>
            <button
              type="button"
              data-testid="copy-diagnostics-button"
              onClick={handleCopyDiagnostics}
              className="btn text-xs py-1.5 px-3 self-start sm:self-auto shrink-0 inline-flex items-center gap-1.5"
            >
              {copyState === "copied" ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Diagnostics copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy diagnostics</span>
                </>
              )}
            </button>
          </div>

          {copyState === "failed" && (
            <div
              role="alert"
              className="p-3 rounded-xl border border-[var(--status-warning)] bg-[var(--status-warning-bg)] text-xs font-mono text-[var(--status-warning)]"
            >
              Clipboard write permission was blocked by the browser. You can select and copy the
              live JSON manifest directly below.
            </div>
          )}

          <pre
            data-testid="diagnostics-manifest-preview"
            className="p-3 rounded-xl bg-[var(--bg-viewport)] border border-[var(--line)] text-[12px] font-mono text-slate-300 overflow-x-auto max-h-60 leading-[1.55]"
          >
            {diagnosticsJson}
          </pre>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 text-[11px] font-mono text-[var(--muted)]">
            <div className="flex justify-between py-1 border-b border-[var(--line-divider)]">
              <span>Engine Pipeline</span>
              <span className="text-[var(--text)]">MediaPipe Tasks Hand Landmarker</span>
            </div>
            <div className="flex justify-between py-1 border-b border-[var(--line-divider)]">
              <span>Filter Algorithm</span>
              <span className="text-[var(--text)]">1€ One Euro Filter (Gain/Damping)</span>
            </div>
            <div className="flex justify-between py-1 border-b border-[var(--line-divider)]">
              <span>Input Injection</span>
              <span className="text-[var(--text)]">Win32 SendInput & LockWorkStation</span>
            </div>
            <div className="flex justify-between py-1 border-b border-[var(--line-divider)]">
              <span>Bridge Protocol</span>
              <span className="text-[var(--text)]">WebSocket (ws://127.0.0.1:8765)</span>
            </div>
          </div>
        </div>
      </details>
    </div>
  );
};

export const Route = createFileRoute("/about")({
  component: AboutPage,
});
