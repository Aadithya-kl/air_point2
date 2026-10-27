import React from "react";
import {
  Activity,
  Cpu,
  Clock,
  Leaf,
  ShieldAlert,
  Sparkles,
  Zap,
} from "lucide-react";
import type { CapsuleBodyProps, CapsuleState } from "./types";

/**
 * Visual metadata for each capsule operating posture.
 */
interface StateVisualConfig {
  defaultLabel: string;
  defaultSublabel: string;
  statusBadge: string;
  badgeStyle: string;
  edgeGlowStyle: string;
  coreLightingClass: string;
  iconNode: React.ReactNode;
}

const STATE_CONFIGS: Record<CapsuleState, StateVisualConfig> = {
  IDLE: {
    defaultLabel: "AirPoint Core",
    defaultSublabel: "Kinetic Standby · Low Energy",
    statusBadge: "IDLE",
    badgeStyle: "bg-white/5 text-white/60 border-white/10",
    edgeGlowStyle: "rgba(34, 211, 238, 0.2)",
    coreLightingClass: "shadow-[0_0_16px_-2px_rgba(34,211,238,0.3)]",
    iconNode: <Cpu className="w-4 h-4 text-cyan-400/90" />,
  },
  ARMED: {
    defaultLabel: "Armed & Ready",
    defaultSublabel: "Pointer Engaged · Sensors Primed",
    statusBadge: "ARMED",
    badgeStyle: "bg-violet-500/15 text-violet-300 border-violet-500/30",
    edgeGlowStyle: "rgba(168, 118, 255, 0.42)",
    coreLightingClass: "shadow-[0_0_22px_-2px_rgba(168,118,255,0.5)]",
    iconNode: <Sparkles className="w-4 h-4 text-violet-300 animate-pulse" />,
  },
  COUNTDOWN: {
    defaultLabel: "Countdown Sequence",
    defaultSublabel: "Hold Gesture · Action Imminent",
    statusBadge: "COUNTDOWN",
    badgeStyle: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
    edgeGlowStyle: "rgba(34, 211, 238, 0.6)",
    coreLightingClass: "shadow-[0_0_26px_0px_rgba(34,211,238,0.55)]",
    iconNode: <Clock className="w-4 h-4 text-cyan-300 animate-spin [animation-duration:4s]" />,
  },
  ACTIVE: {
    defaultLabel: "AirPoint Active",
    defaultSublabel: "Real-time Telemetry · 60 FPS",
    statusBadge: "ONLINE",
    badgeStyle: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    edgeGlowStyle: "rgba(52, 211, 153, 0.5)",
    coreLightingClass: "shadow-[0_0_28px_0px_rgba(52,211,153,0.5)]",
    iconNode: <Activity className="w-4 h-4 text-emerald-300" />,
  },
  POWER_SAVE: {
    defaultLabel: "Power Saver",
    defaultSublabel: "2 Hz Probe · Camera Throttled",
    statusBadge: "ECO SLEEP",
    badgeStyle: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    edgeGlowStyle: "rgba(251, 191, 36, 0.3)",
    coreLightingClass: "shadow-[0_0_16px_-2px_rgba(251,191,36,0.35)]",
    iconNode: <Leaf className="w-4 h-4 text-amber-400" />,
  },
  WAKE: {
    defaultLabel: "Waking System",
    defaultSublabel: "Restoring Sensor Pipeline",
    statusBadge: "WAKE",
    badgeStyle: "bg-sky-500/15 text-sky-300 border-sky-500/30",
    edgeGlowStyle: "rgba(56, 189, 248, 0.65)",
    coreLightingClass: "shadow-[0_0_32px_2px_rgba(56,189,248,0.65)]",
    iconNode: <Zap className="w-4 h-4 text-sky-300 animate-bounce" />,
  },
};

/**
 * CapsuleBody: The central high-precision metallic chassis.
 * Engineered with multi-layered obsidian surfaces, machined titanium rims,
 * integrated lateral hinge docking collars, and dual cyan/violet energy conduits.
 */
