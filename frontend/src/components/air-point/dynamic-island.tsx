import {
  Camera,
  Check,
  Clock,
  Hand,
  Leaf,
  Lock,
  MessageCircle,
  Play,
  ShieldCheck,
  Volume2,
  VolumeX,
} from "lucide-react";
import type { DynamicIslandState } from "@/lib/air-point-model";

export interface DynamicIslandPreviewProps {
  state: DynamicIslandState;
  volume: number;
  countdownSeconds?: number | null;
}

export const DynamicIslandPreview: React.FC<DynamicIslandPreviewProps> = ({
  state,
  volume,
  countdownSeconds,
}) => {
  const renderContent = () => {
    switch (state) {
      case "screenshot-hold":
        return (
          <div className="flex items-center gap-3 px-4 py-2 text-xs font-mono text-amber-300">
            <Camera className="w-4 h-4 animate-pulse" />
            <span>
              HOLD BOTH PALMS · {countdownSeconds ?? 3}s REMAINING (DEMO)
            </span>
          </div>
        );
      case "screenshot":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-emerald-300">
            <Check className="w-4 h-4" />
            <span>SCREENSHOT SAVED · PREVIEW</span>
          </div>
        );
      case "muted":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-rose-300">
            <VolumeX className="w-4 h-4" />
            <span>SYSTEM AUDIO MUTED · PREVIEW</span>
          </div>
        );
      case "unmuted":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-emerald-300">
            <Volume2 className="w-4 h-4" />
            <span>SYSTEM AUDIO UNMUTED · PREVIEW</span>
          </div>
        );
      case "whatsapp":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-emerald-300">
            <MessageCircle className="w-4 h-4" />
            <span>OPENING WHATSAPP DESKTOP · PREVIEW</span>
          </div>
        );
      case "reacquired":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-sky-300">
            <Hand className="w-4 h-4" />
            <span>HAND REACQUIRED · LOCKED</span>
          </div>
        );
      case "lost":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-amber-300">
            <Hand className="w-4 h-4" />
            <span>HAND LOST · STANDBY</span>
          </div>
        );
      case "volume-up":
      case "volume-down":
        return (
          <div className="flex items-center gap-3 px-4 py-2 text-xs font-mono text-white">
            <Volume2 className="w-4 h-4 text-[var(--accent-primary)]" />
            <span>PREVIEW LEVEL</span>
            <div className="w-24 h-2 rounded-full bg-white/15 overflow-hidden">
              <div
                style={{ width: `${volume}%` }}
                className="h-full bg-[var(--accent-primary)] transition-all"
              />
            </div>
            <span className="tabular-nums">{volume}%</span>
          </div>
        );
      case "wakanda-hold":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-purple-300">
            <ShieldCheck className="w-4 h-4 animate-pulse text-[#b983ff]" />
            <span className="font-semibold tracking-wider">
              WAKANDA FOREVER · {countdownSeconds ?? 2.0}s (DEMO)
            </span>
          </div>
        );
      case "wakanda-forever":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-purple-200">
            <Lock className="w-4 h-4 text-[#b983ff]" />
            <span className="font-semibold tracking-wider">WAKANDA FOREVER · LOCKED</span>
          </div>
        );
      case "normal":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-emerald-300">
            <Play className="w-4 h-4 fill-emerald-300 text-emerald-300" />
            <span className="font-semibold tracking-wider">AIR POINT · NORMAL</span>
          </div>
        );
      case "power-save-waiting":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-amber-300">
            <Clock className="w-4 h-4 animate-pulse text-amber-400" />
            <span className="font-semibold tracking-wider">
              POWER SAVER · WAITING
            </span>
          </div>
        );
      case "power-save-countdown":
        return (
          <div className="flex items-center gap-3 px-4 py-2 text-xs font-mono text-emerald-300">
            <Leaf className="w-4 h-4 text-emerald-400" />
            <span className="font-semibold tracking-wider">POWER SAVER</span>
            <span className="px-2 py-0.5 rounded-full bg-emerald-950/70 border border-emerald-500/30 text-emerald-300 text-[11px] font-bold tabular-nums">
              {countdownSeconds !== undefined && countdownSeconds !== null
                ? `${String(Math.floor(countdownSeconds / 60)).padStart(2, "0")}:${String(countdownSeconds % 60).padStart(2, "0")}`
                : "02:00"}
            </span>
          </div>
        );
      case "power-save-complete":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-emerald-300">
            <Leaf className="w-4 h-4 text-emerald-400" />
            <span className="font-semibold tracking-wider">
              POWER SAVER · HIDING
            </span>
          </div>
        );
      case "power-save-wake":
        return (
          <div className="flex items-center gap-2.5 px-4 py-2 text-xs font-mono text-sky-300">
            <Hand className="w-4 h-4 text-sky-400" />
            <span className="font-semibold tracking-wider">
              HAND DETECTED · NORMAL
            </span>
          </div>
        );
      case "idle":
      default:
        return (
          <div className="flex items-center gap-2.5 px-3.5 py-1.5 text-xs font-mono text-slate-300">
            <span className="w-2 h-2 rounded-full bg-[var(--accent-primary)]" />
            <span>AIR POINT HUD · IDLE</span>
          </div>
        );
    }
  };

  return (
    <div
      data-testid="dynamic-island-preview"
      data-island-state={state}
      className="inline-flex items-center justify-center rounded-full bg-[#090b10] border border-white/15 shadow-lg transition-all"
    >
      {renderContent()}
    </div>
  );
};
