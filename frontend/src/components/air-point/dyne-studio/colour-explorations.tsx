import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  rgbHex,
  stadiumLoopBasePath,
  stadiumLoopActivePath,
  stadiumLoopFrame,
  stadiumLoopProject,
  type Settings,
} from "./studio";

type ChannelKey = keyof Settings["customRgb"];
const channels: ReadonlyArray<{
  key: ChannelKey;
  label: "R" | "G" | "B";
  accent: string;
  radius: number;
}> = [
  { key: "r", label: "R", accent: "#ff6670", radius: 172 },
  { key: "g", label: "G", accent: "#55d89a", radius: 134 },
  { key: "b", label: "B", accent: "#70aaff", radius: 96 },
];
const RGB_TICKS = 24;

export function CustomColourView({
  settings,
  transitionState = "idle",
  onChange,
  onBack,
  onDragStateChange,
}: {
  settings: Settings;
  transitionState?: "entering" | "exiting" | "idle";
  onChange: (rgb: Settings["customRgb"]) => void;
  onBack?: () => void;
  onDragStateChange?: (isDragging: boolean) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const dragging = useRef<{ key: ChannelKey; pointerId: number } | null>(null);
  const lastRgb = useRef({ ...settings.customRgb });
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastFeedbackAt = useRef(0);
  const rafId = useRef<number | null>(null);
  const latestPointer = useRef<{ clientX: number; clientY: number } | null>(null);
  const isDragStart = useRef(false);
  const [active, setActive] = useState<ChannelKey>("r");
  const [hovered, setHovered] = useState<ChannelKey | null>(null);
  const [isDraggingState, setIsDraggingState] = useState(false);
  const reduced = useReducedMotion();
  const hex = rgbHex(settings.customRgb);

  useEffect(() => {
    lastRgb.current = { ...settings.customRgb };
  }, [settings.customRgb]);
  useEffect(
    () => () => {
      if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
      if (rafId.current !== null) cancelAnimationFrame(rafId.current);
      if (typeof document !== "undefined" && document.body) {
        document.body.style.cursor = "";
      }
    },
    [],
  );

  function pulseDetent() {
    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    if (now - lastFeedbackAt.current > 35) {
      lastFeedbackAt.current = now;
      if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
        try {
          navigator.vibrate(4);
        } catch {
          /* Haptics are optional */
        }
      }
    }
  }

  function setChannel(key: ChannelKey, raw: number, tactile = false) {
    const next = Math.max(0, Math.min(255, Math.round(raw)));
    const previous = lastRgb.current[key];
    if (next === previous) return;
    if (tactile && Math.floor(previous / 16) !== Math.floor(next / 16)) pulseDetent();
    lastRgb.current = { ...lastRgb.current, [key]: next };
    onChange({ ...lastRgb.current });
  }

  function updateFromPointer(
    e: ReactPointerEvent<SVGElement> | { clientX: number; clientY: number },
    key: ChannelKey,
  ) {
    const matrix = svg.current?.getScreenCTM();
    if (!matrix) return;
    let localX = e.clientX;
    let localY = e.clientY;
    if (typeof DOMPoint !== "undefined") {
      const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse());
      localX = pt.x;
      localY = pt.y;
    } else if (svg.current && typeof svg.current.createSVGPoint === "function") {
      const pt = svg.current.createSVGPoint();
      pt.x = e.clientX;
      pt.y = e.clientY;
      const transformed = pt.matrixTransform(matrix.inverse());
      localX = transformed.x;
      localY = transformed.y;
    }
    const channel = channels.find((c) => c.key === key);
    if (!channel) return;
    const rawFrac = stadiumLoopProject(localX, localY, channel.radius);
    let nextVal = Math.round(rawFrac * 255);
    const prevVal = lastRgb.current[key];

    // Anti-wrap clamp across 0/255 seam during active drag
    if (!isDragStart.current) {
      if (prevVal < 48 && nextVal > 200) nextVal = 0;
      else if (prevVal > 200 && nextVal < 48) nextVal = 255;
    }
    isDragStart.current = false;

    setChannel(key, nextVal, true);
  }

  function beginDrag(e: ReactPointerEvent<SVGElement>, key: ChannelKey) {
    e.preventDefault();
    e.stopPropagation();
    if (dragging.current) return;
    dragging.current = { key, pointerId: e.pointerId };
    isDragStart.current = true;
    setActive(key);
    setIsDraggingState(true);
    onDragStateChange?.(true);
    if (typeof document !== "undefined" && document.body) {
      document.body.style.cursor = "grabbing";
    }
    try {
      svg.current?.setPointerCapture(e.pointerId);
    } catch {
      /* synthetic events */
    }
    updateFromPointer(e, dragging.current.key);
  }

  function finishDrag(e: ReactPointerEvent<SVGElement>) {
    if (dragging.current?.pointerId !== e.pointerId) return;
    dragging.current = null;
    setIsDraggingState(false);
    onDragStateChange?.(false);
    if (typeof document !== "undefined" && document.body) {
      document.body.style.cursor = "";
    }
    if (rafId.current !== null) {
      cancelAnimationFrame(rafId.current);
      rafId.current = null;
    }
    try {
      if (svg.current?.hasPointerCapture(e.pointerId))
        svg.current.releasePointerCapture(e.pointerId);
    } catch {
      /* capture already released */
    }
  }

  function handleKeyDown(e: ReactKeyboardEvent<SVGGElement>, key: ChannelKey) {
    if (
      [
        "ArrowUp",
        "ArrowRight",
        "ArrowDown",
        "ArrowLeft",
        "Home",
        "End",
        "PageUp",
        "PageDown",
      ].includes(e.key)
    ) {
      e.preventDefault();
      e.stopPropagation();
      setActive(key);
      const current = settings.customRgb[key];
      const delta =
        e.key === "PageUp"
          ? 16
          : e.key === "PageDown"
            ? -16
            : ["ArrowUp", "ArrowRight"].includes(e.key)
              ? 1
              : ["ArrowDown", "ArrowLeft"].includes(e.key)
                ? -1
                : 0;
      setChannel(key, e.key === "Home" ? 0 : e.key === "End" ? 255 : current + delta, true);
    }
  }

  const isExiting = transitionState === "exiting";
  const isEntering = transitionState === "entering";

  return (
    <motion.div
      className={`colour-exploration ${isExiting ? "is-exiting" : ""} ${isDraggingState ? "is-dragging" : ""}`}
      aria-label="Custom RGB colour mixer"
      initial={isEntering ? { opacity: 0 } : false}
      animate={{ opacity: isExiting ? 0 : 1 }}
      transition={{ duration: reduced ? 0.1 : isExiting ? 0.18 : 0.32 }}
    >
      {/* Readout pill with text size >= 12px, centered with x: -50% to prevent transform clobber */}
      <motion.div
        className="rgb-readout"
        aria-live="polite"
        initial={isEntering ? { opacity: 0, x: "-50%", y: -6 } : { x: "-50%" }}
        animate={{ opacity: 1, x: "-50%", y: 0 }}
        style={{ left: "50%" }}
        transition={{ delay: reduced ? 0 : 0.16, duration: 0.2 }}
      >
        <div className="rgb-fields">
          {channels.map((channel) => (
            <label
              key={channel.key}
              className={active === channel.key ? "is-active" : ""}
              style={{ "--channel-accent": channel.accent } as CSSProperties}
            >
              <span>{channel.label}</span>
              <input
                aria-label={`${channel.label} value`}
                type="number"
                min={0}
                max={255}
                step={1}
                value={settings.customRgb[channel.key]}
                onFocus={() => setActive(channel.key)}
                onChange={(e) => setChannel(channel.key, Number(e.target.value) || 0)}
              />
            </label>
          ))}
        </div>
        <div className="rgb-hex">
          <span>HEX</span>
          <strong>{hex}</strong>
          <i style={{ background: hex, color: hex }} aria-hidden="true" />
        </div>
      </motion.div>

      <svg
        ref={svg}
        className="custom-rgb-svg"
        viewBox="0 0 860 480"
        role="group"
        aria-label="Three independent RGB adjustment rings"
        onPointerMove={(e) => {
          if (dragging.current?.pointerId === e.pointerId) {
            latestPointer.current = { clientX: e.clientX, clientY: e.clientY };
            if (rafId.current === null) {
              rafId.current = requestAnimationFrame(() => {
                rafId.current = null;
                if (dragging.current && latestPointer.current) {
                  updateFromPointer(latestPointer.current, dragging.current.key);
                }
              });
            }
          }
        }}
        onPointerUp={finishDrag}
        onPointerCancel={finishDrag}
        onLostPointerCapture={() => {
          dragging.current = null;
          setIsDraggingState(false);
          onDragStateChange?.(false);
          if (typeof document !== "undefined" && document.body) {
            document.body.style.cursor = "";
          }
        }}
      >
        <defs>
          <filter id="rgb-ring-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {channels.map((channel, cIdx) => {
          const val = settings.customRgb[channel.key];
          const fraction = val / 255;
          const frame = stadiumLoopFrame(fraction, channel.radius);
          const isHovered = hovered === channel.key;
          const isDraggingThis = dragging.current?.key === channel.key;
          const isActive = active === channel.key;
          const isVisualActive = isActive || isHovered || isDraggingThis;

          // Floating badge appears ONLY for the actively dragged channel
          const showBadge = isDraggingThis;

          // Position handle badge safely outward along normal, avoiding capsule & other rings
          const badgeWidth = 52;
          const badgeHeight = 22;
          let badgeX = frame.x + frame.nx * 26 - badgeWidth / 2;
          let badgeY = frame.y + frame.ny * 26 - badgeHeight / 2;
          badgeX = Math.max(8, Math.min(860 - badgeWidth - 8, badgeX));
          badgeY = Math.max(8, Math.min(480 - badgeHeight - 8, badgeY));

          const p0 = stadiumLoopFrame(0, channel.radius);
          const p255 = stadiumLoopFrame(1, channel.radius);

          return (
            <motion.g
              key={channel.key}
              className={`rgb-ring rgb-ring-${channel.key} ${isVisualActive ? "is-active" : ""}`}
              initial={isEntering ? { opacity: 0 } : false}
              animate={{ opacity: 1 }}
              transition={{ delay: reduced ? 0 : cIdx * 0.04, duration: 0.2 }}
            >
              {/* Closed base track with distinct gap */}
              <path
                d={stadiumLoopBasePath(channel.radius)}
                className="rgb-track-base"
                style={{ stroke: channel.accent }}
              />

              {/* Active arc from 0 to current value */}
              <path
                d={stadiumLoopActivePath(fraction, channel.radius)}
                className="rgb-track-active"
                style={{
                  stroke: channel.accent,
                  filter: isVisualActive
                    ? `drop-shadow(0 0 7px ${channel.accent}bb)`
                    : `drop-shadow(0 0 3px ${channel.accent}55)`,
                }}
              />

              {/* Ticks along the stadium track */}
              {Array.from({ length: RGB_TICKS }, (_, i) => {
                const tickFrame = stadiumLoopFrame(i / (RGB_TICKS - 1), channel.radius);
                const p = { x: tickFrame.x - tickFrame.nx * 4, y: tickFrame.y - tickFrame.ny * 4 };
                const q = { x: tickFrame.x + tickFrame.nx * 4, y: tickFrame.y + tickFrame.ny * 4 };
                return (
                  <path
                    key={i}
                    d={`M ${p.x} ${p.y} L ${q.x} ${q.y}`}
                    className="rgb-tick"
                    style={{ stroke: channel.accent }}
                  />
                );
              })}

              {/* Compact end stop labels on outer track only to avoid clustering */}
              {cIdx === 0 && (
                <g className="rgb-end-stops" pointerEvents="none" opacity={0.65}>
                  <text
                    x={p0.x + 4}
                    y={p0.y + 14}
                    fill={channel.accent}
                    fontSize={10}
                    fontFamily="'Courier New', monospace"
                  >
                    0
                  </text>
                  <text
                    x={p255.x - 22}
                    y={p255.y + 14}
                    fill={channel.accent}
                    fontSize={10}
                    fontFamily="'Courier New', monospace"
                  >
                    255
                  </text>
                </g>
              )}

              {/* Track hit area */}
              <path
                d={stadiumLoopBasePath(channel.radius)}
                className="rgb-track-hit"
                onPointerDown={(e) => beginDrag(e, channel.key)}
                onMouseEnter={() => setHovered(channel.key)}
                onMouseLeave={() => setHovered((h) => (h === channel.key ? null : h))}
              />

              {/* Handle transparent hit area */}
              <circle
                cx={frame.x}
                cy={frame.y}
                r={22}
                className="rgb-handle-hit"
                onPointerDown={(e) => beginDrag(e, channel.key)}
                onMouseEnter={() => setHovered(channel.key)}
                onMouseLeave={() => setHovered((h) => (h === channel.key ? null : h))}
              />

              {/* Precision Handle: fades in after ring is rendered */}
              <motion.g
                className="rgb-handle-group"
                tabIndex={0}
                role="slider"
                aria-label={`${channel.label} channel`}
                aria-valuemin={0}
                aria-valuemax={255}
                aria-valuenow={val}
                aria-valuetext={`${channel.label} ${val}`}
                onPointerDown={(e) => beginDrag(e, channel.key)}
                onKeyDown={(e) => handleKeyDown(e, channel.key)}
                onMouseEnter={() => setHovered(channel.key)}
                onMouseLeave={() => setHovered((h) => (h === channel.key ? null : h))}
                initial={isEntering ? { opacity: 0 } : false}
                animate={{ opacity: 1 }}
                transition={
                  isDraggingThis ? { duration: 0 } : { delay: reduced ? 0 : 0.16, duration: 0.18 }
                }
              >
                <circle
                  cx={frame.x}
                  cy={frame.y}
                  r={12}
                  className="rgb-handle-halo"
                  style={{ stroke: channel.accent, opacity: isVisualActive ? 0.45 : 0.15 }}
                />
                <circle
                  cx={frame.x}
                  cy={frame.y}
                  r={8.5}
                  className="rgb-handle-body"
                  style={{ stroke: "#ffffff", fill: channel.accent }}
                />
                <circle cx={frame.x} cy={frame.y} r={3} fill="#ffffff" />
              </motion.g>

              {/* Floating badge rendered ONLY for the actively dragged channel */}
              {showBadge && (
                <g
                  className="rgb-handle-badge"
                  pointerEvents="none"
                  transform={`translate(${badgeX}, ${badgeY})`}
                >
                  <rect
                    width={badgeWidth}
                    height={badgeHeight}
                    rx={6}
                    fill="#060c14EE"
                    stroke={channel.accent}
                    strokeWidth={1}
                  />
                  <text
                    x={8}
                    y={15}
                    fill={channel.accent}
                    fontSize={12}
                    fontFamily="'Courier New', monospace"
                    fontWeight="bold"
                  >
                    {channel.label}
                  </text>
                  <text
                    x={24}
                    y={15}
                    fill="#ffffff"
                    fontSize={12}
                    fontFamily="'Courier New', monospace"
                  >
                    {val}
                  </text>
                </g>
              )}
            </motion.g>
          );
        })}
      </svg>
    </motion.div>
  );
}
