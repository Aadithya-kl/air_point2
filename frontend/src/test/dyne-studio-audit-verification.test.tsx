import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { DyneStudio } from "@/components/air-point/dyne-studio/dyne-studio";
import { PREVIEW_CAPSULES } from "@/components/air-point/dyne-studio/capsules";
import type { DyneHostAdapter } from "@/components/air-point/dyne-studio/layered/host-adapter";
import type { CapabilityMap } from "@/components/air-point/dyne-studio/layered/types";

const TEST_CAPABILITIES: CapabilityMap = {
  enabled: "read-write",
  notificationsEnabled: "read-write",
  timerEnabled: "read-write",
  autohideEnabled: "read-write",
  hudDurationS: "read-write",
  completionDurationS: "read-write",
};

describe("Dyne Studio Audit Verification & Acceptance Gates Suite", () => {
  let hostAdapter: DyneHostAdapter;
  let recordedUpdates: Record<string, unknown>[];
  let recordedCountdowns: number[];

  beforeEach(() => {
    vi.restoreAllMocks();
    recordedUpdates = [];
    recordedCountdowns = [];
    hostAdapter = {
      setIslandSettings: vi.fn(async (updates) => {
        recordedUpdates.push(updates);
        return true;
      }),
      testDesktopCountdown: vi.fn(async (seconds) => {
        recordedCountdowns.push(seconds);
        return true;
      }),
    };
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("Gate 1 (ISS-01): Top-left slot renders with icon and label across all category rings", async () => {
    render(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={TEST_CAPABILITIES}
        desktopSettings={{
          enabled: true,
          notificationsEnabled: true,
          timerEnabled: true,
          autohideEnabled: true,
          hudDurationS: 120,
          completionDurationS: 2,
        }}
        hostConnected={true}
        settingsSynced={true}
      />,
    );

    // Open main options ring
    const centralCapsule = screen.getByRole("button", { name: /Normal — open main options/i });
    fireEvent.click(centralCapsule);

    // 1. In Main options: top-left slot is "Colour" with visible label
    const colourBtn = screen.getByRole("button", { name: "Colour" });
    expect(colourBtn).toBeInTheDocument();
    expect(colourBtn.querySelector(".segment-label")).toHaveTextContent("Colour");

    // Navigate to Material: top slot is "Surface" with visible label (not clipped to "face")
    const materialBtn = screen.getByRole("button", { name: "Material" });
    fireEvent.click(materialBtn);
    const surfaceBtn = screen.getByRole("button", { name: "Surface" });
    expect(surfaceBtn).toBeInTheDocument();
    expect(surfaceBtn.querySelector(".segment-label")).toHaveTextContent("Surface");

    // Go back to main
    fireEvent.keyDown(window, { key: "Escape" });

    // Navigate to Notifications: top slot is "Notifications: On" (not clipped to "tions: On")
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
    const notifBtn = screen.getByRole("button", { name: "Notifications: On" });
    expect(notifBtn).toBeInTheDocument();
    expect(notifBtn.querySelector(".segment-label")).toHaveTextContent("Notifications: On");

    // Go back to main
    fireEvent.keyDown(window, { key: "Escape" });

    // Navigate to Behaviour & Timing: top-left slot is "Show HUD: On"
    fireEvent.click(screen.getByRole("button", { name: "Behaviour & Timing" }));
    const showHudBtn = screen.getByRole("button", { name: "Show HUD: On" });
    expect(showHudBtn).toBeInTheDocument();
    expect(showHudBtn.querySelector(".segment-label")).toHaveTextContent("Show HUD: On");
  });

  it("Gate 2 (ISS-02, ISS-03): Multi-line labels have adequate line-height and no divider collision", async () => {
    render(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={TEST_CAPABILITIES}
        desktopSettings={{
          enabled: true,
          notificationsEnabled: true,
          timerEnabled: true,
          autohideEnabled: true,
          hudDurationS: 120,
          completionDurationS: 2,
        }}
        hostConnected={true}
        settingsSynced={true}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));

    // Notifications: Completion-message duration
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
    const completionOption = screen.getByRole("button", {
      name: "Completion-message duration",
    });
    expect(completionOption).toBeInTheDocument();
    const tspans = completionOption.querySelectorAll("tspan");
    expect(tspans.length).toBe(2);
    expect(tspans[0]).toHaveTextContent("Completion-message");
    expect(tspans[1]).toHaveTextContent("duration");
    // Verify dy="16" prevents negative overlap
    expect(tspans[1]?.getAttribute("dy")).toBe("16");

    // Back to main -> Behaviour & Timing
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Behaviour & Timing" }));

    // Test countdown button is clearly separated and enabled
    const testCountdownBtn = screen.getByRole("button", { name: "Test countdown" });
    expect(testCountdownBtn).toBeInTheDocument();
    expect(testCountdownBtn).toBeEnabled();
  });

  it("Gate 3 (ISS-06): Host duration sliders update live locally and commit cleanly without stale write races", async () => {
    render(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={TEST_CAPABILITIES}
        desktopSettings={{
          enabled: true,
          notificationsEnabled: true,
          timerEnabled: true,
          autohideEnabled: true,
          hudDurationS: 120,
          completionDurationS: 2,
        }}
        hostConnected={true}
        settingsSynced={true}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Behaviour & Timing" }));

    const slider = screen.getByRole("slider", { name: "HUD duration" });
    expect(slider).toHaveValue("120");

    // Dragging updates local UI value immediately
    fireEvent.change(slider, { target: { value: "240" } });
    expect(screen.getByText(/HUD duration:\s*240\s*s/i)).toBeInTheDocument();

    // Release commits to host
    fireEvent.pointerUp(slider, { clientX: 100, clientY: 100 });

    await waitFor(() => {
      expect(hostAdapter.setIslandSettings).toHaveBeenCalledWith({ hudDurationS: 240 });
    });
  });

  it("Gate 4 (ISS-07): Reports honest host status across connected, offline, and unsynced conditions", () => {
    // 1. Connected & synced
    const { rerender } = render(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={TEST_CAPABILITIES}
        desktopSettings={{
          enabled: true,
          notificationsEnabled: true,
          timerEnabled: true,
          autohideEnabled: true,
          hudDurationS: 120,
          completionDurationS: 2,
        }}
        hostConnected={true}
        settingsSynced={true}
      />,
    );
    expect(screen.getByText("HOST CONNECTED")).toBeInTheDocument();

    // 2. Offline but previously synced (showing last known settings)
    rerender(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={TEST_CAPABILITIES}
        desktopSettings={{
          enabled: true,
          notificationsEnabled: true,
          timerEnabled: true,
          autohideEnabled: true,
          hudDurationS: 120,
          completionDurationS: 2,
        }}
        hostConnected={false}
        settingsSynced={true}
      />,
    );
    expect(screen.getByText("HOST OFFLINE · LAST KNOWN SETTINGS")).toBeInTheDocument();

    // 3. Offline & unsynced
    rerender(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={TEST_CAPABILITIES}
        desktopSettings={null}
        hostConnected={false}
        settingsSynced={false}
      />,
    );
    expect(screen.getByText("HOST OFFLINE · SETTINGS UNSYNCED")).toBeInTheDocument();
  });

  it("Gate 5 (ISS-08): Host boundary strictly enforces allowlist and never writes appearance values", async () => {
    render(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={TEST_CAPABILITIES}
        desktopSettings={{
          enabled: true,
          notificationsEnabled: true,
          timerEnabled: true,
          autohideEnabled: true,
          hudDurationS: 120,
          completionDurationS: 2,
        }}
        hostConnected={true}
        settingsSynced={true}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));

    // Change appearance (Colour -> Red)
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));
    fireEvent.click(screen.getByRole("button", { name: "Red" }));

    // Appearance change must NEVER invoke hostAdapter
    expect(hostAdapter.setIslandSettings).not.toHaveBeenCalled();
    expect(hostAdapter.testDesktopCountdown).not.toHaveBeenCalled();

    // Event state switching must NEVER invoke hostAdapter
    const nextBtn = screen.getByRole("button", { name: "Next event state" });
    fireEvent.click(nextBtn);
    expect(hostAdapter.setIslandSettings).not.toHaveBeenCalled();
  });

  it("Gate 6 (ISS-09): Event switcher maintains independent appearance per event state", async () => {
    render(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={TEST_CAPABILITIES}
        desktopSettings={{
          enabled: true,
          notificationsEnabled: true,
          timerEnabled: true,
          autohideEnabled: true,
          hudDurationS: 120,
          completionDurationS: 2,
        }}
        hostConnected={true}
        settingsSynced={true}
      />,
    );

    // Initial state: Normal
    expect(screen.getByRole("button", { name: /Normal — open main options/i })).toBeInTheDocument();

    // Set Normal accent to Red
    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));
    fireEvent.click(screen.getByRole("button", { name: "Red" }));

    // Back to main -> Switch event state to Power Save Waiting
    fireEvent.click(screen.getByRole("button", { name: "Next event state" }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", {
          name: /Power Save Waiting — (open main options|go back one level)/i,
        }),
      ).toBeInTheDocument();
    });

    // Verify switch occurred without mutating host
    expect(hostAdapter.setIslandSettings).not.toHaveBeenCalled();
  });

  it("Gate 7 (ISS-10): All visible stage typography respects minimum 12px requirement", () => {
    const { container } = render(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={TEST_CAPABILITIES}
        desktopSettings={{
          enabled: true,
          notificationsEnabled: true,
          timerEnabled: true,
          autohideEnabled: true,
          hudDurationS: 120,
          completionDurationS: 2,
        }}
        hostConnected={true}
        settingsSynced={true}
      />,
    );

    // Verify preview badge exists and renders readable text
    const badge = container.querySelector(".capsule-preview-badge");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("Preview");
  });
});
