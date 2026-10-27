import type {
  AirPointHudSettingKey,
  AirPointHudSettings,
  CapabilityAccess,
  CapabilityMap,
  LegacyCapability,
} from "./types";

/** Normalize legacy capability booleans without losing the four-state contract. */
export function normalizeCapability(value: LegacyCapability): CapabilityAccess {
  if (value === true) return "read-write";
  if (value === false) return "none";
  if (value === "read-write" || value === "read-only" || value === "none" || value === "unknown") {
    return value;
  }
  return "unknown";
}

export function canRead(access: LegacyCapability): boolean {
  const normalized = normalizeCapability(access);
  return normalized === "read-write" || normalized === "read-only";
}

export function canWrite(access: LegacyCapability): boolean {
  return normalizeCapability(access) === "read-write";
}

export function reportedValueLabel(
  access: LegacyCapability,
): "Editable" | "Reported by desktop" | "Not available on this desktop yet" | "Unknown" {
  switch (normalizeCapability(access)) {
    case "read-write":
      return "Editable";
    case "read-only":
      return "Reported by desktop";
    case "none":
      return "Not available on this desktop yet";
    case "unknown":
      return "Unknown";
  }
}

/**
 * Whitelist of the exact host settings supported by the discovered AirPoint
 * contract. Concept-only values and UI preferences are deliberately absent.
 */
export const AIRPOINT_SETTING_KEYS: readonly AirPointHudSettingKey[] = [
  "enabled",
  "notificationsEnabled",
  "timerEnabled",
  "autohideEnabled",
  "hudDurationS",
  "completionDurationS",
] as const;

export const AIRPOINT_SETTING_CONSTRAINTS = Object.freeze({
  enabled: { kind: "boolean" as const },
  notificationsEnabled: { kind: "boolean" as const },
  timerEnabled: { kind: "boolean" as const },
  autohideEnabled: { kind: "boolean" as const },
  hudDurationS: { kind: "number" as const, min: 10, max: 1800, step: 10 },
  completionDurationS: { kind: "number" as const, min: 1, max: 5, step: 0.5 },
});

/** Runtime validation protects the host boundary even when an untyped caller casts a payload. */
export function isValidAirPointSettingValue(
  key: AirPointHudSettingKey,
  value: unknown,
): value is AirPointHudSettings[typeof key] {
  const rule = AIRPOINT_SETTING_CONSTRAINTS[key];
  if (rule.kind === "boolean") return typeof value === "boolean";
  if (typeof value !== "number" || !Number.isFinite(value) || value < rule.min || value > rule.max)
    return false;
  const stepsFromMin = (value - rule.min) / rule.step;
  return Math.abs(stepsFromMin - Math.round(stepsFromMin)) < 1e-8;
}

/**
 * Keep only explicitly read-write keys. Unknown, read-only, none, unreported,
 * Concept overrides, and reduced-motion preferences never reach the host.
 */
export function filterWritableSettings(
  updates: Partial<AirPointHudSettings>,
  capabilities: CapabilityMap,
): Partial<AirPointHudSettings> {
  const result: Partial<AirPointHudSettings> = {};
  for (const key of AIRPOINT_SETTING_KEYS) {
    if (
      Object.prototype.hasOwnProperty.call(updates, key) &&
      updates[key] !== undefined &&
      canWrite(capabilities[key]) &&
      isValidAirPointSettingValue(key, updates[key])
    ) {
      (result as Record<AirPointHudSettingKey, unknown>)[key] = updates[key];
    }
  }
  return result;
}
