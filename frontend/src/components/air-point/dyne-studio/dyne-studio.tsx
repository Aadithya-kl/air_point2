import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Palette,
  Type,
  Layers,
  Zap,
  Clock3,
  Hexagon,
  Minus,
  SlidersHorizontal,
  Droplet,
  Circle,
  Eye,
} from "lucide-react";
import { MotionConfig, useReducedMotion } from "framer-motion";
import { SegmentedCapsuleShell, type ShellOption } from "./segmented-capsule-shell";
import { TwoRingColourPalette } from "./two-ring-colour-palette";
import { CustomColourView } from "./colour-explorations";
import { CentralCapsule } from "./central-capsule";
import { CapsuleAdjustmentTrack } from "./capsule-adjustment-track";
import {
  colours,
  extendedColours,
  initialSettings,
  adjustmentConfig,
  fonts,
  type Settings,
  type View,
  type Category,
  type Adjustment,
} from "./studio";
import { PREVIEW_CAPSULES, type CapsuleDefinition } from "./capsules";
import type { DyneHostAdapter } from "./layered/host-adapter";
import type { AirPointHudSettings, CapabilityMap } from "./layered/types";
import { commitDesktopSettings, runDesktopCountdownTest } from "./layered/host-adapter";

function getTitle(view: View): string {
  if (view.kind === "rest") return "Your capsule. Your way.";
  if (view.kind === "main") return "Make it yours.";
  if (view.kind === "category") {
    if (view.category === "Text") return "Choose a text setting.";
    if (view.category === "Colour") return "Choose your colour.";
    return `Choose your ${view.category.toLowerCase()}.`;
  }
  if (view.kind === "materialGroup")
    return view.group === "Surface" ? "Choose a surface." : "Choose your lighting.";
  if (view.kind === "fonts") return "Find your type.";
  if (view.kind === "customColour") return "Mix your colour.";
  if (view.kind === "extendedColours") return "More colours.";
  return "A little fine-tuning.";
}

function getCategoryCrumb(view: View): string {
  if (view.kind === "category") return view.category;
  if (view.kind === "materialGroup") return `Material / ${view.group}`;
  if (view.kind === "fonts") return "Text / Font";
  if (view.kind === "customColour") return "Colour / Custom";
  if (view.kind === "extendedColours") return "Colour / More Colours";
  if (view.kind === "adjust") {
    const parent = view.parentGroup ? `Material / ${view.parentGroup}` : view.parent;
    return `${parent} / ${view.adjustment}`;
  }
  return "Main options";
}

export interface DyneStudioProps {
  hostAdapter?: DyneHostAdapter;
  capabilities?: CapabilityMap;
  desktopSettings?: AirPointHudSettings;
  hostConnected?: boolean;
  settingsSynced?: boolean;
}

