import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { createRouter, rootRouteId } from "@tanstack/react-router";
import { routeTree } from "@/routeTree.gen";
import { AirPointEngineProvider } from "@/components/air-point/engine";
import { DesktopShell } from "@/components/air-point/shell";
import { DynamicIslandPage } from "@/routes/island";
import { AppearancePage } from "@/routes/appearance";
import { AboutPage } from "@/routes/about";

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

const HOST_SETTINGS = {
  island_enabled: true,
  island_notifications_enabled: true,
  island_timer_enabled: true,
  island_autohide_enabled: true,
  island_hud_duration_s: 120,
  island_completion_duration_s: 2,
};

type LoggedRequest = { url: string; method: string; payload?: Record<string, unknown> | undefined };
function mockConnectedBridge() {
  const requests: LoggedRequest[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    const href = String(url);
    const method = String(init?.method ?? "GET");
    const payload = init?.body
      ? (JSON.parse(String(init.body)) as Record<string, unknown>)
      : undefined;
    requests.push({ url: href, method, payload });
    if (href.includes("/api/status")) {
      return new Response(
        JSON.stringify({ running: true, power_state: "NORMAL", settings: HOST_SETTINGS }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }
    if (href.includes("/api/settings") && method === "POST") {
      return new Response(JSON.stringify({ status: "ok", settings: payload ?? {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (href.includes("/api/control") && method === "POST") {
      return new Response(
        JSON.stringify({ status: "ok", action: "test_countdown", triggered: true }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }
    return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  });
  return requests;
}

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

  it("Requirement 2: DesktopShell renders Dyne nav item alongside other tabs", () => {
    render(
      <AirPointEngineProvider>
        <DesktopShell>
          <div>Island Content</div>
        </DesktopShell>
      </AirPointEngineProvider>,
    );

    // Verify all primary navigation items are present
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Gestures")).toBeInTheDocument();
    expect(screen.getByText("Cursor & Controls")).toBeInTheDocument();
    expect(screen.getAllByText("Dyne").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Appearance")).toBeInTheDocument();
    expect(screen.getByText("About Air Point")).toBeInTheDocument();

    // Verify Dyne link points to /island
    const islandLink = screen.getByRole("link", { name: /Dyne/i });
    expect(islandLink).toHaveAttribute("data-to", "/island");
  });

  it("Requirement 3: Distinguishes simulated preview clearly from real desktop overlay status", () => {
    const { unmount } = render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>,
    );

    // /island renders only Dyne Studio and no duplicate simulation or status card
    expect(screen.queryByText("PREVIEW SIMULATION (In-App Only)")).not.toBeInTheDocument();
    expect(screen.queryByText("Real Desktop Overlay Status")).not.toBeInTheDocument();
    unmount();

    // The truthful desktop status is relocated to the About page
    render(
      <AirPointEngineProvider>
        <AboutPage />
      </AirPointEngineProvider>,
    );
    expect(screen.getByText("Real Desktop Overlay Status")).toBeInTheDocument();
    expect(screen.getByText("HOST OFFLINE · SETTINGS UNSYNCED")).toBeInTheDocument();
    expect(screen.getByText("UNSYNCED")).toBeInTheDocument();
  });

  it("Requirement 4: exposes operational controls under Notifications and Behaviour & Timing", async () => {
    mockConnectedBridge();
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>,
    );
    await waitFor(() => expect(screen.getByText("HOST CONNECTED")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /(Normal|Idle) — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
    expect(screen.getByRole("button", { name: "Notifications: On" })).toBeEnabled();
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Behaviour & Timing" }));
    expect(screen.getByRole("button", { name: "Show HUD: On" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Countdown badge: On" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Auto-hide: On" })).toBeEnabled();
  });

  it("Requirement 5: keeps host duration controls within their specified ranges", async () => {
    mockConnectedBridge();
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>,
    );
    await waitFor(() => expect(screen.getByText("HOST CONNECTED")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /(Normal|Idle) — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Behaviour & Timing" }));
    const hudDuration = screen.getByRole("slider", { name: "HUD duration" });
    expect(hudDuration).toHaveAttribute("min", "10");
    expect(hudDuration).toHaveAttribute("max", "1800");
    expect(hudDuration).toHaveAttribute("step", "10");
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
    const completionDuration = screen.getByRole("slider", { name: "Completion-message duration" });
    expect(completionDuration).toHaveAttribute("min", "1");
    expect(completionDuration).toHaveAttribute("max", "5");
    expect(completionDuration).toHaveAttribute("step", "0.5");
  });

  it("Requirement 6: Dyne Studio event selector allows previewing and cycling through lifecycle events", async () => {
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>,
    );

    // Initial state is Normal
    expect(screen.getByRole("button", { name: /Normal — open main options/i })).toBeInTheDocument();

    // Next event state -> Power Save Waiting
    fireEvent.click(screen.getByRole("button", { name: "Next event state" }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Power Save Waiting — open main options/i }),
      ).toBeInTheDocument();
    });

    // Next event state -> Power Save Countdown
    fireEvent.click(screen.getByRole("button", { name: "Next event state" }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Power Save Countdown — open main options/i }),
      ).toBeInTheDocument();
    });

    // Next event state -> Power Save Complete
    fireEvent.click(screen.getByRole("button", { name: "Next event state" }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Power Save Complete — open main options/i }),
      ).toBeInTheDocument();
    });

    // Next event state -> Hand Detected / Wake
    fireEvent.click(screen.getByRole("button", { name: "Next event state" }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Hand Detected \/ Wake — open main options/i }),
      ).toBeInTheDocument();
    });
  });

  it("Requirement 7: operational duration changes use only the existing settings bridge", async () => {
    const requests = mockConnectedBridge();
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>,
    );
    await waitFor(() => expect(screen.getByText("HOST CONNECTED")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /(Normal|Idle) — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Behaviour & Timing" }));
    fireEvent.change(screen.getByRole("slider", { name: "HUD duration" }), {
      target: { value: "300" },
    });
    await waitFor(() =>
      expect(
        requests.some(
          (request) =>
            request.url.includes("/api/settings") &&
            request.payload?.["island_hud_duration_s"] === 300,
        ),
      ).toBe(true),
    );
  });

  it("Requirement 8: test countdown uses the existing one-shot host action", async () => {
    const requests = mockConnectedBridge();
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>,
    );
    await waitFor(() => expect(screen.getByText("HOST CONNECTED")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /(Normal|Idle) — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Behaviour & Timing" }));
    fireEvent.click(screen.getByRole("button", { name: "Test countdown" }));
    await waitFor(() =>
      expect(
        requests.some(
          (request) =>
            request.url.includes("/api/control") &&
            request.method === "POST" &&
            request.payload?.["action"] === "test_countdown" &&
            request.payload?.["duration"] === 5,
        ),
      ).toBe(true),
    );
  });

  it("keeps appearance changes local and never writes them to the host", async () => {
    const requests = mockConnectedBridge();
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>,
    );
    await waitFor(() => expect(screen.getByText("HOST CONNECTED")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /(Normal|Idle) — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));
    fireEvent.click(screen.getByRole("button", { name: "Red" }));
    expect(
      requests.some(
        (request) => request.url.includes("/api/settings") && request.method === "POST",
      ),
    ).toBe(false);
  });

  it("Requirement 9: Appearance tab has HUD simulator completely removed and focuses only on themes, colors, and motion", () => {
    render(
      <AirPointEngineProvider>
        <AppearancePage />
      </AirPointEngineProvider>,
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
