import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import React from "react";
import { AirPointEngineProvider } from "@/components/air-point/engine";
import { OverviewPage } from "@/routes/index";
import { GesturesPage } from "@/routes/gestures";
import { AboutPage } from "@/routes/about";
import { AppearancePage } from "@/routes/appearance";
import { GestureVideoPlayer } from "@/components/air-point/gesture-video-player";

// Mock TanStack Link for isolated route component tests
vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({ children, to, ...props }: { children: React.ReactNode; to?: string; [key: string]: unknown }) => (
      <a href={to || "#"} {...props}>
        {children}
      </a>
    ),
  };
});

describe("Air Point UI Polish Correction Pass", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-accent");
    document.documentElement.removeAttribute("data-theme");
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  describe("Issue 1: Wakanda Forever tile consistency in Overview", () => {
    it("renders Wakanda Forever with the exact same gesture-glass-tile structure and standard toggle as other tiles", () => {
      const { container } = render(
        <AirPointEngineProvider>
          <OverviewPage />
        </AirPointEngineProvider>
      );

      // Verify all 8 tiles are rendered with .gesture-glass-tile
      const tiles = container.querySelectorAll(".gesture-glass-tile");
      expect(tiles.length).toBe(8);

      // Find Lock Screen tile
      const lockScreenHeading = screen.getByText(/(Lock Screen|Wakanda Forever)/i);
      const lockScreenTile = lockScreenHeading.closest(".gesture-glass-tile");
      expect(lockScreenTile).not.toBeNull();

      // Ensure no nested awkward WakandaCapsule inside the Overview tile
      expect(lockScreenTile?.querySelector('[data-testid="wakanda-capsule"]')).toBeNull();

      // Ensure standard toggle button exists inside the tile
      const toggle = lockScreenTile?.querySelector('button[role="switch"]');
      expect(toggle).not.toBeNull();
      expect(toggle?.getAttribute("aria-label")).toMatch(/(Lock Screen|Wakanda Forever)/i);
    });
  });

  describe("Issue 2: Gesture Library row alignment", () => {
    it("renders all gesture rows with consistent row-status-text and tile-icon structure", () => {
      const { container } = render(
        <AirPointEngineProvider>
          <GesturesPage />
        </AirPointEngineProvider>
      );

      const statusLabels = container.querySelectorAll(".row-status-text");
      expect(statusLabels.length).toBe(8);

      const tileIcons = container.querySelectorAll(".tile-icon");
      expect(tileIcons.length).toBe(8);
    });
  });

  describe("Issue 3: Simplified About Page with Collapsed Advanced Diagnostics", () => {
    it("renders user-friendly overview by default with version badge and truthful connection status", () => {
      render(
        <AirPointEngineProvider>
          <AboutPage />
        </AirPointEngineProvider>
      );

      // Header & Badge
      expect(screen.getByText("About Air Point")).toBeInTheDocument();
      expect(screen.getByTestId("version-badge")).toHaveTextContent("v1.0.0");

      // User-friendly plain language card
      expect(screen.getByText("Air Point Control Center")).toBeInTheDocument();
      expect(screen.getByText(/standard webcam into a touchless/i)).toBeInTheDocument();

      // Truthful connection status
      expect(screen.getByTestId("about-connection-badge")).toBeInTheDocument();
      expect(screen.getByText(/Offline · Local preview mode|Connected · 127.0.0.1:8765/i)).toBeInTheDocument();

      // Helpful guidance & links
      expect(screen.getByText(/Quick Setup & Best Practices/i)).toBeInTheDocument();
      expect(screen.getByText(/Explore Gesture Library/i)).toBeInTheDocument();
      expect(screen.getByText(/GitHub Repository/i)).toBeInTheDocument();
      expect(screen.getByText(/MIT License/i)).toBeInTheDocument();
    });

    it("keeps raw diagnostics manifest and developer specs inside a collapsed <details> disclosure", () => {
      const { container } = render(
        <AirPointEngineProvider>
          <AboutPage />
        </AirPointEngineProvider>
      );

      const details = container.querySelector('details[data-testid="advanced-diagnostics-details"]');
      expect(details).not.toBeNull();
      // Should be collapsed by default (not open)
      expect(details).not.toHaveAttribute("open");

      // Verify diagnostics manifest and copy button are present inside disclosure
      expect(screen.getByTestId("diagnostics-manifest-preview")).toBeInTheDocument();
      expect(screen.getByTestId("copy-diagnostics-button")).toBeInTheDocument();
    });
  });

  describe("Issue 4: Persistent Muted badge removal from tutorials", () => {
    it("does not render the persistent Muted badge across tutorial video players", () => {
      const { container } = render(
        <GestureVideoPlayer gestureId="pointer" reducedMotion={false} />
      );

      // Verify .gesture-video-mute-tag is absent
      expect(container.querySelector(".gesture-video-mute-tag")).toBeNull();
      expect(screen.queryByText("Muted")).toBeNull();

      // Verify the HTML5 video element itself remains muted for autoplay policy
      const video = screen.getByTestId("gesture-video-pointer") as HTMLVideoElement;
      expect(video.muted).toBe(true);
    });
  });

  describe("Issue 5: Accent Color Switching (Cyber Sage vs Amethyst Violet)", () => {
    it("updates document data-accent attribute distinctly when switching accents", () => {
      render(
        <AirPointEngineProvider>
          <AppearancePage />
        </AirPointEngineProvider>
      );

      // Click Cyber Sage accent card
      const sageCard = screen.getByTestId("accent-card-sage");
      act(() => {
        fireEvent.click(sageCard);
      });
      expect(document.documentElement.getAttribute("data-accent")).toBe("sage");

      // Click Amethyst Violet accent card
      const violetCard = screen.getByTestId("accent-card-violet");
      act(() => {
        fireEvent.click(violetCard);
      });
      expect(document.documentElement.getAttribute("data-accent")).toBe("violet");

      // Click Hyper Cyan accent card
      const cyanCard = screen.getByTestId("accent-card-cyan");
      act(() => {
        fireEvent.click(cyanCard);
      });
      expect(document.documentElement.getAttribute("data-accent")).toBe("cyan");

      // Click Electric Amber accent card
      const amberCard = screen.getByTestId("accent-card-amber");
      act(() => {
        fireEvent.click(amberCard);
      });
      expect(document.documentElement.getAttribute("data-accent")).toBe("amber");
    });
  });
});
