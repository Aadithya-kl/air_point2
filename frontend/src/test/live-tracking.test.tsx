import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import {
  LiveTrackingCanvas,
  normalizeHandPayload,
  normalizeFacePayload,
  parseCoordinatePair,
} from "@/components/air-point/live-tracking-canvas";

describe("LiveTrackingCanvas component and payload adapters", () => {
  it("renders live landmarks mode by default with SVG canvas", () => {
    const { container } = render(
      <LiveTrackingCanvas
        connected={true}
        paused={false}
        trackingStatus="Right Hand"
        pointerOwner="RIGHT"
        activeGesture="pointer"
      />
    );

    expect(screen.getByText(/TRACKING: RIGHT HAND/i)).toBeInTheDocument();
    expect(screen.getByText("Live landmarks")).toBeInTheDocument();
    expect(screen.getByText("Camera + Landmarks")).toBeInTheDocument();
    expect(screen.getByText("Camera preview")).toBeInTheDocument();

    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
    const canvasSvg = container.querySelector('[data-testid="spatial-landmarks-svg"]');
    expect(canvasSvg).toBeInTheDocument();
    expect(canvasSvg?.getAttribute("viewBox")).toBe("0 0 640 480");
  });

  it("switches to camera + landmarks overlay mode and renders both video feed and SVG overlay", () => {
    const { container } = render(
      <LiveTrackingCanvas
        connected={true}
        paused={false}
        trackingStatus="Right Hand"
        pointerOwner="RIGHT"
        activeGesture="pointer"
      />
    );

    const overlayBtn = screen.getByText("Camera + Landmarks");
    fireEvent.click(overlayBtn);

    const img = container.querySelector('img[alt*="Camera tracking"]') || container.querySelector("img");
    expect(img).toBeInTheDocument();
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
    expect(screen.getByText(/R. HAND:/i)).toBeInTheDocument();
  });

  it("switches to camera preview mode with local privacy guarantee", () => {
    render(
      <LiveTrackingCanvas
        connected={true}
        paused={false}
        trackingStatus="Both Hands"
        pointerOwner="RIGHT"
        activeGesture="idle"
      />
    );

    const cameraBtn = screen.getByText("Camera preview");
    fireEvent.click(cameraBtn);

    expect(screen.getByText(/Local device only/i)).toBeInTheDocument();
    expect(screen.getByText(/MAX 15 FPS/i)).toBeInTheDocument();
  });

  it("indicates scanning state when no hands are detected", () => {
    render(
      <LiveTrackingCanvas
        connected={true}
        paused={false}
        trackingStatus="No Hands"
        pointerOwner="NONE"
        activeGesture="idle"
      />
    );

    expect(screen.getByText("SCANNING FOR HANDS")).toBeInTheDocument();
  });

  it("renders index-fingertip target ring with concentric circles at landmark 8", async () => {
    const mockHands = {
      right: Array.from({ length: 21 }, (_, i) => ({
        x: i === 8 ? 0.45 : 0.40,
        y: i === 8 ? 0.35 : 0.50,
        z: 0.0,
      })),
      left: null,
    };

    const mockPayload = {
      timestamp: Date.now() / 1000,
      hands: mockHands,
      face: null,
      tracking: "Right Hand",
      owner: "RIGHT",
      active_gesture: "pointer",
      is_locked: true,
      click_state: "WAITING FOR RELEASE",
      last_pinch_norm: 0.35,
    };

    const originalFetch = global.fetch;
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockPayload,
    } as any);

    const { container } = render(
      <LiveTrackingCanvas
        connected={true}
        paused={false}
        trackingStatus="Right Hand"
        pointerOwner="RIGHT"
        activeGesture="pointer"
      />
    );

    // Wait for landmark polling
    await waitFor(() => {
      const ring = container.querySelector(".index-target-ring");
      expect(ring).toBeInTheDocument();
    });

    const ring = container.querySelector(".index-target-ring");
    expect(ring).toBeInTheDocument();

    // Verify concentric circles are centred at landmark 8 coordinates (0.45 * 640 = 288, 0.35 * 480 = 168)
    const circles = ring?.querySelectorAll("circle");
    expect(circles && circles.length).toBeGreaterThanOrEqual(2);
    expect(circles?.[0]?.getAttribute("cx")).toBe("288");
    expect(circles?.[0]?.getAttribute("cy")).toBe("168");

    // Verify cardinal ticks rendered in locked state
    const lines = ring?.querySelectorAll("line");
    expect(lines && lines.length).toBe(4);

    global.fetch = originalFetch;
  });

  describe("Payload Normalization Adapters", () => {
    it("safely normalizes verified Python dictionary hands shape {right: [...], left: null}", () => {
      const rightPoints = Array.from({ length: 21 }, (_, i) => ({
        x: 0.5,
        y: 0.5,
        z: 0.0,
      }));
      const pythonPayload = {
        right: rightPoints,
        left: null,
      };

      const normalized = normalizeHandPayload(pythonPayload);
      expect(normalized).toHaveLength(1);
      expect(normalized[0]?.name).toBe("RIGHT");
      expect(normalized[0]?.landmarks).toHaveLength(21);
    });

    it("safely normalizes array hand representations for dual compatibility", () => {
      const arrayPayload = [
        {
          label: "Left",
          handedness: "Left",
          landmarks: Array.from({ length: 21 }, () => ({ x: 0.3, y: 0.4 })),
        },
      ];

      const normalized = normalizeHandPayload(arrayPayload);
      expect(normalized).toHaveLength(1);
      expect(normalized[0]?.name).toBe("LEFT");
      expect(normalized[0]?.landmarks).toHaveLength(21);
    });

    it("handles null, undefined, empty, and malformed hand payloads without crashing", () => {
      expect(normalizeHandPayload(null)).toEqual([]);
      expect(normalizeHandPayload(undefined)).toEqual([]);
      expect(normalizeHandPayload({})).toEqual([]);
      expect(normalizeHandPayload({ right: null, left: null })).toEqual([]);
      expect(normalizeHandPayload({ right: "not-an-array" })).toEqual([]);
      expect(normalizeHandPayload([{ landmarks: "bad" }])).toEqual([]);
      // Short array (< 21 points)
      expect(normalizeHandPayload({ right: [{ x: 0.1, y: 0.2 }] })).toEqual([]);
    });

    it("parses coordinate tuples [x, y] from Python face landmarks", () => {
      expect(parseCoordinatePair([0.45, 0.65])).toEqual({ x: 0.45, y: 0.65 });
      expect(parseCoordinatePair([0.45, 0.65, 0.1])).toEqual({ x: 0.45, y: 0.65 });
      expect(parseCoordinatePair({ x: 0.45, y: 0.65 })).toEqual({ x: 0.45, y: 0.65 });

      // Invalid coordinates rejected without emitting NaN
      expect(parseCoordinatePair(null)).toBeNull();
      expect(parseCoordinatePair(undefined)).toBeNull();
      expect(parseCoordinatePair(["invalid", 0.5])).toBeNull();
      expect(parseCoordinatePair([NaN, 0.5])).toBeNull();
      expect(parseCoordinatePair([])).toBeNull();
      expect(parseCoordinatePair({ x: "bad", y: 0.5 })).toBeNull();
    });

    it("normalizes verified Python facial data with lip contour and ear anchor points", () => {
      const pythonFace = {
        detected: true,
        lip_center: [0.5, 0.6],
        right_ear: [0.35, 0.45],
        left_ear: [0.65, 0.45],
        mouth_width: 0.08,
        lip_contour: [
          [0.48, 0.59],
          [0.52, 0.59],
          [0.5, 0.62],
        ],
      };

      const normalized = normalizeFacePayload(pythonFace);
      expect(normalized).not.toBeNull();
      expect(normalized?.detected).toBe(true);
      expect(normalized?.lipCenter).toEqual({ x: 0.5, y: 0.6 });
      expect(normalized?.rightEar).toEqual({ x: 0.35, y: 0.45 });
      expect(normalized?.leftEar).toEqual({ x: 0.65, y: 0.45 });
      expect(normalized?.lipContour).toHaveLength(3);
      expect(normalized?.lipContour[0]).toEqual({ x: 0.48, y: 0.59 });
    });

    it("handles null or missing facial data safely", () => {
      expect(normalizeFacePayload(null)).toBeNull();
      expect(normalizeFacePayload(undefined)).toBeNull();
      expect(normalizeFacePayload({})).toBeNull();
    });
  });

  describe("Liquid Glass 3-Mode View Selector Interaction", () => {
    it("renders liquid glass selector with a single shared glider and 3 mode buttons", () => {
      const { container } = render(
        <LiveTrackingCanvas
          connected={true}
          paused={false}
          trackingStatus="Right Hand"
          pointerOwner="RIGHT"
          activeGesture="pointer"
        />
      );

      const selector = screen.getByTestId("liquid-glass-selector");
      expect(selector).toBeInTheDocument();
      expect(selector.getAttribute("role")).toBe("tablist");

      // Verify single shared glider
      const gliders = container.querySelectorAll('[data-testid="liquid-glass-glider"]');
      expect(gliders.length).toBe(1);

      // Verify 3 mode tabs
      const tabs = container.querySelectorAll(".liquid-glass-tab");
      expect(tabs.length).toBe(3);

      // Live landmarks is active by default
      const liveBtn = screen.getByRole("tab", { name: /Live landmarks/i });
      expect(liveBtn).toHaveAttribute("aria-selected", "true");
      expect(liveBtn).toHaveClass("is-active");
    });

    it("switches modes and updates active tab", () => {
      render(
        <LiveTrackingCanvas
          connected={true}
          paused={false}
          trackingStatus="Right Hand"
          pointerOwner="RIGHT"
          activeGesture="pointer"
        />
      );

      const overlayBtn = screen.getByRole("tab", { name: /Camera \+ Landmarks/i });
      fireEvent.click(overlayBtn);

      expect(overlayBtn).toHaveAttribute("aria-selected", "true");
      expect(overlayBtn).toHaveClass("is-active");

      const cameraBtn = screen.getByRole("tab", { name: /Camera preview/i });
      fireEvent.click(cameraBtn);

      expect(cameraBtn).toHaveAttribute("aria-selected", "true");
      expect(cameraBtn).toHaveClass("is-active");
    });

    it("supports keyboard arrow navigation across tablist", () => {
      render(
        <LiveTrackingCanvas
          connected={true}
          paused={false}
          trackingStatus="Right Hand"
          pointerOwner="RIGHT"
          activeGesture="pointer"
        />
      );

      const selector = screen.getByTestId("liquid-glass-selector");

      // Press ArrowRight -> moves from landmarks to overlay
      fireEvent.keyDown(selector, { key: "ArrowRight" });
      const overlayBtn = screen.getByRole("tab", { name: /Camera \+ Landmarks/i });
      expect(overlayBtn).toHaveAttribute("aria-selected", "true");

      // Press ArrowRight -> moves from overlay to camera
      fireEvent.keyDown(selector, { key: "ArrowRight" });
      const cameraBtn = screen.getByRole("tab", { name: /Camera preview/i });
      expect(cameraBtn).toHaveAttribute("aria-selected", "true");

      // Press ArrowRight -> wraps back to landmarks
      fireEvent.keyDown(selector, { key: "ArrowRight" });
      const liveBtn = screen.getByRole("tab", { name: /Live landmarks/i });
      expect(liveBtn).toHaveAttribute("aria-selected", "true");

      // Press ArrowLeft -> wraps to camera
      fireEvent.keyDown(selector, { key: "ArrowLeft" });
      expect(cameraBtn).toHaveAttribute("aria-selected", "true");
    });

    it("provides tactile compression effect on pointerdown", () => {
      const { container } = render(
        <LiveTrackingCanvas
          connected={true}
          paused={false}
          trackingStatus="Right Hand"
          pointerOwner="RIGHT"
          activeGesture="pointer"
        />
      );

      const liveBtn = screen.getByRole("tab", { name: /Live landmarks/i });
      const glider = container.querySelector('[data-testid="liquid-glass-glider"]');

      // Pointer down triggers compression state
      fireEvent.pointerDown(liveBtn);
      expect(liveBtn).toHaveClass("is-pressed");
      expect(glider).toHaveClass("is-pressed");

      // Pointer up releases compression
      fireEvent.pointerUp(liveBtn);
      expect(liveBtn).not.toHaveClass("is-pressed");
      expect(glider).not.toHaveClass("is-pressed");
    });

    it("respects reducedMotion prop by applying no-transition class to the glider", () => {
      const { container } = render(
        <LiveTrackingCanvas
          connected={true}
          paused={false}
          trackingStatus="Right Hand"
          pointerOwner="RIGHT"
          activeGesture="pointer"
          reducedMotion={true}
        />
      );

      const glider = container.querySelector('[data-testid="liquid-glass-glider"]');
      expect(glider).toHaveClass("no-transition");
    });
  });
});
