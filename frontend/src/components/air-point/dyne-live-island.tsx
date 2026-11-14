import React from "react";
import {
  AlertTriangle,
  Camera,
  Check,
  Hand,
  Leaf,
  Lock,
  MessageCircle,
  MousePointer2,
  Pause,
  Play,
  Power,
  ShieldCheck,
  Volume2,
  VolumeX,
  Zap,
} from "lucide-react";
import {
  type AirPointEvent,
  type DyneAppearance,
  type DyneIslandPosition,
  dyneAccentHex,
} from "@/lib/air-point-model";

/**
 * The live Dyne notification island of the Control Center.
 *
 * It renders only real events published by the Python engine (the same
 * events the desktop capsule shows); the Dyne Studio carousel and
 * DynamicIslandPreview remain explicit previews. The look (accent, shape,
 * font, material) and the position are the host-persisted Dyne settings, so
 * the island matches the choices made in Dyne Studio across restarts.
 */

export interface DyneLiveIslandProps {
  event: AirPointEvent | null;
  appearance: DyneAppearance;
  position: DyneIslandPosition;
  reducedMotion?: boolean;
  onDismiss?: () => void;
}

type IconComponent = React.ComponentType<{ className?: string }>;

interface Presentation {
  icon: IconComponent;
  tone: "accent" | "healthy" | "warning" | "danger" | "neutral";
}

const PRESENTATION_BY_TYPE: Record<string, Presentation> = {
  "engine.started": { icon: Power, tone: "neutral" },
  "engine.paused": { icon: Pause, tone: "warning" },
  "engine.resumed": { icon: Play, tone: "healthy" },
  "engine.stopping": { icon: Power, tone: "warning" },
  "tracking.acquired": { icon: Hand, tone: "healthy" },
  "tracking.lost": { icon: Hand, tone: "warning" },
  "tracking.recovered": { icon: Hand, tone: "healthy" },
  "screenshot.captured": { icon: Camera, tone: "healthy" },
  "screenshot.failed": { icon: AlertTriangle, tone: "danger" },
  "app.launched": { icon: MessageCircle, tone: "healthy" },
  "app.launch_failed": { icon: AlertTriangle, tone: "danger" },
  "audio.volume": { icon: Volume2, tone: "accent" },
  "audio.muted": { icon: VolumeX, tone: "warning" },
  "audio.unmuted": { icon: Volume2, tone: "healthy" },
  "audio.failed": { icon: AlertTriangle, tone: "danger" },
  "drag.started": { icon: MousePointer2, tone: "accent" },
  "drag.completed": { icon: Check, tone: "healthy" },
  "drag.released": { icon: MousePointer2, tone: "neutral" },
  "drag.failed": { icon: AlertTriangle, tone: "danger" },
  "wakanda.confirmed": { icon: ShieldCheck, tone: "accent" },
  "lock.accepted": { icon: Lock, tone: "healthy" },
  "lock.failed": { icon: AlertTriangle, tone: "danger" },
  "power.save_entered": { icon: Leaf, tone: "neutral" },
  "power.wake": { icon: Zap, tone: "healthy" },
};

const TONE_COLOR: Record<Presentation["tone"], string | null> = {
  accent: null, // uses the Dyne accent colour
  healthy: "#3cd6a0",
  warning: "#f4c75b",
  danger: "#ef505c",
  neutral: "#9ca3af",
};

const FONT_FAMILY: Record<string, string> = {
  System: "Arial, Helvetica, sans-serif",
  Mono: '"Courier New", monospace',
  Humanist: "Verdana, sans-serif",
};

function presentationFor(event: AirPointEvent): Presentation {
  if (event.type && PRESENTATION_BY_TYPE[event.type]) return PRESENTATION_BY_TYPE[event.type]!;
  const kind = event.event.toLowerCase();
  if (kind.includes("fail") || kind.includes("fault")) return { icon: AlertTriangle, tone: "danger" };
  if (kind.includes("lost")) return { icon: Hand, tone: "warning" };
  return { icon: Zap, tone: "accent" };
}

