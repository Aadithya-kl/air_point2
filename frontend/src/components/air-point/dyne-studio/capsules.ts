import type { ComponentType } from "react";
import {
  Activity,
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
import type { Settings } from "./studio";
import type { DynamicIslandState } from "@/lib/air-point-model";

export interface CapsuleDefinition {
  id: DynamicIslandState;
  name: string;
  message: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number; className?: string }>;
  defaultSettings: Settings;
  isPreviewOnly: true;
}

function initial(accent: string, texture: string, style: string, roundness: number): Settings {
  return {
    accent,
    texture,
    font: "System",
    fontSize: 23,
    weight: 400,
    intensity: 50,
    matteIntensity: 50,
    translucentIntensity: 50,
    roundness,
    style,
    customRgb: { r: 140, g: 80, b: 255 },
  };
}

/** Local appearance presets keyed by all 17 real event-state names in air-point-model.ts. */
export const PREVIEW_CAPSULES: CapsuleDefinition[] = [
  {
    id: "normal",
    name: "Normal",
    message: "AIR POINT · NORMAL",
    icon: Play,
    isPreviewOnly: true,
    defaultSettings: initial("Gold", "Glass", "Balanced", 56),
  },
  {
    id: "power-save-waiting",
    name: "Power Save Waiting",
    message: "POWER SAVER · WAITING",
    icon: Clock,
    isPreviewOnly: true,
    defaultSettings: initial("Cyan", "Matte", "Quiet", 28),
  },
  {
    id: "power-save-countdown",
    name: "Power Save Countdown",
    message: "POWER SAVER · 02:00",
    icon: Leaf,
    isPreviewOnly: true,
    defaultSettings: initial("Blue", "Glass", "Balanced", 42),
  },
  {
    id: "power-save-complete",
    name: "Power Save Complete",
    message: "POWER SAVER · HIDING",
    icon: Leaf,
    isPreviewOnly: true,
    defaultSettings: initial("Green", "Glass", "Luminous", 56),
  },
  {
    id: "power-save-wake",
    name: "Hand Detected / Wake",
    message: "HAND DETECTED · NORMAL",
    icon: Hand,
    isPreviewOnly: true,
    defaultSettings: initial("Purple", "Translucent", "Balanced", 42),
  },
  {
    id: "screenshot",
    name: "Screenshot",
    message: "SCREENSHOT SAVED · PREVIEW",
    icon: Check,
    isPreviewOnly: true,
    defaultSettings: initial("Green", "Glass", "Luminous", 56),
  },
  {
    id: "screenshot-hold",
    name: "Screenshot Hold",
    message: "HOLD BOTH PALMS · 3s",
    icon: Camera,
    isPreviewOnly: true,
    defaultSettings: initial("Gold", "Matte", "Balanced", 42),
  },
  {
    id: "muted",
    name: "Muted",
    message: "SYSTEM AUDIO MUTED",
    icon: VolumeX,
    isPreviewOnly: true,
    defaultSettings: initial("Red", "Matte", "Quiet", 28),
  },
  {
    id: "unmuted",
    name: "Unmuted",
    message: "SYSTEM AUDIO UNMUTED",
    icon: Volume2,
    isPreviewOnly: true,
    defaultSettings: initial("Cyan", "Glass", "Balanced", 56),
  },
  {
    id: "whatsapp",
    name: "WhatsApp",
    message: "OPENING WHATSAPP DESKTOP",
    icon: MessageCircle,
    isPreviewOnly: true,
    defaultSettings: initial("Green", "Glass", "Balanced", 56),
  },
  {
    id: "reacquired",
    name: "Hand Reacquired",
    message: "HAND REACQUIRED · LOCKED",
    icon: Hand,
    isPreviewOnly: true,
    defaultSettings: initial("Blue", "Glass", "Luminous", 42),
  },
  {
    id: "lost",
    name: "Hand Lost",
    message: "HAND LOST · STANDBY",
    icon: Hand,
    isPreviewOnly: true,
    defaultSettings: initial("Gold", "Matte", "Quiet", 28),
  },
  {
    id: "volume-up",
    name: "Volume Up",
    message: "VOLUME LEVEL · 68%",
    icon: Volume2,
    isPreviewOnly: true,
    defaultSettings: initial("Cyan", "Glass", "Balanced", 56),
  },
  {
    id: "volume-down",
    name: "Volume Down",
    message: "VOLUME LEVEL · 68%",
    icon: Volume2,
    isPreviewOnly: true,
    defaultSettings: initial("Blue", "Glass", "Balanced", 56),
  },
  {
    id: "wakanda-forever",
    name: "Wakanda Forever",
    message: "WAKANDA FOREVER · LOCKED",
    icon: Lock,
    isPreviewOnly: true,
    defaultSettings: initial("Purple", "Glass", "Luminous", 56),
  },
  {
    id: "wakanda-hold",
    name: "Wakanda Hold",
    message: "WAKANDA FOREVER · 2.0s",
    icon: ShieldCheck,
    isPreviewOnly: true,
    defaultSettings: initial("Purple", "Matte", "Balanced", 42),
  },
  {
    id: "idle",
    name: "Idle",
    message: "AIR POINT HUD · IDLE",
    icon: Activity,
    isPreviewOnly: true,
    defaultSettings: initial("Neon", "Glass", "Balanced", 56),
  },
];
