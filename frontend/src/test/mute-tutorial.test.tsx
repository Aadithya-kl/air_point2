import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { GestureTutorial } from "@/components/air-point/gesture-tutorial";
import { GesturesPage } from "@/routes/gestures";
import { OverviewPage } from "@/routes/index";
import { AirPointEngineProvider } from "@/components/air-point/engine";
import { GESTURE_SPECS } from "@/lib/air-point-model";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({ children, to, ...props }: { children: React.ReactNode; to?: string; [key: string]: unknown }) => (
      <a href={to} {...props}>
        {children}
      </a>
    ),
  };
});

describe("Mute / Unmute Animated Gesture Tutorial & Recent Activity", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("GestureTutorial: renders local GIF and 3 instructional steps for mute gesture", () => {
    render(<GestureTutorial gestureId="mute" reducedMotion={false} />);

    const gif = screen.getByTestId("mute-gesture-tutorial-gif") as HTMLImageElement;
    expect(gif).toBeInTheDocument();
    expect(gif.src).toContain("/assets/gestures/mute-unmute.gif");
    expect(gif.alt).toContain("placing index fingertip vertically against lips");

    // Check 3 instructional steps
    expect(screen.getByText(/Extend your index finger/i)).toBeInTheDocument();
    expect(screen.getByText(/vertically against your lips and hold/i)).toBeInTheDocument();
    expect(screen.getByText(/Air Point toggles system audio mute\/unmute/i)).toBeInTheDocument();
  });

  it("GestureTutorial: displays static poster frame when reduced motion is preferred", () => {
    render(<GestureTutorial gestureId="mute" reducedMotion={true} />);

    const img = screen.getByTestId("mute-gesture-tutorial-gif") as HTMLImageElement;
    expect(img).toBeInTheDocument();
    expect(img.src).toContain("/assets/gestures/mute-unmute-poster.png");
    expect(screen.getByText(/REDUCED MOTION/i)).toBeInTheDocument();
  });

  it("GestureTutorial: returns null for other gestures (only mute gets the tutorial)", () => {
    const { container: pointerContainer } = render(
      <GestureTutorial gestureId="pointer" />
    );
    expect(pointerContainer.firstChild).toBeNull();

    const { container: screenshotContainer } = render(
      <GestureTutorial gestureId="screenshot" />
    );
    expect(screenshotContainer.firstChild).toBeNull();
  });

  it("GesturesPage: displays the tutorial when Mute / Unmute is selected, and hides it for other gestures", () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Offline"));

    render(
      <AirPointEngineProvider>
        <GesturesPage />
      </AirPointEngineProvider>
    );

    // Initial selected gesture is pointer -> no tutorial GIF
    expect(screen.queryByTestId("mute-gesture-tutorial-gif")).toBeNull();

    // Click Mute / Unmute in the gesture library list
    const muteRow = screen.getByRole("button", { name: /Mute \/ unmute/i });
    act(() => {
      fireEvent.click(muteRow);
    });

    // Now Mute / Unmute tutorial GIF should be displayed
    const tutorialGif = screen.getByTestId("mute-gesture-tutorial-gif");
    expect(tutorialGif).toBeInTheDocument();

    // Click another gesture (Drag & drop) -> tutorial is removed
    const dragRow = screen.getByRole("button", { name: /Drag & drop/i });
    act(() => {
      fireEvent.click(dragRow);
    });
    expect(screen.queryByTestId("mute-gesture-tutorial-gif")).toBeNull();
  });

  it("GesturesPage: keeps all 8 gestures listed and toggle connected to backend", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        running: true,
        fps: 30,
        owner: "RIGHT",
        settings: {
          enabled: { mute: false },
        },
      }),
    } as Response);

    render(
      <AirPointEngineProvider>
        <GesturesPage />
      </AirPointEngineProvider>
    );

    // Verify all 8 gestures are rendered in library
    GESTURE_SPECS.forEach((spec) => {
      expect(
        screen.getByRole("button", { name: new RegExp(spec.name, "i") })
      ).toBeInTheDocument();
    });

    // Select Mute
    const muteRow = screen.getByRole("button", { name: /Mute \/ unmute/i });
    act(() => {
      fireEvent.click(muteRow);
    });

    // Toggle mute
    const toggleBtn = screen.getByRole("switch", { name: /Enable Mute \/ unmute/i });
    await act(async () => {
      fireEvent.click(toggleBtn);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8765/api/settings",
      expect.objectContaining({
        method: "POST",
      })
    );
  });

  it("Overview Recent Activity: displays at most three items and empty state when offline", () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Offline"));

    render(
      <AirPointEngineProvider>
        <OverviewPage />
      </AirPointEngineProvider>
    );

    // When offline and 0 events, shows empty state
    expect(screen.getByTestId("empty-recent-activity")).toBeInTheDocument();
    expect(screen.queryByTestId("recent-activity-list")).toBeNull();
  });
});