function positionStyle(position: DyneIslandPosition): React.CSSProperties {
  const base: React.CSSProperties = { position: "fixed", zIndex: 60, pointerEvents: "auto" };
  switch (position) {
    case "top-left":
      return { ...base, top: 14, left: 16 };
    case "top-right":
      return { ...base, top: 14, right: 16 };
    case "bottom-center":
      return { ...base, bottom: 18, left: "50%", transform: "translateX(-50%)" };
    case "top-center":
    default:
      return { ...base, top: 14, left: "50%", transform: "translateX(-50%)" };
  }
}

function surfaceStyle(appearance: DyneAppearance): React.CSSProperties {
  const alpha =
    appearance.texture === "Translucent"
      ? 0.55 + (appearance.translucentIntensity / 100) * 0.3
      : appearance.texture === "Glass"
        ? 0.72 + (appearance.intensity / 100) * 0.2
        : 0.9 + (appearance.matteIntensity / 100) * 0.1;
  const glow =
    appearance.style === "Luminous" ? 0.45 : appearance.style === "Quiet" ? 0.12 : 0.25;
  const accent = dyneAccentHex(appearance);
  const glowHex = Math.round(glow * 255).toString(16).padStart(2, "0");
  return {
    background: `rgba(12, 13, 18, ${alpha.toFixed(2)})`,
    borderRadius: appearance.roundness,
    boxShadow: `0 10px 30px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.08), 0 0 24px ${accent}${glowHex}`,
    ...(appearance.texture === "Matte" ? {} : { backdropFilter: "blur(14px)" }),
    fontFamily: FONT_FAMILY[appearance.font] ?? FONT_FAMILY["System"]!,
    fontWeight: appearance.weight,
    color: "#f5f6fa",
  };
}

export const DyneLiveIsland: React.FC<DyneLiveIslandProps> = ({
  event,
  appearance,
  position,
  reducedMotion = false,
  onDismiss,
}) => {
  if (!event) return null;
  const presentation = presentationFor(event);
  const Icon = presentation.icon;
  const accent = dyneAccentHex(appearance);
  const iconColor = TONE_COLOR[presentation.tone] ?? accent;
  const title = event.title ?? event.action;
  const message = event.message ?? event.action;
  const volumePercent =
    event.type === "audio.volume" && event.metadata && typeof event.metadata["percent"] === "number"
      ? (event.metadata["percent"] as number)
      : null;
  const fontSize = Math.max(11, Math.round(appearance.fontSize * 0.56));

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="dyne-live-island"
      data-live="true"
      data-event-type={event.type ?? event.event}
      data-event-id={event.id}
      data-position={position}
      style={positionStyle(position)}
    >
      <div
        className={`flex items-center gap-3 px-4 py-2.5 border border-white/10 ${
          reducedMotion ? "" : "transition-all duration-300"
        }`}
        style={surfaceStyle(appearance)}
        onClick={onDismiss}
        title="Live Dyne notification from the AirPoint engine. Click to dismiss."
      >
        <span
          className="inline-flex items-center justify-center w-7 h-7 rounded-full shrink-0"
          style={{ background: `${iconColor}22`, color: iconColor }}
        >
          <Icon className="w-4 h-4" />
        </span>
        <div className="min-w-0 max-w-[420px]">
          <div className="flex items-center gap-2">
            <span className="font-semibold tracking-wide truncate" style={{ fontSize: fontSize + 1 }}>
              {title}
            </span>
            <span
              className="text-[9px] font-mono uppercase tracking-[0.18em] px-1.5 py-0.5 rounded-full border"
              style={{ color: accent, borderColor: `${accent}66` }}
            >
              Live
            </span>
          </div>
          {message !== title && (
            <div className="truncate opacity-80" style={{ fontSize }}>
              {message}
            </div>
          )}
          {volumePercent !== null && (
            <div className="flex items-center gap-2 mt-1">
              <div className="w-28 h-1.5 rounded-full bg-white/15 overflow-hidden">
                <div
                  className={reducedMotion ? "h-full" : "h-full transition-all"}
                  style={{ width: `${volumePercent}%`, background: accent }}
                />
              </div>
              <span className="tabular-nums text-[11px] opacity-80">{volumePercent}%</span>
            </div>
          )}
        </div>
        <span className="font-mono text-[10px] opacity-60 shrink-0 pl-1">{event.time}</span>
      </div>
    </div>
  );
};