export function DyneStudio({
  hostAdapter,
  capabilities = {},
  desktopSettings,
  hostConnected = false,
  settingsSynced = false,
}: DyneStudioProps = {}) {
  // Per-capsule settings store (preview-only, persists across switches, never sent to native writer)
  const [capsulesSettings, setCapsulesSettings] = useState<Record<string, Settings>>(() => {
    const initial: Record<string, Settings> = {};
    for (const cap of PREVIEW_CAPSULES) {
      initial[cap.id] = { ...cap.defaultSettings };
    }
    return initial;
  });
  const [activeCapsuleIndex, setActiveCapsuleIndex] = useState(0);
  const [switchDirection, setSwitchDirection] = useState(0);
  const [dragOffset, setDragOffset] = useState(0);
  const wasSwiped = useRef(false);
  const swipeState = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    startTime: number;
    currentX: number;
    currentY: number;
    hasMoved: boolean;
  } | null>(null);

  const activeCapsule = PREVIEW_CAPSULES[activeCapsuleIndex] ?? PREVIEW_CAPSULES[0]!;
  const settings = capsulesSettings[activeCapsule.id] ?? initialSettings;

  const [activeView, setActiveView] = useState<View>({ kind: "rest" });
  const [transitionState, setTransitionState] = useState<"idle" | "transitioning">("idle");
  const [isRgbDragging, setIsRgbDragging] = useState(false);
  const [isTrackDragging, setIsTrackDragging] = useState(false);

  // The displayed heading derives from synchronized transition timing (never leads incoming content)
  const [displayedTitle, setDisplayedTitle] = useState<string>("Your capsule. Your way.");
  const [displayedCrumb, setDisplayedCrumb] = useState<string>("Main options");

  const reduced = useReducedMotion();
  const transitionTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const headingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isSwitcherEnabled = activeView.kind === "rest" || activeView.kind === "main";

  const change = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    setCapsulesSettings((prev) => {
      const current = prev[activeCapsule.id] ?? activeCapsule.defaultSettings;
      return {
        ...prev,
        [activeCapsule.id]: {
          ...current,
          [key]: value,
        },
      };
    });
  };

  const switchTo = useCallback(
    (index: number, dir?: number) => {
      if (index === activeCapsuleIndex) return;
      const chosenDir = dir !== undefined ? dir : index > activeCapsuleIndex ? 1 : -1;
      setSwitchDirection(chosenDir);
      setActiveCapsuleIndex(index);
    },
    [activeCapsuleIndex],
  );

  const prevCapsule = useCallback(() => {
    if (PREVIEW_CAPSULES.length <= 1) return;
    setSwitchDirection(-1);
    setActiveCapsuleIndex((i) => (i - 1 + PREVIEW_CAPSULES.length) % PREVIEW_CAPSULES.length);
  }, []);

  const nextCapsule = useCallback(() => {
    if (PREVIEW_CAPSULES.length <= 1) return;
    setSwitchDirection(1);
    setActiveCapsuleIndex((i) => (i + 1) % PREVIEW_CAPSULES.length);
  }, []);

  // Synchronized navigation transition:
  // Immediate unmount of outgoing layer prevents colliding layouts and lingering ring outlines.
  const navigate = useCallback(
    (target: View) => {
      if (transitionTimer.current) clearTimeout(transitionTimer.current);
      if (headingTimer.current) clearTimeout(headingTimer.current);

      if (reduced || target.kind === "rest") {
        setActiveView(target);
        setDisplayedTitle(getTitle(target));
        setDisplayedCrumb(getCategoryCrumb(target));
        setTransitionState("idle");
        return;
      }

      setActiveView(target);
      setTransitionState("transitioning");

      headingTimer.current = setTimeout(() => {
        setDisplayedTitle(getTitle(target));
        setDisplayedCrumb(getCategoryCrumb(target));
      }, 80);

      transitionTimer.current = setTimeout(() => {
        setTransitionState("idle");
      }, 200);
    },
    [reduced],
  );

  const back = useCallback(() => {
    const current = activeView;
    let next: View = { kind: "rest" };

    if (current.kind === "rest") {
      next = { kind: "main" };
    } else if (current.kind === "main") {
      next = { kind: "rest" };
    } else if (current.kind === "adjust") {
      next = current.parentGroup
        ? { kind: "materialGroup", group: current.parentGroup }
        : { kind: "category", category: current.parent };
    } else if (current.kind === "materialGroup") {
      next = { kind: "category", category: "Material" };
    } else if (current.kind === "fonts") {
      next = { kind: "category", category: "Text" };
    } else if (current.kind === "customColour" || current.kind === "extendedColours") {
      next = { kind: "category", category: "Colour" };
    } else {
      next = { kind: "main" };
    }

    navigate(next);
  }, [activeView, navigate]);

  useEffect(() => {
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        back();
        return;
      }

      if (
        isSwitcherEnabled &&
        PREVIEW_CAPSULES.length > 1 &&
        (e.key === "ArrowLeft" || e.key === "ArrowRight")
      ) {
        const activeEl = document.activeElement;
        const tagName = activeEl?.tagName;
        const isInput =
          tagName === "INPUT" ||
          tagName === "TEXTAREA" ||
          activeEl?.classList.contains("track-handle") ||
          activeEl?.getAttribute("role") === "slider";
        if (!isInput) {
          e.preventDefault();
          if (e.key === "ArrowLeft") {
            prevCapsule();
          } else {
            nextCapsule();
          }
        }
      }
    };
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [back, isSwitcherEnabled, prevCapsule, nextCapsule, activeView.kind]);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isSwitcherEnabled || PREVIEW_CAPSULES.length <= 1) return;
    if (
      (e.target as HTMLElement).closest(
        ".capsule-nav-arrow, .capsule-dot, .shell-option, .track-handle, input, textarea",
      )
    ) {
      return;
    }

    swipeState.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      startTime: typeof performance !== "undefined" ? performance.now() : Date.now(),
      currentX: e.clientX,
      currentY: e.clientY,
      hasMoved: false,
    };
    wasSwiped.current = false;
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!swipeState.current || swipeState.current.pointerId !== e.pointerId) return;

    const dx = e.clientX - swipeState.current.startX;
    const dy = e.clientY - swipeState.current.startY;
    swipeState.current.currentX = e.clientX;
    swipeState.current.currentY = e.clientY;

    if (Math.hypot(dx, dy) >= 6) {
      if (!swipeState.current.hasMoved) {
        try {
          e.currentTarget.setPointerCapture(e.pointerId);
        } catch {
          /* Pointer capture is optional in some browsers and test environments. */
        }
      }
      swipeState.current.hasMoved = true;
      wasSwiped.current = true;
      // Follow pointer slightly (resisted travel up to ~24px, no inertia)
      const resisted = Math.sign(dx) * Math.min(24, Math.abs(dx) * 0.25);
      setDragOffset(resisted);
    }
  };

  const handlePointerEnd = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!swipeState.current || swipeState.current.pointerId !== e.pointerId) return;

    const { startX, startY, startTime, hasMoved } = swipeState.current;
    try {
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
    } catch {
      /* Pointer capture may already have been released by the browser. */
    }

    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    const dt = Math.max(1, now - startTime);
    const vx = Math.abs(dx) / dt;

    if (hasMoved) {
      const isMostlyHorizontal = Math.abs(dx) > 1.5 * Math.abs(dy);
      const isCommitted = (Math.abs(dx) > 48 || vx > 0.4) && isMostlyHorizontal;

      if (isCommitted) {
        if (dx < 0) {
          nextCapsule();
        } else {
          prevCapsule();
        }
      }
    }

    setDragOffset(0);
    swipeState.current = null;
    setTimeout(() => {
      wasSwiped.current = false;
    }, 60);
  };

  const handleCapsuleClick = () => {
    if (wasSwiped.current) return;
    back();
  };

  useEffect(
    () => () => {
      if (transitionTimer.current) clearTimeout(transitionTimer.current);
      if (headingTimer.current) clearTimeout(headingTimer.current);
    },
    [],
  );

  const adjust = (adjustment: Adjustment, parent: Category, parentGroup?: "Surface" | "Lighting") =>
    navigate({ kind: "adjust", adjustment, parent, ...(parentGroup ? { parentGroup } : {}) });
  const apply = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    change(key, value);
    navigate({ kind: "main" });
  };

  // Builder for layer options
  const buildOptions = (targetView: View): ShellOption[] => {
    if (targetView.kind === "main") {
      return (
        [
          ["Colour", Palette],
          ["Text", Type],
          ["Material", Layers],
          ["Notifications", Zap],
          ["Behaviour & Timing", Clock3],
          ["Shape", Hexagon],
        ] as const
      ).map(([label, icon]) => ({
        label,
        icon,
        onSelect: () => navigate({ kind: "category", category: label }),
      }));
    }

    if (targetView.kind === "category") {
      if (targetView.category === "Colour") {
        return [
          ...["Brown", "Red", "Blue", "Neon"].map((name) => ({
            label: name,
            colour: colours.find((c) => c[0] === name)?.[1],
            selected: settings.accent === name,
            onSelect: () => apply("accent", name),
          })),
          {
            label: "More Colours",
            icon: Palette,
            onSelect: () => navigate({ kind: "extendedColours" }),
          },
          ...["White", "Grey", "Gold", "Purple"].map((name) => ({
            label: name,
            colour: colours.find((c) => c[0] === name)?.[1],
            selected: settings.accent === name,
            onSelect: () => apply("accent", name),
          })),
          {
            label: "Custom",
            icon: Palette,
            selected: settings.accent === "Custom",
            onSelect: () => {
              change("accent", "Custom");
              navigate({ kind: "customColour" });
            },
          },
        ];
      }

      if (targetView.category === "Material") {
        return [
          {
            label: "Surface",
            icon: Layers,
            onSelect: () => navigate({ kind: "materialGroup", group: "Surface" }),
          },
          {
            label: "Lighting",
            icon: Clock3,
            onSelect: () => navigate({ kind: "materialGroup", group: "Lighting" }),
          },
        ];
      }

      if (targetView.category === "Text") {
        return ["Font", "Font Size", "Font Boldness"].map((label) => ({
          label,
          icon: Type,
          onSelect: () =>
            label === "Font" ? navigate({ kind: "fonts" }) : adjust(label as Adjustment, "Text"),
        }));
      }

      if (targetView.category === "Shape") {
        return [
          {
            label: "Classic",
            icon: Hexagon,
            selected: settings.roundness === 56,
            onSelect: () => apply("roundness", 56),
          },
          {
            label: "Roundness",
            icon: SlidersHorizontal,
            onSelect: () => adjust("Roundness", "Shape"),
          },
          {
            label: "Soft square",
            icon: Minus,
            selected: settings.roundness === 28,
            onSelect: () => apply("roundness", 28),
          },
        ];
      }

      if (targetView.category === "Notifications") {
        const enabled = desktopSettings?.notificationsEnabled ?? true;
        return [
          {
            label: `Notifications: ${enabled ? "On" : "Off"}`,
            icon: Zap,
            selected: enabled,
            disabled: !settingsSynced || !hostConnected || !hostAdapter,
            onSelect: () => {
              if (hostAdapter && settingsSynced && hostConnected)
                void commitDesktopSettings(
                  hostAdapter,
                  { notificationsEnabled: !enabled },
                  capabilities,
                );
            },
          },
          {
            label: "Completion-message duration",
            icon: Clock3,
            onSelect: () => navigate({ kind: "category", category: "Notifications" }),
          },
        ];
      }
      if (targetView.category === "Behaviour & Timing") {
        const enabled = desktopSettings?.enabled ?? true,
          countdown = desktopSettings?.timerEnabled ?? true,
          autoHide = desktopSettings?.autohideEnabled ?? true;
        return [
          {
            label: `Show HUD: ${enabled ? "On" : "Off"}`,
            icon: Eye,
            selected: enabled,
            disabled: !settingsSynced || !hostConnected || !hostAdapter,
            onSelect: () => {
              if (hostAdapter && settingsSynced && hostConnected)
                void commitDesktopSettings(hostAdapter, { enabled: !enabled }, capabilities);
            },
          },
          {
            label: `Countdown badge: ${countdown ? "On" : "Off"}`,
            icon: Clock3,
            selected: countdown,
            disabled: !settingsSynced || !hostConnected || !hostAdapter,
            onSelect: () => {
              if (hostAdapter && settingsSynced && hostConnected)
                void commitDesktopSettings(hostAdapter, { timerEnabled: !countdown }, capabilities);
            },
          },
          {
            label: `Auto-hide: ${autoHide ? "On" : "Off"}`,
            icon: Eye,
            selected: autoHide,
            disabled: !settingsSynced || !hostConnected || !hostAdapter,
            onSelect: () => {
              if (hostAdapter && settingsSynced && hostConnected)
                void commitDesktopSettings(
                  hostAdapter,
                  { autohideEnabled: !autoHide },
                  capabilities,
                );
            },
          },
          {
            label: "HUD duration",
            icon: Clock3,
            onSelect: () => navigate({ kind: "category", category: "Behaviour & Timing" }),
          },
          {
            label: "Test countdown",
            icon: Zap,
            disabled: !settingsSynced || !hostConnected || !hostAdapter,
            onSelect: () => {
              if (hostAdapter && settingsSynced && hostConnected)
                void runDesktopCountdownTest(hostAdapter, 5);
            },
          },
        ];
      }
    }

    if (targetView.kind === "materialGroup" && targetView.group === "Surface") {
      return (["Matte", "Glass", "Translucent"] as const).map((label) => ({
        label,
        icon: label === "Glass" ? Droplet : label === "Matte" ? Circle : Layers,
        selected: settings.texture === label,
        onSelect: () => adjust(label, "Material", "Surface"),
      }));
    }

    if (targetView.kind === "materialGroup" && targetView.group === "Lighting") {
      return (["Luminous", "Balanced", "Quiet"] as const).map((label) => ({
        label,
        icon: Clock3,
        selected: settings.style === label,
        onSelect: () => apply("style", label),
      }));
    }

    if (targetView.kind === "fonts") {
      return Object.keys(fonts).map((label) => ({
        label,
        icon: Type,
        selected: settings.font === label,
        onSelect: () => apply("font", label),
      }));
    }

    if (targetView.kind === "extendedColours") {
      return extendedColours.map(([label, colour]) => ({
        label,
        colour,
        selected: settings.accent === label,
        onSelect: () => {
          change("accent", label);
          navigate({ kind: "category", category: "Colour" });
        },
      }));
    }

    return [];
  };

  // Render a specific layer view with a transitionState
  const renderLayer = (layerView: View, state: "entering" | "exiting" | "idle") => {
    if (layerView.kind === "rest") return null;

    if (layerView.kind === "customColour") {
      return (
        <CustomColourView
          key={`custom-${state}`}
          settings={settings}
          transitionState={state}
          onDragStateChange={setIsRgbDragging}
          onChange={(customRgb) => {
            change("customRgb", customRgb);
            change("accent", "Custom");
          }}
          onBack={back}
        />
      );
    }

    if (layerView.kind === "extendedColours") {
      return (
        <TwoRingColourPalette
          key={`palette-${state}`}
          settings={settings}
          transitionState={state}
          onSelect={(colourName) => {
            change("accent", colourName);
            navigate({ kind: "category", category: "Colour" });
          }}
          onBack={back}
        />
      );
    }

    if (layerView.kind === "adjust") {
      const config = adjustmentConfig[layerView.adjustment];
      if (!config) return null;
      return (
        <CapsuleAdjustmentTrack
          key={`adjust-${layerView.adjustment}-${state}`}
          title={layerView.adjustment}
          value={Number(settings[config.key])}
          min={config.min}
          max={config.max}
          midpoint={config.midpoint}
          step={config.step}
          unit={config.unit}
          transitionState={state}
          onDragStateChange={setIsTrackDragging}
          onChange={(value) => change(config.key, value)}
        />
      );
    }

    const opts = buildOptions(layerView);
    if (opts.length === 0) return null;

    const key = layerView.kind === "category" ? layerView.category : layerView.kind;
    return (
      <SegmentedCapsuleShell key={`shell-${key}-${state}`} options={opts} transitionState={state} />
    );
  };

  const isTextureActive =
    (activeView.kind === "category" && activeView.category === "Material") ||
    (activeView.kind === "materialGroup" && activeView.group === "Surface") ||
    (activeView.kind === "adjust" &&
      ["Glass", "Matte", "Translucent"].includes(activeView.adjustment));

  return (
    <MotionConfig reducedMotion="user">
      <div className="dyne-studio-root" data-testid="dyne-studio-root">
        <main className="studio">
          <header className={`studio-header ${activeView.kind === "rest" ? "sr-only" : ""}`}>
            <div>
              <div className="brand-eyebrow">
                AIRPOINT <span>/</span> DYNE
              </div>
              <h1>
                Dyne Studio
                <span className="title-dot" aria-hidden="true">
                  .
                </span>
              </h1>
              <p>Shape the capsule that lives on your desktop.</p>
            </div>
            <div className="header-note">
              <span className="mode-dot" />
              {hostConnected && settingsSynced ? "HOST CONNECTED" : "LOCAL PREVIEW"}
              <span className="header-divider" />
              <span>STUDIO 01</span>
            </div>
          </header>

          <section
            className={`capsule-stage ${activeView.kind === "rest" ? "is-resting" : ""}`}
            aria-label="Capsule customization stage"
          >
            <div className={activeView.kind === "rest" ? "sr-only" : "stage-topline"}>
              <div className="stage-breadcrumb">
                <span className="stage-index">01</span>
                <span>CAPSULE STUDIO</span>
                <ChevronRight size={12} />
                <span className="active-crumb">{displayedCrumb}</span>
              </div>
            </div>

            <div className={activeView.kind === "rest" ? "sr-only" : "stage-heading"}>
              <h2>{displayedTitle}</h2>
            </div>

            <div className="interaction-frame">
              <div
                className="capsule-assembly"
                role="region"
                aria-roledescription="carousel"
                aria-label="Preview event states"
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerEnd}
                onPointerCancel={handlePointerEnd}
              >
                {/* Screen reader politeness live region for carousel updates */}
                <div className="sr-only" aria-live="polite" aria-atomic="true">
                  {`Event preview ${activeCapsuleIndex + 1} of ${PREVIEW_CAPSULES.length}: ${activeCapsule.name}`}
                </div>

                {isTextureActive && <div className="texture-preview-backdrop" aria-hidden="true" />}

                {renderLayer(activeView, transitionState === "transitioning" ? "entering" : "idle")}

                {/* Central capsule stays permanently mounted across the entire session */}
                <CentralCapsule
                  capsule={activeCapsule}
                  settings={settings}
                  resting={activeView.kind === "rest"}
                  isDragging={isRgbDragging || isTrackDragging}
                  direction={switchDirection}
                  dragOffset={dragOffset}
                  onClick={handleCapsuleClick}
                />

                {/* Switcher Navigation Arrows (Enabled on Rest & Main layers only) */}
                {isSwitcherEnabled && PREVIEW_CAPSULES.length > 1 && (
                  <div
                    className={`capsule-switcher-arrows ${activeView.kind === "rest" ? "unobtrusive-at-rest" : ""}`}
                  >
                    <button
                      type="button"
                      className="capsule-nav-arrow capsule-nav-prev"
                      aria-label="Previous event state"
                      onClick={prevCapsule}
                    >
                      <ChevronLeft size={20} strokeWidth={2} />
                    </button>
                    <button
                      type="button"
                      className="capsule-nav-arrow capsule-nav-next"
                      aria-label="Next event state"
                      onClick={nextCapsule}
                    >
                      <ChevronRight size={20} strokeWidth={2} />
                    </button>
                  </div>
                )}

                {/* Switcher Dots Indicator (Enabled on Rest & Main layers only) */}
                {isSwitcherEnabled && PREVIEW_CAPSULES.length > 1 && (
                  <div
                    className={`capsule-switcher-indicator ${activeView.kind === "rest" ? "unobtrusive-at-rest" : ""}`}
                    role="tablist"
                    aria-label="Preview event selection"
                  >
                    <div className="capsule-dots-group">
                      {PREVIEW_CAPSULES.map((cap, idx) => (
                        <button
                          key={cap.id}
                          type="button"
                          role="tab"
                          aria-selected={idx === activeCapsuleIndex}
                          aria-label={`Preview event: ${cap.name}`}
                          onClick={() => switchTo(idx)}
                          className={`capsule-dot ${idx === activeCapsuleIndex ? "is-active" : ""}`}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {activeView.kind === "category" &&
              (activeView.category === "Notifications" ||
                activeView.category === "Behaviour & Timing") && (
                <div className="dyne-host-controls" aria-label="Desktop operational settings">
                  {!settingsSynced && (
                    <p role="status">WAITING FOR HOST SYNC — operational controls are disabled.</p>
                  )}
                  {settingsSynced && !hostConnected && (
                    <p role="status">HOST OFFLINE — showing last known settings.</p>
                  )}
                  {settingsSynced && hostConnected && <p role="status">HOST CONNECTED</p>}
                  {activeView.category === "Notifications" && (
                    <label>
                      Completion-message duration: {desktopSettings?.completionDurationS ?? "—"} s
                      <input
                        aria-label="Completion-message duration"
                        type="range"
                        min="1"
                        max="5"
                        step="0.5"
                        disabled={!settingsSynced || !hostConnected || !hostAdapter}
                        value={desktopSettings?.completionDurationS ?? 2}
                        onChange={(e) => {
                          const value = Number(e.currentTarget.value);
                          if (hostAdapter)
                            void commitDesktopSettings(
                              hostAdapter,
                              { completionDurationS: value },
                              capabilities,
                            );
                        }}
                      />
                    </label>
                  )}
                  {activeView.category === "Behaviour & Timing" && (
                    <label>
                      HUD duration: {desktopSettings?.hudDurationS ?? "—"} s
                      <input
                        aria-label="HUD duration"
                        type="range"
                        min="10"
                        max="1800"
                        step="10"
                        disabled={!settingsSynced || !hostConnected || !hostAdapter}
                        value={desktopSettings?.hudDurationS ?? 120}
                        onChange={(e) => {
                          const value = Number(e.currentTarget.value);
                          if (hostAdapter)
                            void commitDesktopSettings(
                              hostAdapter,
                              { hudDurationS: value },
                              capabilities,
                            );
                        }}
                      />
                    </label>
                  )}
                </div>
              )}

            {activeView.kind !== "rest" && (
              <div className="stage-bottomline">
                <span>
                  <span className="keycap">ESC</span> TO GO BACK
                </span>
              </div>
            )}
          </section>
        </main>
      </div>
    </MotionConfig>
  );
}
