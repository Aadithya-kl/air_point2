import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, waitFor, within } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { createRouter, rootRouteId } from "@tanstack/react-router";
import { routeTree } from "@/routeTree.gen";
import {
  AirPointEngineProvider,
  useAirPointEngine,
} from "@/components/air-point/engine";
import { DesktopShell } from "@/components/air-point/shell";
import { DynamicIslandPage } from "@/routes/island";
import { AppearancePage } from "@/routes/appearance";

// Mock TanStack router for isolated shell rendering
vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({
      children,
      to,
      ...props
    }: {
      children: React.ReactNode;
      to?: string;
      [key: string]: unknown;
    }) => (
      <a href={to || "#"} data-to={to} {...props}>
        {children}
      </a>
    ),
    useRouterState: () => ({ location: { pathname: "/island" } }),
  };
});

describe("Dynamic Island Tab & Smart Power Notifications Suite", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("Requirement 1: TanStack router matches /island route successfully", () => {
    const router = createRouter({
      routeTree,
      context: { queryClient: new QueryClient() },
    });
    const matches = router.matchRoutes("/island");
    expect(matches.at(-1)?.routeId).not.toBe(rootRouteId);
    expect(matches.at(-1)?.pathname).toBe("/island");
  });

  it("Requirement 2: DesktopShell renders Dynamic Island nav item alongside other tabs", () => {
    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>Island Content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    // Verify all primary navigation items are present
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Gestures")).toBeInTheDocument();
    expect(screen.getByText("Cursor & Controls")).toBeInTheDocument();
    expect(screen.getAllByText("Dynamic Island").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Appearance")).toBeInTheDocument();
    expect(screen.getByText("About Air Point")).toBeInTheDocument();

    // Verify Dynamic Island link points to /island
    const islandLink = screen.getByRole("link", { name: /Dynamic Island/i });
    expect(islandLink).toHaveAttribute("data-to", "/island");
  });

  it("Requirement 3: Distinguishes simulated preview clearly from real desktop overlay status", () => {
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>
    );

    // Explicit preview simulation badge
    expect(screen.getByText("PREVIEW SIMULATION (In-App Only)")).toBeInTheDocument();

    // Real desktop overlay status card
    expect(screen.getByText("Real Desktop Overlay Status")).toBeInTheDocument();
    expect(screen.getByText(/ACTIVE \(Win32\)/i)).toBeInTheDocument();
  });

  it("Requirement 4: Renders configuration switches for overlay, notifications, timer, and autohide", () => {
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>
    );

    const toggleOverlay = screen.getByTestId("toggle-island-enabled");
    const toggleNotifications = screen.getByTestId("toggle-island-notifications");
    const toggleTimer = screen.getByTestId("toggle-island-timer");
    const toggleAutohide = screen.getByTestId("toggle-island-autohide");

    expect(toggleOverlay).toBeInTheDocument();
    expect(toggleNotifications).toBeInTheDocument();
    expect(toggleTimer).toBeInTheDocument();
    expect(toggleAutohide).toBeInTheDocument();

    // All default to checked
    expect(toggleOverlay).toHaveAttribute("aria-checked", "true");
    expect(toggleNotifications).toHaveAttribute("aria-checked", "true");
    expect(toggleTimer).toHaveAttribute("aria-checked", "true");
    expect(toggleAutohide).toHaveAttribute("aria-checked", "true");
  });

  it("Requirement 5: Displays formatted HUD duration and preset duration buttons", () => {
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>
    );

    // Default duration is 2 minutes (120s)
    const durationLabel = screen.getByTestId("hud-duration-label");
    expect(durationLabel).toHaveTextContent("2 min (120s)");

    // Preset buttons are rendered
    expect(screen.getByRole("button", { name: "30s" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1 min" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "2 min (Default)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "5 min" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "10 min" })).toBeInTheDocument();
  });

  it("Requirement 6: Simulation controls trigger corresponding preview states", async () => {
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>
    );

    const previewContainer = screen.getByTestId("dynamic-island-preview");

    // 1. Simulate Waiting for Inactivity
    fireEvent.click(screen.getByRole("button", { name: /Waiting for Inactivity/i }));
    await waitFor(() => {
      expect(previewContainer).toHaveAttribute("data-island-state", "power-save-waiting");
      expect(within(previewContainer).getByText("POWER SAVER · WAITING")).toBeInTheDocument();
    });

    // 2. Simulate Power Saver Mode (Countdown)
    fireEvent.click(screen.getByRole("button", { name: /Power Saver Mode/i }));
    await waitFor(() => {
      expect(previewContainer).toHaveAttribute("data-island-state", "power-save-countdown");
      expect(within(previewContainer).getByText("POWER SAVER")).toBeInTheDocument();
    });

    // 3. Simulate Countdown Complete
    fireEvent.click(screen.getByRole("button", { name: /Countdown Complete/i }));
    await waitFor(() => {
      expect(previewContainer).toHaveAttribute("data-island-state", "power-save-complete");
      expect(within(previewContainer).getByText("POWER SAVER · HIDING")).toBeInTheDocument();
    });

    // 4. Simulate Hand Detected / Wake
    fireEvent.click(screen.getByRole("button", { name: /Hand Detected \/ Wake/i }));
    await waitFor(() => {
      expect(previewContainer).toHaveAttribute("data-island-state", "power-save-wake");
      expect(within(previewContainer).getByText("HAND DETECTED · NORMAL")).toBeInTheDocument();
    });

    // 5. Simulate Normal Mode
    fireEvent.click(screen.getByRole("button", { name: /Normal Mode/i }));
    await waitFor(() => {
      expect(previewContainer).toHaveAttribute("data-island-state", "normal");
      expect(within(previewContainer).getByText("AIR POINT · NORMAL")).toBeInTheDocument();
    });
  });

  it("Requirement 7: Toggling settings sends POST /api/settings mutation to backend", async () => {
    let lastPostedPayload: Record<string, unknown> | null = null;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (u.includes("/api/settings") && init?.method === "POST") {
        lastPostedPayload = JSON.parse(String(init.body));
        return new Response(
          JSON.stringify({
            status: "ok",
            settings: lastPostedPayload,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({
            running: true,
            settings: {
              island_enabled: true,
              island_notifications_enabled: true,
              island_timer_enabled: true,
              island_autohide_enabled: true,
              island_hud_duration_s: 120.0,
              island_completion_duration_s: 2.0,
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>
    );

    // 1. Click preset 1 min while enabled
    const preset1m = screen.getByRole("button", { name: "1 min" });
    fireEvent.click(preset1m);

    await waitFor(() => {
      expect(lastPostedPayload).not.toBeNull();
      expect(lastPostedPayload).toHaveProperty("island_hud_duration_s", 60);
    });

    // 2. Toggle Show Dynamic Island
    const toggleOverlay = screen.getByTestId("toggle-island-enabled");
    fireEvent.click(toggleOverlay);

    await waitFor(() => {
      expect(lastPostedPayload).toHaveProperty("island_enabled", false);
    });
  });

  it("Requirement 8: Clicking 'Test 5s Countdown' dispatches safe test to /api/control without altering power state", async () => {
    let lastPostedPayload: Record<string, unknown> | null = null;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (u.includes("/api/control") && init?.method === "POST") {
        lastPostedPayload = JSON.parse(String(init.body));
        return new Response(
          JSON.stringify({ status: "ok", action: "test_countdown", triggered: true }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>
    );

    const testBtn = screen.getByTestId("test-countdown-btn");
    expect(testBtn).toBeInTheDocument();
    expect(testBtn).toHaveTextContent("Test 5s Countdown");

    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(lastPostedPayload).toEqual({
        action: "test_countdown",
        duration: 5.0,
      });
    });
  });

  it("Requirement 9: Appearance tab has HUD simulator completely removed and focuses only on themes, colors, and motion", () => {
    render(
      <AirPointEngineProvider>
        <AppearancePage />
      </AirPointEngineProvider>
    );

    // Verify themes and colors remain
    expect(screen.getByText("Appearance themes")).toBeInTheDocument();
    expect(screen.getByText("Accent color")).toBeInTheDocument();
    expect(screen.getByText("Layout density")).toBeInTheDocument();
    expect(screen.getByText("Reduced motion")).toBeInTheDocument();

    // Verify HUD simulator and preview are completely absent from Appearance
    expect(screen.queryByText(/Dynamic Island HUD Simulator/i)).toBeNull();
    expect(screen.queryByText(/Screenshot Hold/i)).toBeNull();
    expect(screen.queryByText(/IN-APP PREVIEW ONLY/i)).toBeNull();
  });
});
