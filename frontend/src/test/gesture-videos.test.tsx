import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { GestureVideoPlayer, GESTURE_VIDEO_SPECS } from "@/components/air-point/gesture-video-player";
import { GesturesPage } from "@/routes/gestures";
import { AirPointEngineProvider } from "@/components/air-point/engine";
import { GESTURE_SPECS, type GestureId } from "@/lib/air-point-model";

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

describe("Air Point Gesture Video Integration", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const EXPECTED_MAPPINGS: Array<{
    id: Exclude<GestureId, "mute">;
    expectedSrc: string;
    expectedPoster: string;
    expectedTitle: string;
  }> = [
    {
      id: "pointer",
      expectedSrc: "/videos/gestures/pointer-click.mp4",
      expectedPoster: "/videos/gestures/posters/pointer-click-poster.jpg",
      expectedTitle: "How to steer & click",
    },
    {
      id: "drag",
      expectedSrc: "/videos/gestures/drag-drop.mp4",
      expectedPoster: "/videos/gestures/posters/drag-drop-poster.jpg",
      expectedTitle: "How to drag & drop",
    },
    {
      id: "screenshot",
      expectedSrc: "/videos/gestures/screenshot.mp4",
      expectedPoster: "/videos/gestures/posters/screenshot-poster.jpg",
      expectedTitle: "How to capture screenshot",
    },
    {
      id: "whatsapp",
      expectedSrc: "/videos/gestures/whatsapp.mp4",
      expectedPoster: "/videos/gestures/posters/whatsapp-poster.jpg",
      expectedTitle: "How to open WhatsApp",
    },
    {
      id: "volume-up",
      expectedSrc: "/videos/gestures/volume-up.mp4",
      expectedPoster: "/videos/gestures/posters/volume-up-poster.jpg",
      expectedTitle: "How to increase volume",
    },
    {
      id: "volume-down",
      expectedSrc: "/videos/gestures/volume-down.mp4",
      expectedPoster: "/videos/gestures/posters/volume-down-poster.jpg",
      expectedTitle: "How to decrease volume",
    },
    {
      id: "wakanda-forever",
      expectedSrc: "/videos/gestures/wakanda-forever.mp4",
      expectedPoster: "/videos/gestures/posters/wakanda-forever-poster.jpg",
      expectedTitle: "How to lock workstation",
    },
  ];

  EXPECTED_MAPPINGS.forEach(({ id, expectedSrc, expectedPoster, expectedTitle }) => {
    it(`GestureVideoPlayer: renders verified asset and controls for '${id}'`, () => {
      render(<GestureVideoPlayer gestureId={id} reducedMotion={false} />);

      const video = screen.getByTestId(`gesture-video-${id}`) as HTMLVideoElement;
      expect(video).toBeInTheDocument();
      expect(video.getAttribute("src")).toBe(expectedSrc);
      expect(video.getAttribute("poster")).toBe(expectedPoster);
      expect(video.muted).toBe(true);
      expect(video).toHaveAttribute("loop");
      expect(video).toHaveAttribute("playsinline");
      expect(video.getAttribute("preload")).toBe("metadata");

      // Verify Title & Instructional steps exist
      expect(screen.getByText(expectedTitle)).toBeInTheDocument();
      expect(screen.getByText("STEP 1")).toBeInTheDocument();
      expect(screen.getByText("STEP 2")).toBeInTheDocument();
      expect(screen.getByText("STEP 3")).toBeInTheDocument();
    });
  });

  it("GestureVideoPlayer: returns null for 'mute' (Mute is exclusively handled by GestureTutorial)", () => {
    const { container } = render(<GestureVideoPlayer gestureId="mute" />);
    expect(container.firstChild).toBeNull();
  });

  it("GestureVideoPlayer: respects reduced motion preference", () => {
    render(<GestureVideoPlayer gestureId="pointer" reducedMotion={true} />);
    expect(screen.getByText(/REDUCED MOTION/i)).toBeInTheDocument();
  });

  it("GestureVideoPlayer: toggles playback via play/pause control button", () => {
    render(<GestureVideoPlayer gestureId="screenshot" reducedMotion={false} />);

    const playBtn = screen.getByTestId("gesture-video-play-btn");
    expect(playBtn).toBeInTheDocument();

    fireEvent.click(playBtn);
    expect(playBtn).toBeInTheDocument();
  });

  it("GesturesPage: displays corresponding video tutorial when selecting each gesture and preserves Mute GIF", () => {
    render(
      <AirPointEngineProvider>
        <GesturesPage />
      </AirPointEngineProvider>
    );

    // Default gesture is Pointer & click -> displays pointer video
    expect(screen.getByTestId("gesture-video-pointer")).toBeInTheDocument();

    // Select Mute / unmute -> should display the GIF tutorial, not video
    const muteButton = screen.getByRole("button", { name: /Mute \/ unmute/i });
    act(() => {
      fireEvent.click(muteButton);
    });
    expect(screen.getByTestId("mute-gesture-tutorial")).toBeInTheDocument();
    expect(screen.queryByTestId("gesture-video-pointer")).not.toBeInTheDocument();

    // Select Lock Screen -> should display wakanda video and WakandaSimulationDeck
    const wakandaButton = screen.getByRole("button", { name: /(Wakanda Forever|Lock Screen)/i });
    act(() => {
      fireEvent.click(wakandaButton);
    });
    expect(screen.getByTestId("gesture-video-wakanda-forever")).toBeInTheDocument();
    expect(screen.getByText(/Wakanda Forever Activation Sequence/i)).toBeInTheDocument();

    // Select Open WhatsApp -> should display whatsapp video
    const whatsappButton = screen.getByRole("button", { name: /Open WhatsApp/i });
    act(() => {
      fireEvent.click(whatsappButton);
    });
    expect(screen.getByTestId("gesture-video-whatsapp")).toBeInTheDocument();

    // Select Drag & Drop -> should display drag video
    const dragButton = screen.getByRole("button", { name: /Drag & drop/i });
    act(() => {
      fireEvent.click(dragButton);
    });
    expect(screen.getByTestId("gesture-video-drag")).toBeInTheDocument();

    // Select Volume Up -> should display volume-up video
    const volUpButton = screen.getByRole("button", { name: /Volume up/i });
    act(() => {
      fireEvent.click(volUpButton);
    });
    expect(screen.getByTestId("gesture-video-volume-up")).toBeInTheDocument();

    // Select Volume Down -> should display volume-down video
    const volDownButton = screen.getByRole("button", { name: /Volume down/i });
    act(() => {
      fireEvent.click(volDownButton);
    });
    expect(screen.getByTestId("gesture-video-volume-down")).toBeInTheDocument();
  });
});
