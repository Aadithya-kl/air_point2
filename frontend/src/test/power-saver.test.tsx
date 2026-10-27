import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import {
  AirPointEngineProvider,
  useAirPointEngine,
} from "@/components/air-point/engine";
import { DesktopShell } from "@/components/air-point/shell";
import { OverviewPage } from "@/routes/index";

// Mock TanStack router for isolated rendering
vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({ children, to, ...props }: { children: React.ReactNode; to?: string; [key: string]: unknown }) => (
      <a href={to || "#"} {...props}>
        {children}
      </a>
    ),
    useRouterState: () => ({ location: { pathname: "/" } }),
  };
});

describe("Air Point Power Saver Control & Synchronization Suite", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("Requirement 1: defaults to OFF (Normal Mode) on launch", async () => {
    let capturedContext: ReturnType<typeof useAirPointEngine> | null = null;
    const TestConsumer = () => {
      capturedContext = useAirPointEngine();
      return <div>Power Save: {capturedContext.powerSave ? "ON" : "OFF"} | Mode: {capturedContext.powerState}</div>;
    };

    render(
      <AirPointEngineProvider>
        <TestConsumer />
      </AirPointEngineProvider>
    );

    expect(capturedContext).not.toBeNull();
    expect(capturedContext!.powerSave).toBe(false);
    expect(capturedContext!.powerState).toBe("NORMAL");
    expect(screen.getByText(/Power Save: OFF \| Mode: NORMAL/i)).toBeInTheDocument();
  });

  it("Requirement 2: sidebar shell renders Power Saver toggle and operating mode badge", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({
            running: true,
            tracking: "Active",
            fps: 30,
            owner: "NONE",
            power_state: "NORMAL",
            settings: { power_save: false },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>App content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    const toggle = await screen.findByRole("switch", { name: /Toggle Power Saver mode/i });
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveAttribute("data-state", "unchecked");
    expect(screen.getByText("Power Saver")).toBeInTheDocument();
    expect(screen.getByText("Normal (Full rate)")).toBeInTheDocument();
  });

  it("Requirement 3: toggling Power Saver ON dispatches POST /api/settings with power_save: true", async () => {
    let capturedPayload: unknown = null;

    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({
            running: true,
            tracking: "Active",
            fps: 30,
            owner: "NONE",
            power_state: "NORMAL",
            settings: { power_save: false },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (u.includes("/api/settings") && init?.method === "POST") {
        capturedPayload = JSON.parse(String(init.body));
        return new Response(
          JSON.stringify({
            status: "ok",
            settings: { power_save: true },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>App content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    const toggle = await screen.findByRole("switch", { name: /Toggle Power Saver mode/i });
    await act(async () => {
      fireEvent.click(toggle);
    });

    expect(capturedPayload).toEqual({ power_save: true });
    await waitFor(() => {
      expect(toggle).toHaveAttribute("data-state", "checked");
    });
  });

  it("Requirement 4: Overview page displays Power Management card with operating mode indicator", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({
            running: true,
            tracking: "Active",
            fps: 30,
            owner: "NONE",
            power_state: "POWER_SAVE",
            settings: { power_save: true },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <OverviewPage />
      </AirPointEngineProvider>
    );

    expect(await screen.findByText("POWER MANAGEMENT")).toBeInTheDocument();
    expect(screen.getByText("Power Saver Active")).toBeInTheDocument();
    expect(screen.getByText("Idle Cadence (2 Hz)")).toBeInTheDocument();
  });

  it("Requirement 5: toggle is disabled when Python bridge is disconnected or engine is stopped", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({
            running: false,
            tracking: "Stopped",
            fps: 0,
            owner: "NONE",
            power_state: "NORMAL",
            settings: { power_save: false },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>App content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    const toggle = await screen.findByRole("switch", { name: /Toggle Power Saver mode/i });
    expect(toggle).toBeDisabled();
  });
});
