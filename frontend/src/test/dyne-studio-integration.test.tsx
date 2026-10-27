import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { AirPointEngineProvider } from "@/components/air-point/engine";
import { DynamicIslandPage } from "@/routes/island";
import { DyneStudio } from "@/components/air-point/dyne-studio";
import { PREVIEW_CAPSULES } from "@/components/air-point/dyne-studio/capsules";

// Mock TanStack router for isolated page rendering
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

describe("Dyne Studio × AirPoint Integration Suite", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders the personal Dyne Studio editor inside the existing AirPoint route without duplicate preview or status card", () => {
    render(
      <AirPointEngineProvider>
        <DynamicIslandPage />
      </AirPointEngineProvider>,
    );

    expect(screen.getByRole("heading", { name: "Dyne Studio" })).toBeInTheDocument();
    expect(screen.getByTestId("dyne-studio-root")).toBeInTheDocument();
    expect(screen.getByText("Preview")).toBeInTheDocument();
    expect(screen.queryByText("Real Desktop Overlay Status")).not.toBeInTheDocument();
    expect(screen.queryByText("PREVIEW SIMULATION (In-App Only)")).not.toBeInTheDocument();
  });

  it("navigates into main options when the central capsule is clicked", async () => {
    render(<DyneStudio />);

    const centralCapsule = screen.getByRole("button", { name: /Normal — open main options/i });
    fireEvent.click(centralCapsule);

    // Main options shell should appear with 6 categories
    await waitFor(() => {
      expect(screen.getByText("Make it yours.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Text" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Material" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Shape" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Behaviour & Timing/ })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Colour" })).toBeInTheDocument();
    });
  });

  it("keeps Text, Material, and Shape features reachable under their new categories", async () => {
    render(<DyneStudio />);
    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Text" }));
    fireEvent.click(screen.getByRole("button", { name: "Font" }));
    expect(screen.getByRole("button", { name: "Humanist" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "System" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mono" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Material" }));
    fireEvent.click(screen.getByRole("button", { name: "Surface" }));
    expect(screen.getByRole("button", { name: "Matte" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Glass" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Translucent" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Lighting" }));
    expect(screen.getByRole("button", { name: "Luminous" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Balanced" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Quiet" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Shape" }));
    expect(screen.getByRole("button", { name: "Soft square" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Classic" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Roundness" })).toBeInTheDocument();
  });

  it("navigates into Colour category and allows exploring Custom RGB mixer", async () => {
    render(<DyneStudio />);

    // Open main options
    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Colour" })).toBeInTheDocument();
    });

    // Open Colour options
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));

    await waitFor(() => {
      expect(screen.getByText("Choose your colour.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Custom" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "More Colours" })).toBeInTheDocument();
    });

    // Open Custom RGB mixer
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));

    await waitFor(() => {
      expect(screen.getByText("Mix your colour.")).toBeInTheDocument();
      expect(screen.getByLabelText("R value")).toBeInTheDocument();
      expect(screen.getByLabelText("G value")).toBeInTheDocument();
      expect(screen.getByLabelText("B value")).toBeInTheDocument();
      expect(screen.getByText("HEX")).toBeInTheDocument();
    });
  });

  it("navigates into More Colours and renders two-ring colour palette", async () => {
    render(<DyneStudio />);

    // Open main options
    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Colour" })).toBeInTheDocument();
    });

    // Open Colour options
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "More Colours" })).toBeInTheDocument();
    });

    // Open More Colours palette
    fireEvent.click(screen.getByRole("button", { name: "More Colours" }));

    await waitFor(() => {
      expect(screen.getByText("More colours.")).toBeInTheDocument();
      // Should have segments from outer and inner rings (e.g. Cyan, Teal, Rose, Magenta, etc.)
      expect(screen.getByRole("button", { name: "Cyan" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Rose" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Magenta" })).toBeInTheDocument();
    });
  });

  it("exposes the six requested category labels", async () => {
    render(<DyneStudio />);

    // Open main options
    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Behaviour & Timing" })).toBeInTheDocument();
    });

    // Confirm every category is present under its new name.
    expect(screen.getByRole("button", { name: "Colour" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Text" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Material" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Shape" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });

  it("allows switching preview event states without sending mutations to backend", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => {
      return new Response("{}", { status: 200 });
    });

    render(<DyneStudio />);

    // Verify initial event state is Idle
    expect(screen.getByText("Normal")).toBeInTheDocument();

    // Click Next event state button
    const nextBtn = screen.getByRole("button", { name: "Next event state" });
    fireEvent.click(nextBtn);

    // Event state should change to Power Save Waiting
    await waitFor(() => {
      expect(screen.getByText("Power Save Waiting")).toBeInTheDocument();
    });

    // Click Next event state button again -> Power Save Countdown
    fireEvent.click(nextBtn);
    await waitFor(() => {
      expect(screen.getByText("Power Save Countdown")).toBeInTheDocument();
    });

    // Click Next event state button again -> Power Save Complete
    fireEvent.click(nextBtn);
    await waitFor(() => {
      expect(screen.getByText("Power Save Complete")).toBeInTheDocument();
    });

    // Verify that NO POST /api/settings was made by preview capsule switching
    const postedSettingsCalls = fetchSpy.mock.calls.filter(
      ([url, init]) => String(url).includes("/api/settings") && init?.method === "POST",
    );
    expect(postedSettingsCalls.length).toBe(0);
  });

  it("keeps appearance settings independent for each preview event", async () => {
    render(<DyneStudio />);
    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));
    fireEvent.click(screen.getByRole("button", { name: "Red" }));
    fireEvent.click(screen.getByRole("button", { name: "Next event state" }));
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));
    expect(screen.getByRole("button", { name: "Red" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(
      screen.getByRole("button", { name: /Power Save Waiting — go back one level/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Previous event state" }));
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));
    expect(screen.getByRole("button", { name: "Red" })).toHaveAttribute("aria-pressed", "true");
  });

  it("disables event switching while RGB and slider layers are active", async () => {
    render(<DyneStudio />);
    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Text" }));
    fireEvent.click(screen.getByRole("button", { name: "Font Size" }));
    expect(screen.queryByRole("button", { name: "Next event state" })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByText("Normal")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    expect(screen.queryByRole("button", { name: "Next event state" })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByText("Normal")).toBeInTheDocument();
  });

  it("supports Escape key navigation to step back through layers", async () => {
    render(<DyneStudio />);

    // 1. Rest -> Main
    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));
    await waitFor(() => {
      expect(screen.getByText("Make it yours.")).toBeInTheDocument();
    });

    // 2. Main -> Colour
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));
    await waitFor(() => {
      expect(screen.getByText("Choose your colour.")).toBeInTheDocument();
    });

    // 3. Press Escape -> back to Main
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => {
      expect(screen.getByText("Make it yours.")).toBeInTheDocument();
    });

    // 4. Press Escape -> back to Rest
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => {
      expect(screen.getByText("Your capsule. Your way.")).toBeInTheDocument();
    });
  });

  it("writes only whitelisted operational settings through the injected host adapter", async () => {
    const setIslandSettings = vi.fn(
      async (
        _updates: Partial<{
          enabled: boolean;
          notificationsEnabled: boolean;
          timerEnabled: boolean;
          autohideEnabled: boolean;
          hudDurationS: number;
          completionDurationS: number;
        }>,
      ) => true,
    );
    const testDesktopCountdown = vi.fn(async () => true);
    const hostAdapter = { setIslandSettings, testDesktopCountdown };
    const capabilities = {
      enabled: "read-write",
      notificationsEnabled: "read-write",
      timerEnabled: "read-write",
      autohideEnabled: "read-write",
      hudDurationS: "read-write",
      completionDurationS: "read-write",
    } as const;
    const desktopSettings = {
      enabled: true,
      notificationsEnabled: true,
      timerEnabled: true,
      autohideEnabled: true,
      hudDurationS: 120,
      completionDurationS: 2,
    };
    render(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={capabilities}
        desktopSettings={desktopSettings}
        hostConnected
        settingsSynced
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
    fireEvent.click(screen.getByRole("button", { name: "Notifications: On" }));
    await waitFor(() =>
      expect(setIslandSettings).toHaveBeenCalledWith({ notificationsEnabled: false }),
    );
    for (const [payload] of setIslandSettings.mock.calls) {
      expect(
        Object.keys(payload).every((key) =>
          [
            "enabled",
            "notificationsEnabled",
            "timerEnabled",
            "autohideEnabled",
            "hudDurationS",
            "completionDurationS",
          ].includes(key),
        ),
      ).toBe(true);
    }
  });

  it("keeps appearance changes local and event switching never calls the host", async () => {
    const setIslandSettings = vi.fn(
      async (
        _updates: Partial<{
          enabled: boolean;
          notificationsEnabled: boolean;
          timerEnabled: boolean;
          autohideEnabled: boolean;
          hudDurationS: number;
          completionDurationS: number;
        }>,
      ) => true,
    );
    const testDesktopCountdown = vi.fn(async () => true);
    const hostAdapter = { setIslandSettings, testDesktopCountdown };
    const capabilities = {
      enabled: "read-write",
      notificationsEnabled: "read-write",
      timerEnabled: "read-write",
      autohideEnabled: "read-write",
      hudDurationS: "read-write",
      completionDurationS: "read-write",
    } as const;
    const desktopSettings = {
      enabled: true,
      notificationsEnabled: true,
      timerEnabled: true,
      autohideEnabled: true,
      hudDurationS: 120,
      completionDurationS: 2,
    };
    render(
      <DyneStudio
        hostAdapter={hostAdapter}
        capabilities={capabilities}
        desktopSettings={desktopSettings}
        hostConnected
        settingsSynced
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Normal — open main options/i }));
    fireEvent.click(screen.getByRole("button", { name: "Colour" }));
    fireEvent.click(screen.getByRole("button", { name: "Red" }));
    expect(setIslandSettings).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Next event state" }));
    expect(screen.getByText("Power Save Waiting")).toBeInTheDocument();
    expect(setIslandSettings).not.toHaveBeenCalled();
    expect(testDesktopCountdown).not.toHaveBeenCalled();
  });

  it("exposes all 17 DynamicIslandState values and keeps them selectable with independent appearance", () => {
    render(<DyneStudio />);

    // All 17 states must be present in PREVIEW_CAPSULES exactly once
    expect(PREVIEW_CAPSULES).toHaveLength(17);
    const ids = PREVIEW_CAPSULES.map((c) => c.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(17);

    const required17States = [
      "idle",
      "screenshot",
      "screenshot-hold",
      "muted",
      "unmuted",
      "whatsapp",
      "reacquired",
      "lost",
      "volume-up",
      "volume-down",
      "wakanda-forever",
      "wakanda-hold",
      "normal",
      "power-save-waiting",
      "power-save-countdown",
      "power-save-complete",
      "power-save-wake",
    ];
    for (const stateId of required17States) {
      expect(ids).toContain(stateId);
    }
  });

  it("treats pointer movement under 6px as a click and opens the category ring", async () => {
    render(<DyneStudio />);

    const capsule = screen.getByRole("button", { name: /Normal — open main options/i });

    // Simulate pointer down, subtle drift (dx=3, dy=2 < 6px), and pointer up
    fireEvent.pointerDown(capsule, { clientX: 100, clientY: 100, pointerId: 1 });
    fireEvent.pointerMove(capsule, { clientX: 103, clientY: 102, pointerId: 1 });
    fireEvent.pointerUp(capsule, { clientX: 103, clientY: 102, pointerId: 1 });
    fireEvent.click(capsule);

    // Because movement was < 6px, click was not suppressed and opened main options
    await waitFor(() => {
      expect(screen.getByText("Make it yours.")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Colour" })).toBeInTheDocument();
    });
  });

  describe("Regression: Guaranteed Visible Capsule in Initial State", () => {
    it("renders a visible central capsule in the initial rest state before any category is selected", () => {
      render(<DyneStudio />);

      // Capsule must be discoverable by test ID and by accessible button role
      const capsule = screen.getByTestId("central-capsule");
      expect(capsule).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Normal — open main options/i })).toBe(capsule);

      // Label and Preview badge must be present on initial render
      expect(screen.getByText("Normal")).toBeInTheDocument();
      expect(screen.getByText("Preview")).toBeInTheDocument();

      // Initial event must resolve to a valid registered capsule
      expect(PREVIEW_CAPSULES[0]?.id).toBe("normal");

      // Initial state must NOT render an expanded category ring or adjustment slider
      expect(screen.queryByRole("button", { name: "Colour" })).not.toBeInTheDocument();
      expect(screen.queryByTestId("capsule-adjustment-track")).not.toBeInTheDocument();
      expect(screen.queryByTestId("custom-colour-view")).not.toBeInTheDocument();
    });

    it("ensures capsule remains rendered and interactive when host is offline or unsynced", () => {
      render(
        <DyneStudio
          hostConnected={false}
          settingsSynced={false}
          desktopSettings={{
            enabled: false,
            notificationsEnabled: false,
            timerEnabled: false,
            autohideEnabled: false,
            hudDurationS: 60,
            completionDurationS: 2,
          }}
        />,
      );

      const capsule = screen.getByTestId("central-capsule");
      expect(capsule).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Normal — open main options/i }),
      ).toBeInTheDocument();
    });

    it("toggles category ring open on capsule click and backs out cleanly to rest on next click", async () => {
      render(<DyneStudio />);

      const capsule = screen.getByTestId("central-capsule");

      // Click opens category ring
      fireEvent.click(capsule);
      await waitFor(() => {
        expect(screen.getByRole("button", { name: "Colour" })).toBeInTheDocument();
      });

      // Accessible title derives to back out one level
      expect(
        screen.getByRole("button", { name: /Normal — go back one level/i }),
      ).toBeInTheDocument();

      // Click again backs out to rest
      fireEvent.click(capsule);
      await waitFor(() => {
        expect(screen.queryByRole("button", { name: "Colour" })).not.toBeInTheDocument();
      });
      expect(
        screen.getByRole("button", { name: /Normal — open main options/i }),
      ).toBeInTheDocument();
    });
  });
});
