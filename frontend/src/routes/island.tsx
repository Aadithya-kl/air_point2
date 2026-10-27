import React, { useMemo } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useAirPointEngine } from "@/components/air-point/engine";
import { DyneStudio } from "@/components/air-point/dyne-studio/dyne-studio";
import type { DyneHostAdapter } from "@/components/air-point/dyne-studio/layered/host-adapter";
import type { CapabilityMap } from "@/components/air-point/dyne-studio/layered/types";

export const Route = createFileRoute("/island")({
  component: DynamicIslandPage,
});

const DYNE_HOST_CAPABILITIES: CapabilityMap = {
  // Each field is explicitly supported by the existing engine adapter's
  // setIslandSettings mapping. Rejected host writes still surface as failures.
  enabled: "read-write",
  notificationsEnabled: "read-write",
  timerEnabled: "read-write",
  autohideEnabled: "read-write",
  hudDurationS: "read-write",
  completionDurationS: "read-write",
};

export function DynamicIslandPage() {
  const engine = useAirPointEngine();
  const { islandSettings, islandSettingsSynced, setIslandSettings, testDesktopCountdown } = engine;

  const hostAdapter = useMemo<DyneHostAdapter>(
    () => ({
      setIslandSettings: (updates) => setIslandSettings(updates),
      testDesktopCountdown: (durationS = 5) => testDesktopCountdown(durationS),
    }),
    [setIslandSettings, testDesktopCountdown],
  );

  return (
    <div
      className="dyne-island-page flex flex-col items-center justify-center min-h-[calc(100vh-140px)] w-full py-4"
      data-testid="dynamic-island-page"
    >
      <section aria-label="Dyne Studio" className="w-full flex justify-center">
        <DyneStudio
          hostAdapter={hostAdapter}
          capabilities={DYNE_HOST_CAPABILITIES}
          desktopSettings={islandSettings}
          hostConnected={engine.connected}
          settingsSynced={islandSettingsSynced}
        />
      </section>
    </div>
  );
}
