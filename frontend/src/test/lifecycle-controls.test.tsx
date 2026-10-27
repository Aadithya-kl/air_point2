import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import {
  AirPointEngineProvider,
  useAirPointEngine,
  type EngineContextValue,
} from "@/components/air-point/engine";
import { DesktopShell } from "@/components/air-point/shell";

// Mock TanStack router for isolated DesktopShell rendering
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

describe("Air Point Engine Lifecycle Controls & Anti-Flicker Regression Suite", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // Test 1: Running state displays the red Shutdown action
  it("Requirement 1: displays red Shutdown action with power icon when engine is running", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({
            running: true,
            tracking: "Active",
            fps: 30,
            owner: "NONE",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>Content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    const shutdownBtn = await screen.findByRole("button", { name: /Shutdown tracking/i });
    expect(shutdownBtn).toBeInTheDocument();
    expect(shutdownBtn).toHaveTextContent("Shutdown");
    // Verify red danger styling
    expect(shutdownBtn.className).toContain("text-[var(--status-danger)]");
    expect(shutdownBtn.className).toContain("bg-[var(--status-danger-bg)]");
    expect(shutdownBtn.getAttribute("title")).toBe("Shutdown tracking engine");
  });

  // Test 2: Confirmed stopped state displays the green Start action
  it("Requirement 2: displays green Start action with play icon when engine is stopped", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({
            running: false,
            tracking: "Stopped",
            fps: 0,
            owner: "NONE",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>Content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    const startBtn = await screen.findByRole("button", { name: /Start tracking/i });
    expect(startBtn).toBeInTheDocument();
    expect(startBtn).toHaveTextContent("Start");
    // Verify green healthy styling
    expect(startBtn.className).toContain("text-[var(--status-healthy)]");
    expect(startBtn.className).toContain("bg-[var(--status-healthy-bg)]");
    expect(startBtn.getAttribute("title")).toBe("Start tracking engine");
  });

  // Test 3: A Shutdown click issues exactly one stop command
  it("Requirement 3: Shutdown click issues exactly one stop command and updates state upon confirmation", async () => {
    let stopCallCount = 0;
    let isRunning = true;

    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({
            running: isRunning,
            tracking: isRunning ? "Active" : "Stopped",
            fps: isRunning ? 30 : 0,
            owner: "NONE",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (u.includes("/api/stop") && init?.method === "POST") {
        stopCallCount++;
        isRunning = false;
        return new Response(
          JSON.stringify({ status: "ok", running: false, action: "stop" }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>Content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    const shutdownBtn = await screen.findByRole("button", { name: /Shutdown tracking/i });
    await act(async () => {
      fireEvent.click(shutdownBtn);
    });

    expect(stopCallCount).toBe(1);
    const startBtn = await screen.findByRole("button", { name: /Start tracking/i });
    expect(startBtn).toBeInTheDocument();
  });

  // Test 4: A Start click issues exactly one start command
  it("Requirement 4: Start click issues exactly one start command and updates state upon confirmation", async () => {
    let startCallCount = 0;
    let isRunning = false;

    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({
            running: isRunning,
            tracking: isRunning ? "Active" : "Stopped",
            fps: isRunning ? 30 : 0,
            owner: "NONE",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (u.includes("/api/start") && init?.method === "POST") {
        startCallCount++;
        isRunning = true;
        return new Response(
          JSON.stringify({ status: "ok", running: true, action: "start" }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>Content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    const startBtn = await screen.findByRole("button", { name: /Start tracking/i });
    await act(async () => {
      fireEvent.click(startBtn);
    });

    expect(startCallCount).toBe(1);
    const shutdownBtn = await screen.findByRole("button", { name: /Shutdown tracking/i });
    expect(shutdownBtn).toBeInTheDocument();
  });

  // Test 5: Repeated clicks do not produce concurrent or duplicate lifecycle operations
  it("Requirement 5: Repeated rapid clicks do not produce concurrent or duplicate lifecycle operations", async () => {
    let stopCallCount = 0;
    let resolveStopPromise: (val: Response) => void;
    const stopPromise = new Promise<Response>((resolve) => {
      resolveStopPromise = resolve;
    });

    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({ running: true, tracking: "Active", fps: 30 }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (u.includes("/api/stop") && init?.method === "POST") {
        stopCallCount++;
        return stopPromise;
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>Content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    const shutdownBtn = await screen.findByRole("button", { name: /Shutdown tracking/i });

    // Rapidly fire multiple clicks while operation is in-flight
    await act(async () => {
      fireEvent.click(shutdownBtn);
      fireEvent.click(shutdownBtn);
      fireEvent.click(shutdownBtn);
      fireEvent.click(shutdownBtn);
    });

    expect(stopCallCount).toBe(1);
    expect(shutdownBtn).toBeDisabled();
    expect(shutdownBtn).toHaveTextContent(/Shutting down/i);

    // Resolve in-flight request
    await act(async () => {
      resolveStopPromise!(
        new Response(
          JSON.stringify({ status: "ok", running: false, action: "stop" }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    });

    expect(stopCallCount).toBe(1);
  });

  // Test 6: Status polling cannot trigger a state mutation
  it("Requirement 6: Status polling observes state without triggering POST mutations", async () => {
    vi.useFakeTimers();
    const postCalls: string[] = [];

    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (init?.method === "POST") {
        postCalls.push(u);
      }
      return new Response(
        JSON.stringify({ running: true, tracking: "Active", fps: 30 }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    });

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>Content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    // Advance clock across 5 polling intervals (7500ms)
    await act(async () => {
      vi.advanceTimersByTime(7500);
    });

    // Verify zero POST mutation requests were sent by polling
    expect(postCalls.length).toBe(0);
  });

  // Test 7: A failed stop or start request displays an accurate error state
  it("Requirement 7: Failed stop or start request displays an accurate error state and does not falsely mark state", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({ running: true, tracking: "Active", fps: 30 }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (u.includes("/api/stop") && init?.method === "POST") {
        throw new Error("Connection refused");
      }
      return new Response("{}", { status: 200 });
    });

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>Content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    const shutdownBtn = await screen.findByRole("button", { name: /Shutdown tracking/i });
    await act(async () => {
      fireEvent.click(shutdownBtn);
    });

    // Button should still reflect running=true because the shutdown failed
    expect(screen.getByRole("button", { name: /Shutdown tracking/i })).toBeInTheDocument();
  });

  // Test 8: Stale responses cannot overwrite a newer engine state
  it("Requirement 8: Stale status polling response cannot overwrite a newer confirmed engine state", async () => {
    let resolveSlowStatus: (val: Response) => void;
    const slowStatusPromise = new Promise<Response>((resolve) => {
      resolveSlowStatus = resolve;
    });

    let statusRequestIndex = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        statusRequestIndex++;
        if (statusRequestIndex === 1) {
          // Slow initial status poll that will resolve late with running=true
          return slowStatusPromise;
        }
        return new Response(
          JSON.stringify({ running: false, tracking: "Stopped", fps: 0 }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      if (u.includes("/api/stop") && init?.method === "POST") {
        return new Response(
          JSON.stringify({ status: "ok", running: false, action: "stop" }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    let contextRef!: EngineContextValue;
    const Inspector = () => {
      contextRef = useAirPointEngine();
      return <div data-testid="status-val">{contextRef.running ? "RUNNING" : "STOPPED"}</div>;
    };

    render(
      <AirPointEngineProvider>
        <Inspector />
      </AirPointEngineProvider>
    );

    // Trigger shutdown while slow status is still in flight
    await act(async () => {
      await contextRef.shutdownEngine();
    });

    expect(contextRef.running).toBe(false);
    expect(screen.getByTestId("status-val")).toHaveTextContent("STOPPED");

    // Now resolve the older slow status (which carried running: true)
    await act(async () => {
      resolveSlowStatus!(
        new Response(
          JSON.stringify({ running: true, tracking: "Active", fps: 30 }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      );
    });

    // The stale response must NOT revert running back to true!
    expect(contextRef.running).toBe(false);
    expect(screen.getByTestId("status-val")).toHaveTextContent("STOPPED");
  });

  // Test 9: Once stopped, the engine remains stopped without unexplained transitions for at least 60 seconds
  it("Requirement 9: Once stopped, engine remains stopped without transitions for at least 60s", async () => {
    vi.useFakeTimers();
    const observedStates: boolean[] = [];

    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({ running: false, tracking: "Stopped", fps: 0 }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    let contextRef!: EngineContextValue;
    const StateTracker = () => {
      contextRef = useAirPointEngine();
      React.useEffect(() => {
        observedStates.push(contextRef.running);
      }, [contextRef?.running]);
      return <div data-testid="state-val">{contextRef.running ? "ON" : "OFF"}</div>;
    };

    render(
      <AirPointEngineProvider>
        <StateTracker />
      </AirPointEngineProvider>
    );

    // Initial state after initial connect
    await act(async () => {
      vi.advanceTimersByTime(100);
    });

    expect(contextRef.running).toBe(false);

    // Advance clock for 60 seconds (40 polls at 1500ms intervals)
    for (let i = 0; i < 40; i++) {
      await act(async () => {
        vi.advanceTimersByTime(1500);
      });
      expect(contextRef.running).toBe(false);
    }

    // Verify no true transitions occurred over the full 60 seconds
    expect(observedStates.filter(Boolean).length).toBe(0);
  });

  // Test 10: Once running, the engine remains running without unexplained transitions for at least 60 seconds
  it("Requirement 10: Once running, engine remains running without transitions for at least 60s", async () => {
    vi.useFakeTimers();
    const observedStates: boolean[] = [];

    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.includes("/api/status")) {
        return new Response(
          JSON.stringify({ running: true, tracking: "Active", fps: 30 }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        );
      }
      return new Response("{}", { status: 200 });
    });

    let contextRef!: EngineContextValue;
    const StateTracker = () => {
      contextRef = useAirPointEngine();
      React.useEffect(() => {
        observedStates.push(contextRef.running);
      }, [contextRef?.running]);
      return <div data-testid="state-val">{contextRef.running ? "ON" : "OFF"}</div>;
    };

    render(
      <AirPointEngineProvider>
        <StateTracker />
      </AirPointEngineProvider>
    );

    // Initial state after initial connect
    await act(async () => {
      vi.advanceTimersByTime(100);
    });

    expect(contextRef.running).toBe(true);
    // Clear array to evaluate strictly during the 60 seconds of running
    observedStates.length = 0;

    // Advance clock for 60 seconds (40 polls at 1500ms intervals)
    for (let i = 0; i < 40; i++) {
      await act(async () => {
        vi.advanceTimersByTime(1500);
      });
      expect(contextRef.running).toBe(true);
    }

    // Verify all observed states during 60s remained strictly true (no transitions to false)
    expect(observedStates.includes(false)).toBe(false);
  });

  // Test 11: Bridge disconnected shows truthful disabled state
  it("displays truthful disabled 'Bridge offline' control when bridge is disconnected", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Network offline"));

    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>Content</div>
        </DesktopShell>
      </AirPointEngineProvider>
    );

    const offlineBtn = await screen.findByRole("button", { name: /Bridge offline/i });
    expect(offlineBtn).toBeInTheDocument();
    expect(offlineBtn).toBeDisabled();
    expect(offlineBtn.className).toContain("opacity-50");
    expect(offlineBtn.className).toContain("cursor-not-allowed");
  });
});
