/** Minimal host-boundary types retained for safe writes to the existing engine. */
export interface AirPointHudSettings {
  enabled: boolean;
  notificationsEnabled: boolean;
  timerEnabled: boolean;
  autohideEnabled: boolean;
  hudDurationS: number;
  completionDurationS: number;
}

export type AirPointHudSettingKey = keyof AirPointHudSettings;
export type CapabilityAccess = "read-write" | "read-only" | "none" | "unknown";
export type LegacyCapability = boolean | CapabilityAccess | undefined;
export type CapabilityMap = Partial<Record<AirPointHudSettingKey, LegacyCapability>>;