export const CapsuleBody: React.FC<CapsuleBodyProps> = ({
  state,
  accent = "dual",
  label,
  sublabel,
  badge,
  icon,
  onClick,
  className = "",
  interactive = false,
  testId = "capsule-body",
}) => {
  const config = STATE_CONFIGS[state] || STATE_CONFIGS.IDLE;
  const displayLabel = label ?? config.defaultLabel;
  const displaySublabel = sublabel ?? config.defaultSublabel;
  const displayBadge = badge ?? config.statusBadge;

  // Resolve accent lighting overrides
  const isCyanAccent =
    accent === "cyan" ||
    (accent === "dual" && (state === "IDLE" || state === "COUNTDOWN" || state === "ACTIVE"));
  const isVioletAccent =
    accent === "violet" ||
    (accent === "dual" && (state === "ARMED" || state === "WAKE"));

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`${displayLabel} — ${displaySublabel}`}
      data-testid={testId}
      data-capsule-state={state}
      data-capsule-accent={accent}
      onClick={interactive ? onClick : undefined}
      className={`
        group relative z-20 flex items-center justify-between
        w-full max-w-[420px] h-[64px] sm:h-[66px] px-4 py-2.5
        rounded-full select-none
        bg-gradient-to-b from-[#202534] via-[#12151f] to-[#06070a]
        border border-white/16
        transition-all duration-300
        ${interactive ? "cursor-pointer hover:border-white/30 active:scale-[0.985]" : ""}
        ${className}
      `}
      style={{
        boxShadow: `
          0 28px 65px -12px rgba(0, 0, 0, 0.95),
          0 12px 28px -6px rgba(0, 0, 0, 0.8),
          0 0 32px -4px ${config.edgeGlowStyle},
          inset 0 1.5px 2px 0 rgba(255, 255, 255, 0.35),
          inset 0 3px 6px 0 rgba(0, 0, 0, 0.85),
          inset 0 -2px 3px 0 rgba(0, 0, 0, 0.9)
        `,
      }}
    >
      {/* 1. Anisotropic Specular Highlight Sheen along top perimeter */}
      <div
        className="pointer-events-none absolute inset-0 rounded-full overflow-hidden"
        aria-hidden="true"
      >
        <div className="absolute inset-x-4 top-0 h-[1.8px] bg-gradient-to-r from-transparent via-white/45 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-b from-white/[0.09] via-transparent to-black/50" />
      </div>

      {/* 2. Left Lateral Hinge Docking Collar (Physical Receiving Flange) */}
      <div
        className="pointer-events-none absolute left-1 top-1/2 -translate-y-1/2 w-4 h-11 rounded-l-full bg-gradient-to-r from-white/20 via-white/5 to-transparent border-l border-y border-white/25"
        aria-hidden="true"
      >
        <div className="absolute left-1 top-1/2 -translate-y-1/2 w-1.5 h-6 rounded-full bg-black/70 border border-white/15" />
      </div>

      {/* 3. Left Lateral Energy Conduit (Electric Cyan) */}
      <div
        className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 w-2 h-7 rounded-full overflow-hidden flex items-center justify-center transition-all duration-300"
        aria-hidden="true"
      >
        <div
          className={`
            w-full h-full rounded-full transition-all duration-500
            ${isCyanAccent ? "bg-cyan-400 opacity-95 shadow-[0_0_12px_rgba(34,211,238,0.95)]" : "bg-cyan-900/40 opacity-30"}
          `}
        />
      </div>

      {/* 4. Center Chassis Instrumentation: Machined Aperture Bezel & Readout */}
      <div className="relative z-10 flex items-center gap-3.5 pl-4 pr-2 min-w-0">
        {/* Raised CNC Machined Aperture Housing */}
        <div
          className={`
            relative flex items-center justify-center
            w-9 h-9 rounded-full
            bg-gradient-to-b from-[#1d2232] to-[#0c0e15]
            border border-white/20
            shadow-[0_2px_8px_rgba(0,0,0,0.8),inset_0_1px_1px_rgba(255,255,255,0.25)]
            transition-all duration-300
            ${config.coreLightingClass}
          `}
        >
          {/* Internal Iris Precision Geometric Reticle */}
          <svg
            className="absolute inset-0 w-full h-full text-white/[0.08] pointer-events-none"
            viewBox="0 0 36 36"
            fill="none"
          >
            <circle cx="18" cy="18" r="16" stroke="currentColor" strokeWidth="1" strokeDasharray="3 3" />
            <circle cx="18" cy="18" r="11" stroke="currentColor" strokeWidth="0.8" />
            <line x1="18" y1="2" x2="18" y2="6" stroke="currentColor" strokeWidth="1" />
            <line x1="18" y1="30" x2="18" y2="34" stroke="currentColor" strokeWidth="1" />
            <line x1="2" y1="18" x2="6" y2="18" stroke="currentColor" strokeWidth="1" />
            <line x1="30" y1="18" x2="34" y2="18" stroke="currentColor" strokeWidth="1" />
          </svg>

          {/* Active Sensor Core Icon */}
          <div className="relative z-10 flex items-center justify-center">
            {icon ?? config.iconNode}
          </div>
        </div>

        {/* Typographic Readout with Clear Visual Hierarchy */}
        <div className="flex flex-col min-w-0 justify-center">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[13.5px] font-semibold tracking-wider uppercase text-white/95 truncate">
              {displayLabel}
            </span>
          </div>
          <span className="font-mono text-[11px] text-white/55 tracking-wide truncate">
            {displaySublabel}
          </span>
        </div>
      </div>

      {/* 5. Right Status Chip / Telemetry Badge */}
      <div className="relative z-10 flex items-center gap-2 pl-2 pr-1.5">
        <span
          className={`
            inline-flex items-center px-2.5 py-0.5 rounded-full
            font-mono text-[10.5px] font-bold tracking-wider uppercase
            border transition-all duration-300
            ${config.badgeStyle}
          `}
        >
          {displayBadge}
        </span>
      </div>

      {/* 6. Right Lateral Energy Conduit (Hyper-Violet) */}
      <div
        className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 w-2 h-7 rounded-full overflow-hidden flex items-center justify-center transition-all duration-300"
        aria-hidden="true"
      >
        <div
          className={`
            w-full h-full rounded-full transition-all duration-500
            ${isVioletAccent ? "bg-violet-400 opacity-95 shadow-[0_0_12px_rgba(168,118,255,0.95)]" : "bg-violet-900/40 opacity-30"}
          `}
        />
      </div>

      {/* 7. Right Lateral Hinge Docking Collar (Physical Receiving Flange) */}
      <div
        className="pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 w-4 h-11 rounded-r-full bg-gradient-to-l from-white/20 via-white/5 to-transparent border-r border-y border-white/25"
        aria-hidden="true"
      >
        <div className="absolute right-1 top-1/2 -translate-y-1/2 w-1.5 h-6 rounded-full bg-black/70 border border-white/15" />
      </div>
    </div>
  );
};
