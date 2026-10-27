import React, { useEffect, useState, useRef, useCallback, useLayoutEffect } from "react";
import { Camera, Eye, Layers, Lock, Radio, ShieldCheck, Terminal, Unlock, VideoOff } from "lucide-react";
import { DEFAULT_BRIDGE_BASE_URL } from "@/lib/air-point-model";

export type TrackingViewMode = "landmarks" | "overlay" | "camera";

export interface NormalizedPoint {
  x: number;
  y: number;
  z?: number;
}

export interface HandLandmarkPayload {
  label?: string;
  handedness?: string;
  landmarks: NormalizedPoint[];
}

export interface RawFacePayload {
  detected?: boolean;
  lip_center?: [number, number] | [number, number, number] | { x: number; y: number } | null;
  right_ear?: [number, number] | [number, number, number] | { x: number; y: number } | null;
  left_ear?: [number, number] | [number, number, number] | { x: number; y: number } | null;
  mouth_width?: number | null;
  lip_contour?: Array<[number, number] | { x: number; y: number }> | null;
}

export interface LandmarksResponse {
  timestamp?: number;
  hands?:
    | {
        right?: NormalizedPoint[] | null;
        left?: NormalizedPoint[] | null;
      }
    | HandLandmarkPayload[]
    | null;
  face?: RawFacePayload | NormalizedPoint[] | Record<string, unknown> | null;
  tracking?: string;
  owner?: string;
  active_gesture?: string;
  is_locked?: boolean;
  click_state?: string | boolean;
  last_pinch_norm?: number;
}

export interface NormalizedHand {
  name: "RIGHT" | "LEFT";
  isRight: boolean;
  landmarks: NormalizedPoint[];
}

export interface NormalizedFaceData {
  detected: boolean;
  lipCenter: { x: number; y: number } | null;
  rightEar: { x: number; y: number } | null;
  leftEar: { x: number; y: number } | null;
  lipContour: Array<{ x: number; y: number }>;
}

export const HAND_CONNECTIONS: ReadonlyArray<[number, number]> = [
  [0, 1], [1, 2], [2, 3], [3, 4],       // Thumb
  [0, 5], [5, 6], [6, 7], [7, 8],       // Index
  [0, 9], [9, 10], [10, 11], [11, 12],  // Middle
  [0, 13], [13, 14], [14, 15], [15, 16],// Ring
  [0, 17], [17, 18], [18, 19], [19, 20],// Pinky
  [5, 9], [9, 13], [13, 17],            // Palm knuckle arch
];

function parseLandmarkPoints(arr: unknown[]): NormalizedPoint[] {
  const valid: NormalizedPoint[] = [];
  for (const pt of arr) {
    if (!pt || typeof pt !== "object") continue;
    const p = pt as Record<string, unknown>;
    const x = Number(p["x"]);
    const y = Number(p["y"]);
    const z = typeof p["z"] === "number" ? Number(p["z"]) : 0;
    if (Number.isFinite(x) && Number.isFinite(y)) {
      valid.push({ x, y, z });
    }
  }
  return valid;
}

export function normalizeHandPayload(rawHands: unknown): NormalizedHand[] {
  if (!rawHands) return [];
  const result: NormalizedHand[] = [];

  // Case 1: Verified Python Engine Dictionary {"right": [...], "left": [...]}
  if (typeof rawHands === "object" && !Array.isArray(rawHands)) {
    const dict = rawHands as Record<string, unknown>;
    const rightRaw = dict["right"];
    const leftRaw = dict["left"];

    if (Array.isArray(rightRaw) && rightRaw.length >= 21) {
      const pts = parseLandmarkPoints(rightRaw);
      if (pts.length >= 21) {
        result.push({ name: "RIGHT", isRight: true, landmarks: pts });
      }
    }
    if (Array.isArray(leftRaw) && leftRaw.length >= 21) {
      const pts = parseLandmarkPoints(leftRaw);
      if (pts.length >= 21) {
        result.push({ name: "LEFT", isRight: false, landmarks: pts });
      }
    }
    return result;
  }

  // Case 2: Array Format [{ label?: string, handedness?: string, landmarks: [...] }]
  if (Array.isArray(rawHands)) {
    rawHands.forEach((item, idx) => {
      if (!item || typeof item !== "object") return;
      const rawItem = item as Record<string, unknown>;
      const rawPts = rawItem["landmarks"];
      if (!Array.isArray(rawPts) || rawPts.length < 21) return;
      const pts = parseLandmarkPoints(rawPts);
      if (pts.length < 21) return;

      const label = String(rawItem["label"] ?? rawItem["handedness"] ?? "").toUpperCase();
      const isRight = label.includes("RIGHT") || (label === "" && idx === 0);
      result.push({
        name: isRight ? "RIGHT" : "LEFT",
        isRight,
        landmarks: pts,
      });
    });
    return result;
  }

  return [];
}

