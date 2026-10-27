import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import {
  DEFAULT_HOLD_DURATION,
  GESTURE_SPECS,
  clampHoldDuration,
  resolveCursorPreset,
  sanitizeUIPreferences,
} from "@/lib/air-point-model";
import { GestureDiagram } from "@/components/air-point/illustrations";

describe("Air Point product rules", () => {
  it("represents exactly the eight supported gestures", () => {
    expect(GESTURE_SPECS.map((gesture) => gesture.id)).toEqual([
      "pointer",
      "drag",
      "screenshot",
      "whatsapp",
      "wakanda-forever",
      "mute",
      "volume-up",
      "volume-down",
    ]);
  });

  it("defaults screenshot palm hold to 3 seconds and clamps valid settings", () => {
    expect(DEFAULT_HOLD_DURATION).toBe(3);
    expect(clampHoldDuration(0)).toBe(1);
    expect(clampHoldDuration(3)).toBe(3);
    expect(clampHoldDuration(9)).toBe(5);
  });

  it("keeps volume gestures anchored to the anatomical ears", () => {
    expect(GESTURE_SPECS.find((g) => g.id === "volume-up")?.anatomicalAnchor)
      .toContain("Right Ear");
    expect(GESTURE_SPECS.find((g) => g.id === "volume-down")?.anatomicalAnchor)
      .toContain("Left Ear");
  });

  it("resolves cursor presets and marks unmatched values custom", () => {
    expect(resolveCursorPreset(0.6, 85)).toBe("precision");
    expect(resolveCursorPreset(0.85, 65)).toBe("balanced");
    expect(resolveCursorPreset(1.5, 35)).toBe("fast");
    expect(resolveCursorPreset(1.1, 50)).toBe("custom");
  });

  it("sanitizes invalid personalization preferences", () => {
    expect(sanitizeUIPreferences({ theme: "invalid", accent: null, density: 7 })).toMatchObject({
      theme: "obsidian",
      accent: "sage",
      density: "comfortable",
      lastDarkTheme: "obsidian",
    });
  });

  it("migrates legacy 'light' and 'dark' preferences silently to 'titanium' and 'obsidian'", () => {
    const migratedLight = sanitizeUIPreferences({ theme: "light" });
    expect(migratedLight.theme).toBe("titanium");
    expect(migratedLight.lastDarkTheme).toBe("obsidian");

    const migratedDark = sanitizeUIPreferences({ theme: "dark" });
    expect(migratedDark.theme).toBe("obsidian");
    expect(migratedDark.lastDarkTheme).toBe("obsidian");
  });

  it("preserves lastDarkTheme across light mode and dark mode presets", () => {
    const oledDark = sanitizeUIPreferences({ theme: "oled", lastDarkTheme: "oled" });
    expect(oledDark.theme).toBe("oled");
    expect(oledDark.lastDarkTheme).toBe("oled");

    const slateInLight = sanitizeUIPreferences({ theme: "titanium", lastDarkTheme: "slate" });
    expect(slateInLight.theme).toBe("titanium");
    expect(slateInLight.lastDarkTheme).toBe("slate");

    const invalidLastDark = sanitizeUIPreferences({ theme: "titanium", lastDarkTheme: "invalid" });
    expect(invalidLastDark.lastDarkTheme).toBe("obsidian");
  });

  it("renders the required screenshot and WhatsApp gesture shapes", () => {
    const screenshot = render(<GestureDiagram gestureId="screenshot" />);
    expect(
      screenshot.container.querySelector('[data-gesture-shape="open-palms-thumbs-inward"]')
    ).not.toBeNull();

    const whatsapp = render(<GestureDiagram gestureId="whatsapp" />);
    expect(
      whatsapp.container.querySelector('[data-gesture-shape="two-hand-w-pose"]')
    ).not.toBeNull();
  });
});
