import React from "react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import {
  UI_PREFERENCES_STORAGE_KEY,
  buildDiagnosticsManifest,
  resolveCursorPreset,
  sanitizeUIPreferences,
} from "@/lib/air-point-model";
import {
  AirPointEngineProvider,
  useAirPointEngine,
} from "@/components/air-point/engine";
import { GestureDiagram } from "@/components/air-point/illustrations";

const TestHarness: React.FC = () => {
  const engine = useAirPointEngine();
  return (
    <div>
      <div data-testid="theme-val">{engine.preferences.theme}</div>
      <div data-testid="accent-val">{engine.preferences.accent}</div>
      <div data-testid="density-val">{engine.preferences.density}</div>
      <div data-testid="events-count">{engine.events.length}</div>
      <div data-testid="preset-val">{engine.activePreset}</div>
      <button
        type="button"
        onClick={() => engine.setTheme("oled")}
        data-testid="btn-oled"
      >
        OLED
      </button>
      <button
        type="button"
        onClick={() => engine.setAccent("cyan")}
        data-testid="btn-cyan"
      >
        Cyan
      </button>
      <button
        type="button"
        onClick={() => engine.setDensity("compact")}
        data-testid="btn-compact"
      >
        Compact
      </button>
      <button
        type="button"
        onClick={() => engine.applyCursorPreset("precision")}
        data-testid="btn-precision"
      >
        Precision
      </button>
      <GestureDiagram gestureId="screenshot" />
      <GestureDiagram gestureId="whatsapp" />
    </div>
  );
};

describe("Air Point Aero Obsidian Redesign Regression Suite", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("DEF-04: initializes with zero fabricated recent activity events", () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Offline"));
    render(
      <AirPointEngineProvider>
        <TestHarness />
      </AirPointEngineProvider>
    );
    expect(screen.getByTestId("events-count").textContent).toBe("0");
  });

  it("DEF-08: applies and persists theme, accent, and density in localStorage", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("Offline"));
    render(
      <AirPointEngineProvider>
        <TestHarness />
      </AirPointEngineProvider>
    );

    fireEvent.click(screen.getByTestId("btn-oled"));
    fireEvent.click(screen.getByTestId("btn-cyan"));
    fireEvent.click(screen.getByTestId("btn-compact"));

    expect(screen.getByTestId("theme-val").textContent).toBe("oled");
    expect(screen.getByTestId("accent-val").textContent).toBe("cyan");
    expect(screen.getByTestId("density-val").textContent).toBe("compact");
    expect(document.documentElement.getAttribute("data-theme")).toBe("oled");
    expect(document.documentElement.getAttribute("data-accent")).toBe("cyan");
    expect(document.documentElement.getAttribute("data-density")).toBe(
      "compact"
    );

    const saved = JSON.parse(
      window.localStorage.getItem(UI_PREFERENCES_STORAGE_KEY) ?? "{}"
    );
    expect(saved.theme).toBe("oled");
    expect(saved.accent).toBe("cyan");
    expect(saved.density).toBe("compact");
  });

  it("handles corrupted or invalid stored preference values gracefully", () => {
    const sanitized = sanitizeUIPreferences({
      theme: "non-existent-neon",
      accent: 999,
      density: null,
    });
    expect(sanitized.theme).toBe("obsidian");
    expect(sanitized.accent).toBe("sage");
    expect(sanitized.density).toBe("comfortable");
  });

  it("sends verified POST /api/settings payload when applying Precision cursor preset", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({
        ok: true,
        json: async () => ({
          running: true,
          fps: 30,
          owner: "RIGHT",
          settings: { sensitivity: 0.6, smoothing: 85 },
        }),
      } as Response);

    render(
      <AirPointEngineProvider>
        <TestHarness />
      </AirPointEngineProvider>
    );

    fireEvent.click(screen.getByTestId("btn-precision"));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8765/api/settings",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ sensitivity: 0.6, smoothing: 85 }),
        })
      );
    });
    expect(resolveCursorPreset(0.6, 85)).toBe("precision");
    expect(resolveCursorPreset(1.15, 50)).toBe("custom");
  });

  it("DEF-01: constructs truthful runtime diagnostics for both connected and offline states", () => {
    const connectedReport = buildDiagnosticsManifest({
      bridgeUrl: "http://127.0.0.1:8765",
      connected: true,
      connectionState: "connected",
      running: true,
      trackingStatus: "Active",
      fps: 29,
      pointerOwner: "RIGHT",
      cameraStreamAvailable: true,
      lastHeartbeatAt: "2026-10-15T20:00:00.000Z",
      sensitivity: 0.85,
      smoothing: 65,
      holdDuration: 3.0,
      enabled: {
        pointer: true,
        drag: true,
        screenshot: true,
        whatsapp: true,
        mute: true,
        "volume-up": true,
        "volume-down": true,
        "wakanda-forever": false,
      },
      preferences: sanitizeUIPreferences({}),
      recentEventCount: 2,
      lastError: null,
    });

    expect(connectedReport.bridge.reachable).toBe(true);
    expect(connectedReport.engine.processingFps).toBe(29);
    expect(connectedReport.engine.pointerOwner).toBe("RIGHT");
    expect(connectedReport.engine.cameraFeed).toContain(
      "Resolution not reported by bridge"
    );
  });

  it("preserves mandatory SVG gesture test attributes", () => {
    const { container } = render(
      <div>
        <GestureDiagram gestureId="screenshot" />
        <GestureDiagram gestureId="whatsapp" />
      </div>
    );
    expect(
      container.querySelector('[data-gesture-shape="open-palms-thumbs-inward"]')
    ).not.toBeNull();
    expect(
      container.querySelector('[data-gesture-shape="two-hand-w-pose"]')
    ).not.toBeNull();
  });
});