export function parseCoordinatePair(val: unknown): { x: number; y: number } | null {
  if (!val) return null;
  if (Array.isArray(val) && val.length >= 2) {
    const x = Number(val[0]);
    const y = Number(val[1]);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      return { x, y };
    }
    return null;
  }
  if (typeof val === "object" && val !== null) {
    const obj = val as Record<string, unknown>;
    const x = Number(obj["x"]);
    const y = Number(obj["y"]);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      return { x, y };
    }
  }
  return null;
}

export function normalizeFacePayload(rawFace: unknown): NormalizedFaceData | null {
  if (!rawFace || typeof rawFace !== "object") return null;

  // Subcase A: rawFace is an array of points
  if (Array.isArray(rawFace)) {
    const contour: Array<{ x: number; y: number }> = [];
    for (const item of rawFace) {
      const pt = parseCoordinatePair(item);
      if (pt) contour.push(pt);
    }
    if (contour.length === 0) return null;
    return {
      detected: true,
      lipCenter: contour[0] ?? null,
      rightEar: null,
      leftEar: null,
      lipContour: contour,
    };
  }

  const dict = rawFace as Record<string, unknown>;
  const keys = Object.keys(dict);
  if (keys.length === 0) return null;

  const detected = Boolean(dict["detected"] ?? false);
  const lipCenter = parseCoordinatePair(dict["lip_center"] ?? dict["lipCenter"]);
  const rightEar = parseCoordinatePair(dict["right_ear"] ?? dict["rightEar"]);
  const leftEar = parseCoordinatePair(dict["left_ear"] ?? dict["leftEar"]);

  const contour: Array<{ x: number; y: number }> = [];
  const rawContour = dict["lip_contour"] ?? dict["lipContour"];
  if (Array.isArray(rawContour)) {
    for (const pt of rawContour) {
      const parsed = parseCoordinatePair(pt);
      if (parsed) contour.push(parsed);
    }
  }

  if (!detected && !lipCenter && !rightEar && !leftEar && contour.length === 0) {
    return null;
  }

  return {
    detected: detected || Boolean(lipCenter || rightEar || leftEar || contour.length > 0),
    lipCenter,
    rightEar,
    leftEar,
    lipContour: contour,
  };
}

export interface LiveTrackingCanvasProps {
  connected?: boolean;
  running?: boolean;
  paused?: boolean;
  trackingStatus?: string;
  pointerOwner?: string;
  activeGesture?: string;
  bridgeUrl?: string;
  initialMode?: TrackingViewMode;
  onStreamStatusChange?: (available: boolean) => void;
  reducedMotion?: boolean;
}

