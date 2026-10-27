import { filterWritableSettings } from "./capabilities";
import type { CapabilityMap, AirPointHudSettings } from "./types";

/** Narrow, injectable boundary for integration with useAirPointEngine(). */
export interface DyneHostAdapter {
  setIslandSettings(updates: Partial<AirPointHudSettings>): Promise<boolean>;
  testDesktopCountdown?(durationS?: number): Promise<boolean>;
}

export interface SafeCommitResult {
  accepted: boolean;
  forwarded: Partial<AirPointHudSettings>;
  reason?: "no-writable-fields" | "host-rejected";
}

/**
 * A defensive bridge: only explicitly read-write, known host settings can be
 * forwarded. Concept settings and reduced-motion preferences have no type path
 * through this function.
 */
export async function commitDesktopSettings(
  host: DyneHostAdapter,
  updates: Partial<AirPointHudSettings>,
  capabilities: CapabilityMap,
): Promise<SafeCommitResult> {
  const forwarded = filterWritableSettings(updates, capabilities);
  if (Object.keys(forwarded).length === 0) {
    return { accepted: false, forwarded, reason: "no-writable-fields" };
  }
  const accepted = await host.setIslandSettings(forwarded);
  return accepted ? { accepted, forwarded } : { accepted, forwarded, reason: "host-rejected" };
}

export async function runDesktopCountdownTest(
  host: DyneHostAdapter,
  durationS = 5,
): Promise<boolean> {
  if (!host.testDesktopCountdown) return false;
  if (!Number.isFinite(durationS) || durationS <= 0) return false;
  return host.testDesktopCountdown(durationS);
}