export const LiveTrackingCanvas: React.FC<LiveTrackingCanvasProps> = ({
  connected = false,
  running,
  paused,
  trackingStatus = "No Hands",
  pointerOwner = "NONE",
  activeGesture = "idle",
  bridgeUrl = DEFAULT_BRIDGE_BASE_URL,
  initialMode = "landmarks",
  onStreamStatusChange,
  reducedMotion,
}) => {
  const isRunning = running !== undefined ? running : paused !== undefined ? !paused : true;
  const isPaused = paused !== undefined ? paused : !isRunning;

  const [mode, setMode] = useState<TrackingViewMode>(initialMode);
  const [landmarksData, setLandmarksData] = useState<LandmarksResponse>({
    hands: null,
    face: null,
    is_locked: false,
    click_state: "idle",
  });
  const [cameraError, setCameraError] = useState<boolean>(false);

  // Liquid Glass Selector state and DOM measurement
  const trackRef = useRef<HTMLDivElement | null>(null);
  const buttonRefs = useRef<Record<TrackingViewMode, HTMLButtonElement | null>>({
    landmarks: null,
    overlay: null,
    camera: null,
  });

  const [indicator, setIndicator] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
    ready: boolean;
  }>({ left: 0, top: 0, width: 0, height: 0, ready: false });

  const [hasInitialized, setHasInitialized] = useState<boolean>(false);
  const [pressedMode, setPressedMode] = useState<TrackingViewMode | null>(null);
  const [pointerSheen, setPointerSheen] = useState<{ x: number; y: number; visible: boolean }>({
    x: 0,
    y: 0,
    visible: false,
  });

  // Track system & preference reduced motion
  const [systemReducedMotion, setSystemReducedMotion] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return (
      window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
      document.documentElement.getAttribute("data-reduced-motion") === "true"
    );
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleMq = () => {
      setSystemReducedMotion(
        mq.matches || document.documentElement.getAttribute("data-reduced-motion") === "true"
      );
    };
    mq.addEventListener?.("change", handleMq);

    const observer = new MutationObserver(() => {
      setSystemReducedMotion(
        mq.matches || document.documentElement.getAttribute("data-reduced-motion") === "true"
      );
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-reduced-motion"],
    });

    return () => {
      mq.removeEventListener?.("change", handleMq);
      observer.disconnect();
    };
  }, []);

  const isMotionReduced = reducedMotion ?? systemReducedMotion;

  // Glider measurement and alignment
  const updateIndicator = useCallback(() => {
    const track = trackRef.current;
    const btn = buttonRefs.current[mode];
    if (!track || !btn) return;

    const trackRect = track.getBoundingClientRect();
    const btnRect = btn.getBoundingClientRect();

    const left = trackRect.width > 0 ? btnRect.left - trackRect.left : btn.offsetLeft;
    const top = trackRect.height > 0 ? btnRect.top - trackRect.top : btn.offsetTop;
    const width = btnRect.width > 0 ? btnRect.width : (btn.offsetWidth || 120);
    const height = btnRect.height > 0 ? btnRect.height : (btn.offsetHeight || 28);

    setIndicator({
      left,
      top,
      width,
      height,
      ready: true,
    });
  }, [mode]);

  // Synchronize on state change and layout
  useLayoutEffect(() => {
    updateIndicator();
  }, [updateIndicator]);

  useEffect(() => {
    // Immediate alignment on mount without animation flight, then enable transitions
    const raf = requestAnimationFrame(() => {
      updateIndicator();
      setTimeout(() => {
        setHasInitialized(true);
      }, 30);
    });

    const handleResize = () => {
      updateIndicator();
    };

    window.addEventListener("resize", handleResize);
    window.addEventListener("orientationchange", handleResize);

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined" && trackRef.current) {
      ro = new ResizeObserver(() => updateIndicator());
      ro.observe(trackRef.current);
    }

    if (document.fonts?.ready) {
      document.fonts.ready.then(updateIndicator).catch(() => {});
    }

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("orientationchange", handleResize);
      if (ro) ro.disconnect();
    };
  }, [updateIndicator]);

  // Pointer sheen tracking confined to selector track
  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (isMotionReduced) return;
    const rect = e.currentTarget.getBoundingClientRect();
    setPointerSheen({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      visible: true,
    });
  };

  const handlePointerLeave = () => {
    setPointerSheen((prev) => ({ ...prev, visible: false }));
  };

  // Full keyboard navigation across segmented options
  const handleTablistKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const modes: TrackingViewMode[] = ["landmarks", "overlay", "camera"];
    const curIdx = modes.indexOf(mode);
    let targetIdx = curIdx;

    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      targetIdx = (curIdx + 1) % modes.length;
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      targetIdx = (curIdx - 1 + modes.length) % modes.length;
    } else if (e.key === "Home") {
      e.preventDefault();
      targetIdx = 0;
    } else if (e.key === "End") {
      e.preventDefault();
      targetIdx = modes.length - 1;
    }

    if (targetIdx !== curIdx) {
      const nextMode = modes[targetIdx];
      if (nextMode) {
        setMode(nextMode);
        if (nextMode === "overlay" || nextMode === "camera") {
          setCameraError(false);
        }
        buttonRefs.current[nextMode]?.focus();
      }
    }
  };

  // Poll GET /api/landmarks every 50ms when connected
  useEffect(() => {
    let active = true;
    const pollLandmarks = async () => {
      try {
        const res = await fetch(`${bridgeUrl}/api/landmarks`);
        if (!res.ok) return;
        const json = (await res.json()) as LandmarksResponse;
        if (active && json && typeof json === "object") {
          setLandmarksData(json);
        }
      } catch {
        // Offline handled via parent connected prop
      }
    };

    pollLandmarks();
    const interval = setInterval(pollLandmarks, 50);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [bridgeUrl, connected, isRunning]);

  useEffect(() => {
    setCameraError(false);
  }, [mode, connected]);

  // Safely normalize hands and face using verified backend adapters
  const normalizedHands = normalizeHandPayload(landmarksData.hands);
  const hasHands = normalizedHands.length > 0;
  const hasRightHand = normalizedHands.some((h) => h.isRight);
  const hasLeftHand = normalizedHands.some((h) => !h.isRight);

  const faceData = normalizeFacePayload(landmarksData.face);
  const isLocked = Boolean(landmarksData.is_locked);
  const clickState = String(landmarksData.click_state ?? "idle");
  const isClickConfirmed = clickState === "SINGLE CLICK" || clickState === "DOUBLE CLICK";
  const isCandidate =
    clickState === "CANDIDATE" ||
    clickState === "DOUBLE-CLICK CANDIDATE" ||
    clickState === "CLICK PENDING" ||
    clickState === "PINCH DETECTED" ||
    clickState === "WAITING FOR RELEASE";

  const showCameraFeed = (mode === "overlay" || mode === "camera") && connected && !cameraError;
  const showLandmarksLayer = mode === "landmarks" || mode === "overlay";

  // Derive top header title
  const trackingHeaderTitle = connected
    ? isPaused
      ? "TRACKING PAUSED"
      : mode === "overlay"
      ? "CAMERA + LIVE LANDMARKS"
      : mode === "camera"
      ? "RAW CAMERA STREAM"
      : trackingStatus
      ? `TRACKING: ${trackingStatus.toUpperCase()}`
      : hasHands
      ? `TRACKING ACTIVE · ${normalizedHands.length} HAND(S)`
      : "SCANNING FOR HANDS"
    : "ENGINE OFFLINE";

  return (
    <div className="ap-panel overflow-hidden flex flex-col">
      {/* Top Viewport Control Bar */}
      <div className="px-4 py-2.5 border-b border-[var(--border-subtle)] bg-[var(--bg-elevated)] flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <Radio
            className={`w-4 h-4 ${
              connected && isRunning
                ? "text-[var(--status-healthy)] animate-pulse"
                : "text-[var(--text-muted)]"
            }`}
          />
          <span className="text-xs font-mono font-semibold uppercase tracking-wider">
            {trackingHeaderTitle}
          </span>
          {connected && (
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono ${
                isLocked
                  ? "bg-[var(--accent-muted)] text-[var(--accent-primary)] border border-[var(--accent-border)]"
                  : "bg-[var(--bg-surface)] text-[var(--text-secondary)] border border-[var(--border-default)]"
              }`}
            >
              {isLocked ? (
                <>
                  <Lock className="w-3 h-3" /> LOCKED
                </>
              ) : (
                <>
                  <Unlock className="w-3 h-3" /> UNLOCKED
                </>
              )}
            </span>
          )}
        </div>

        {/* Apple-grade Liquid Glass 3-Mode View Selector */}
        <div
          ref={trackRef}
          role="tablist"
          aria-label="Spatial viewport display mode"
          tabIndex={0}
          onKeyDown={handleTablistKeyDown}
          onPointerMove={handlePointerMove}
          onPointerLeave={handlePointerLeave}
          className="liquid-glass-track"
          data-testid="liquid-glass-selector"
        >
          {/* Shared gliding glass indicator */}
          <div
            className={`liquid-glass-glider ${
              !hasInitialized || isMotionReduced ? "no-transition" : ""
            } ${pressedMode !== null ? "is-pressed" : ""}`}
            style={{
              transform: `translate3d(${indicator.left}px, ${indicator.top}px, 0) scale(${
                pressedMode !== null ? 0.97 : 1
              })`,
              width: `${indicator.width}px`,
              height: `${indicator.height}px`,
              opacity: indicator.ready ? 1 : 0,
            }}
            aria-hidden="true"
            data-testid="liquid-glass-glider"
          >
            <div className="liquid-glass-specular" aria-hidden="true" />
          </div>

          {/* Dynamic pointer reflection confined to selector track */}
          {!isMotionReduced && pointerSheen.visible && (
            <div
              className="liquid-glass-sheen"
              style={{
                transform: `translate3d(${pointerSheen.x}px, ${pointerSheen.y}px, 0) translate(-50%, -50%)`,
                opacity: 1,
              }}
              aria-hidden="true"
            />
          )}

          {/* Mode tab buttons */}
          {(
            [
              {
                id: "landmarks",
                label: "Live landmarks",
                icon: <Eye className="w-3.5 h-3.5 text-current shrink-0" />,
              },
              {
                id: "overlay",
                label: "Camera + Landmarks",
                icon: <Layers className="w-3.5 h-3.5 text-current shrink-0" />,
              },
              {
                id: "camera",
                label: "Camera preview",
                icon: <Camera className="w-3.5 h-3.5 text-current shrink-0" />,
              },
            ] as const
          ).map(({ id, label, icon }) => {
            const isSelected = mode === id;
            const isPressed = pressedMode === id;
            return (
              <button
                key={id}
                ref={(el) => {
                  buttonRefs.current[id] = el;
                }}
                type="button"
                role="tab"
                aria-selected={isSelected}
                tabIndex={isSelected ? 0 : -1}
                onClick={() => {
                  setMode(id);
                  if (id === "overlay" || id === "camera") {
                    setCameraError(false);
                  }
                }}
                onPointerDown={() => setPressedMode(id)}
                onPointerUp={() => setPressedMode(null)}
                onPointerCancel={() => setPressedMode(null)}
                className={`liquid-glass-tab ${isSelected ? "is-active" : ""} ${
                  isPressed ? "is-pressed" : ""
                }`}
              >
                {icon}
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Spatial Tracking Stage (Native 640x480 Aspect Ratio matching OpenCV Camera Stream) */}
      <div className="relative aspect-[4/3] w-full bg-[var(--bg-viewport)] ap-grid-backdrop overflow-hidden flex items-center justify-center">
        {/* Live MJPEG Stream Layer */}
        {showCameraFeed && (
          <img
            src={`${bridgeUrl}/api/camera/stream`}
            alt={mode === "overlay" ? "Camera tracking overlay showing live detected skeletons" : "Live camera stream"}
            data-testid="live-camera-stream"
            onLoad={() => onStreamStatusChange?.(true)}
            onError={() => {
              setCameraError(true);
              onStreamStatusChange?.(false);
            }}
            className={`absolute inset-0 w-full h-full object-fill ${
              mode === "overlay" ? "opacity-75" : "opacity-100"
            }`}
          />
        )}

        {/* Camera stream error fallback */}
        {((mode === "overlay" || mode === "camera") && (!connected || cameraError)) && (
          <div className="flex flex-col items-center gap-2 text-[var(--text-secondary)] p-6 text-center z-10">
            <VideoOff className="w-7 h-7 stroke-[1.4] text-[var(--text-muted)]" />
            <span className="text-xs font-mono">
              {connected ? "Camera stream unavailable" : "Engine offline · Start python main.py"}
            </span>
          </div>
        )}

        {/* Vector Landmark Overlay SVG in Native 640x480 coordinate space */}
        {showLandmarksLayer && (
          <svg
            viewBox="0 0 640 480"
            data-testid="spatial-landmarks-svg"
            className="relative z-10 w-full h-full select-none"
            role="img"
            aria-label="Camera tracking overlay showing live detected skeletons"
          >
            <defs>
              <pattern id="live-tracking-grid" width="32" height="32" patternUnits="userSpaceOnUse">
                <circle cx="1" cy="1" r="0.75" fill="var(--accent-primary)" opacity="0.12" />
              </pattern>
            </defs>

            {/* Background Grid in Landmarks Mode */}
            {mode === "landmarks" && (
              <rect width="640" height="480" fill="url(#live-tracking-grid)" />
            )}

            {/* Cardinal Calibration Frame */}
            <g
              stroke="var(--border-strong)"
              strokeWidth="1"
              fill="none"
              opacity="0.6"
            >
              <path d="M 20 40 V 20 H 40" />
              <path d="M 620 40 V 20 H 600" />
              <path d="M 20 440 V 460 H 40" />
              <path d="M 620 440 V 460 H 600" />
              <line x1="320" y1="20" x2="320" y2="460" strokeDasharray="3 6" opacity="0.25" />
              <line x1="20" y1="240" x2="620" y2="240" strokeDasharray="3 6" opacity="0.25" />
            </g>

            {/* Facial Anchor Landmarks (Lips & Ears) */}
            {faceData && faceData.detected && (
              <g className="facial-anchors">
                {/* Lip Contour Polygon */}
                {faceData.lipContour.length >= 3 && (
                  <polygon
                    points={faceData.lipContour.map((p) => `${p.x * 640},${p.y * 480}`).join(" ")}
                    fill="none"
                    stroke="#d49b56"
                    strokeWidth="1.2"
                    strokeLinejoin="round"
                    opacity="0.85"
                  />
                )}

                {/* Lip Center */}
                {faceData.lipCenter && (
                  <g
                    data-face-anchor="lip-center"
                    transform={`translate(${faceData.lipCenter.x * 640}, ${faceData.lipCenter.y * 480})`}
                  >
                    <circle r="7" fill="none" stroke="var(--status-info)" strokeWidth="1.2" />
                    <circle r="2" fill="var(--status-info)" />
                    <text
                      y="16"
                      textAnchor="middle"
                      fill="var(--status-info)"
                      fontSize="9"
                      fontFamily="IBM Plex Mono, monospace"
                      letterSpacing="0.08em"
                      opacity="0.9"
                    >
                      LIPS
                    </text>
                  </g>
                )}

                {/* Right Ear Anchor */}
                {faceData.rightEar && (
                  <g
                    data-face-anchor="right-ear"
                    transform={`translate(${faceData.rightEar.x * 640}, ${faceData.rightEar.y * 480})`}
                  >
                    <circle r="5" fill="none" stroke="#d49b56" strokeWidth="1" strokeDasharray="2 2" />
                    <circle r="1.5" fill="#d49b56" />
                    <text
                      y="-8"
                      textAnchor="middle"
                      fill="#d49b56"
                      fontSize="8"
                      fontFamily="IBM Plex Mono, monospace"
                      opacity="0.9"
                    >
                      R. EAR
                    </text>
                  </g>
                )}

                {/* Left Ear Anchor */}
                {faceData.leftEar && (
                  <g
                    data-face-anchor="left-ear"
                    transform={`translate(${faceData.leftEar.x * 640}, ${faceData.leftEar.y * 480})`}
                  >
                    <circle r="5" fill="none" stroke="#d49b56" strokeWidth="1" strokeDasharray="2 2" />
                    <circle r="1.5" fill="#d49b56" />
                    <text
                      y="-8"
                      textAnchor="middle"
                      fill="#d49b56"
                      fontSize="8"
                      fontFamily="IBM Plex Mono, monospace"
                      opacity="0.9"
                    >
                      L. EAR
                    </text>
                  </g>
                )}
              </g>
            )}

            {/* Hand Skeletons & Primary Fingertip Reticle (#8) */}
            {normalizedHands.map((hand, hIdx) => {
              const pts = hand.landmarks;
              const handName = hand.name;
              const isOwner = pointerOwner === handName || (pointerOwner === "NONE" && hand.isRight);
              const indexTip = pts[8];
              const thumbTip = pts[4];

              return (
                <g key={`hand-${handName}-${hIdx}`} data-hand-skeleton={handName} className="hand-skeleton">
                  {/* Bone Topology */}
                  {HAND_CONNECTIONS.map(([a, b]) => {
                    const p1 = pts[a];
                    const p2 = pts[b];
                    if (!p1 || !p2) return null;
                    return (
                      <line
                        key={`bone-${a}-${b}`}
                        x1={p1.x * 640}
                        y1={p1.y * 480}
                        x2={p2.x * 640}
                        y2={p2.y * 480}
                        stroke={isOwner ? "var(--accent-primary)" : "#6b8a7c"}
                        strokeWidth={isOwner ? "2" : "1.6"}
                        strokeOpacity="0.88"
                        strokeLinecap="round"
                      />
                    );
                  })}

                  {/* Thumb-Index Pinch Vector Line */}
                  {indexTip && thumbTip && (
                    <line
                      data-testid={`pinch-vector-${hIdx}`}
                      x1={thumbTip.x * 640}
                      y1={thumbTip.y * 480}
                      x2={indexTip.x * 640}
                      y2={indexTip.y * 480}
                      stroke="var(--status-warning)"
                      strokeWidth="1.75"
                      strokeDasharray="4 3"
                    />
                  )}

                  {/* Joint Nodes */}
                  {pts.map((pt, jIdx) => {
                    const isTip = jIdx === 4 || jIdx === 8 || jIdx === 12 || jIdx === 16 || jIdx === 20;
                    const isIndexTip = jIdx === 8;
                    const r = isIndexTip && isOwner ? 4.5 : isTip ? 3.5 : 2.5;

                    return (
                      <g key={`joint-${jIdx}`}>
                        <circle
                          data-landmark-index={jIdx}
                          cx={pt.x * 640}
                          cy={pt.y * 480}
                          r={r}
                          fill={jIdx === 8 ? "var(--accent-primary)" : jIdx === 4 ? "var(--status-warning)" : "#ffffff"}
                          stroke="rgba(18, 19, 22, 0.85)"
                          strokeWidth="1"
                        />

                        {/* Landmark 8 Index-Fingertip Concentric Target Ring */}
                        {isIndexTip && (
                          <g
                            className="index-target-ring"
                            pointerEvents="none"
                            data-testid="tracked-fingertip-reticle"
                            data-landmark-reticle="8"
                          >
                            {/* Subtle dark backdrop halos */}
                            <circle
                              cx={pt.x * 640}
                              cy={pt.y * 480}
                              r={isLocked ? "14.5" : isClickConfirmed ? "14" : isCandidate ? "13.5" : "12.5"}
                              fill="none"
                              stroke="rgba(18, 19, 22, 0.75)"
                              strokeWidth="3.2"
                            />
                            <circle
                              cx={pt.x * 640}
                              cy={pt.y * 480}
                              r={isLocked ? "7.5" : isClickConfirmed ? "7.5" : isCandidate ? "7.5" : "6.5"}
                              fill="none"
                              stroke="rgba(18, 19, 22, 0.75)"
                              strokeWidth="3.0"
                            />

                            {/* Concentric Outer Ring */}
                            <circle
                              cx={pt.x * 640}
                              cy={pt.y * 480}
                              r={isLocked ? "14.5" : isClickConfirmed ? "14" : isCandidate ? "13.5" : "12.5"}
                              fill="none"
                              stroke={isLocked ? "#d49b56" : isClickConfirmed ? "#ffffff" : isCandidate ? "#d49b56" : "var(--accent-primary)"}
                              strokeWidth={isClickConfirmed ? "1.8" : isLocked ? "1.5" : "1.2"}
                              opacity="0.95"
                            />

                            {/* Concentric Inner Ring */}
                            <circle
                              cx={pt.x * 640}
                              cy={pt.y * 480}
                              r={isLocked ? "7.5" : isClickConfirmed ? "7.5" : isCandidate ? "7.5" : "6.5"}
                              fill="none"
                              stroke={isLocked ? "#d49b56" : isClickConfirmed ? "#ffffff" : isCandidate ? "#d49b56" : "var(--accent-primary)"}
                              strokeWidth={isClickConfirmed ? "1.6" : "1.1"}
                              strokeDasharray={isCandidate ? "2 2" : undefined}
                              opacity="0.92"
                            />

                            {/* Center Dot Target Anchor */}
                            <circle
                              cx={pt.x * 640}
                              cy={pt.y * 480}
                              r={isClickConfirmed ? "2.2" : "1.5"}
                              fill={isLocked ? "#d49b56" : isClickConfirmed ? "#ffffff" : isCandidate ? "#d49b56" : "var(--accent-primary)"}
                            />

                            {/* 4 Cardinal Reticle Ticks when Locked */}
                            {isLocked && (
                              <g stroke="#d49b56" strokeWidth="1.2" opacity="0.95">
                                <line x1={pt.x * 640 - 18} y1={pt.y * 480} x2={pt.x * 640 - 14.5} y2={pt.y * 480} />
                                <line x1={pt.x * 640 + 14.5} y1={pt.y * 480} x2={pt.x * 640 + 18} y2={pt.y * 480} />
                                <line x1={pt.x * 640} y1={pt.y * 480 - 18} x2={pt.x * 640} y2={pt.y * 480 - 14.5} />
                                <line x1={pt.x * 640} y1={pt.y * 480 + 14.5} x2={pt.x * 640} y2={pt.y * 480 + 18} />
                              </g>
                            )}

                            {/* Coordinate readout */}
                            <text
                              x={pt.x * 640 + 18}
                              y={pt.y * 480 - 10}
                              fill="#f8fafc"
                              fontSize="11"
                              fontFamily="IBM Plex Mono, monospace"
                              fontWeight="600"
                            >
                              {handName} #8 ({Math.round(pt.x * 100)}%, {Math.round(pt.y * 100)}%)
                            </text>
                          </g>
                        )}
                      </g>
                    );
                  })}

                  {/* Wrist Label */}
                  {pts[0] && (
                    <text
                      x={pts[0].x * 640}
                      y={pts[0].y * 480 + 18}
                      textAnchor="middle"
                      fill={isOwner ? "var(--accent-primary)" : "#6b8a7c"}
                      fontSize="10"
                      fontFamily="IBM Plex Mono, monospace"
                      letterSpacing="0.08em"
                      opacity="0.9"
                    >
                      {handName} HAND {isOwner ? "(CURSOR)" : ""}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Awaiting Hands Scanning Graphic — only when connected to avoid text collision with offline overlay */}
            {connected && !hasHands && (
              <g className="scanning-state">
                <circle cx="320" cy="240" r="38" fill="none" stroke="var(--accent-primary)" strokeWidth="1" opacity="0.35" />
                <circle cx="320" cy="240" r="68" fill="none" stroke="var(--accent-primary)" strokeWidth="1" strokeDasharray="4 6" opacity="0.2" />
                <text
                  x="320"
                  y="244"
                  textAnchor="middle"
                  fill="var(--accent-primary)"
                  fontSize="11"
                  fontFamily="IBM Plex Mono, monospace"
                  letterSpacing="0.1em"
                  opacity="0.8"
                >
                  {isPaused ? "TRACKING PAUSED" : "SCANNING FOR HANDS"}
                </text>
              </g>
            )}
          </svg>
        )}

        {/* Small Readable Status Badges in top-left in Overlay Mode */}
        {mode === "overlay" && (
          <div className="absolute top-2 left-2 flex flex-col gap-1 pointer-events-none z-20">
            <div className="flex items-center gap-1.5 bg-black/75 px-2 py-0.5 rounded text-[10px] font-mono border border-white/10 backdrop-blur-xs">
              <span className={`w-1.5 h-1.5 rounded-full ${hasRightHand ? "bg-[var(--accent-primary)]" : "bg-neutral-600"}`} />
              <span className={hasRightHand ? "text-[var(--accent-primary)]" : "text-neutral-400"}>
                R. HAND: {hasRightHand ? "DETECTED" : "SEARCHING"}
              </span>
            </div>
            <div className="flex items-center gap-1.5 bg-black/75 px-2 py-0.5 rounded text-[10px] font-mono border border-white/10 backdrop-blur-xs">
              <span className={`w-1.5 h-1.5 rounded-full ${hasLeftHand ? "bg-[var(--status-info)]" : "bg-neutral-600"}`} />
              <span className={hasLeftHand ? "text-[var(--status-info)]" : "text-neutral-400"}>
                L. HAND: {hasLeftHand ? "DETECTED" : "SEARCHING"}
              </span>
            </div>
            {faceData?.detected && (
              <div className="flex items-center gap-1.5 bg-black/75 px-2 py-0.5 rounded text-[10px] font-mono border border-white/10 backdrop-blur-xs">
                <span className="w-1.5 h-1.5 rounded-full bg-[#d49b56]" />
                <span className="text-[#d49b56]">FACE ANCHORS: LOCKED</span>
              </div>
            )}
          </div>
        )}

        {/* Privacy Watermarks */}
        {mode === "overlay" && (
          <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between pointer-events-none z-20">
            <span className="inline-flex items-center gap-1 text-[10px] font-mono bg-black/70 text-[var(--accent-primary)] px-2 py-0.5 rounded border border-[var(--accent-border)]">
              <ShieldCheck className="w-3.5 h-3.5 text-[var(--accent-primary)]" />
              Local device only · Real-time MediaPipe overlay
            </span>
            <span className="text-[10px] font-mono text-white/60 bg-black/70 px-1.5 py-0.5 rounded">
              LIVE OVERLAY
            </span>
          </div>
        )}

        {mode === "camera" && (
          <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between pointer-events-none z-20">
            <span className="inline-flex items-center gap-1 text-[10px] font-mono bg-black/70 text-[var(--accent-primary)] px-2 py-0.5 rounded border border-[var(--accent-border)]">
              <ShieldCheck className="w-3.5 h-3.5 text-[var(--accent-primary)]" />
              Local device only · Never stored or transmitted externally
            </span>
            <span className="text-[10px] font-mono text-white/60 bg-black/70 px-1.5 py-0.5 rounded">
              MAX 15 FPS
            </span>
          </div>
        )}

        {/* Purposeful Offline Guidance Overlay in landmarks mode when offline */}
        {!connected && !hasHands && mode === "landmarks" && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center p-6 text-center bg-black/65">
            <div className="w-14 h-14 rounded-full border border-[var(--border-strong)] bg-[var(--bg-surface)] flex items-center justify-center mb-3">
              <Terminal className="w-6 h-6 text-[var(--accent-primary)]" />
            </div>
            <div className="text-sm font-mono font-semibold tracking-wide text-white uppercase">
              ENGINE OFFLINE — NO LIVE FEED
            </div>
            <p className="text-xs text-slate-300 max-w-md mt-1.5">
              Start the Python computer-vision engine to stream live MediaPipe hand landmarks, facial anchors, and webcam frames over{" "}
              <code className="text-[var(--accent-primary)]">127.0.0.1:8765</code>.
            </p>
            <div className="mt-3 px-3 py-1.5 rounded bg-[var(--bg-surface)] border border-[var(--border-default)] font-mono text-xs text-[var(--accent-primary)]">
              python main.py
            </div>
          </div>
        )}
      </div>

      {/* Bottom Viewport Telemetry Footer */}
      <div className="px-4 py-2.5 border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] flex flex-wrap items-center justify-between gap-3 text-xs font-mono text-[var(--text-secondary)]">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                hasHands ? "bg-[var(--accent-primary)]" : "bg-[var(--text-muted)]"
              }`}
            />
            Hand landmarks ({hasHands ? `${normalizedHands.length} tracked` : "Searching"})
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                faceData && faceData.detected ? "bg-[var(--status-info)]" : "bg-[var(--text-muted)]"
              }`}
            />
            Facial anchors ({faceData && faceData.detected ? "Locked" : "Ready"})
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span>Click state: {clickState.toUpperCase()}</span>
          <span>{connected ? (isRunning ? "LIVE" : "PAUSED") : "Standby"}</span>
        </div>
      </div>
    </div>
  );
};
