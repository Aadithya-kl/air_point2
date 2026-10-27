import { useEffect, useRef, type PointerEvent as ReactPointerEvent } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  stadiumTrackFrame,
  stadiumTrackPoint,
  stadiumTrackPath,
  stadiumTrackProject,
} from "./studio";

type Props = {
  title: string;
  value: number;
  min: number;
  max: number;
  midpoint: number;
  step: number;
  unit: string;
  radius?: number;
  accent?: string;
  transitionState?: "entering" | "exiting" | "idle";
  onDragStateChange?: (isDragging: boolean) => void;
  onChange: (value: number) => void;
};

export function CapsuleAdjustmentTrack({
  title,
  value,
  min,
  max,
  midpoint,
  step,
  unit,
  radius = 132,
  accent = "#79bcff",
  transitionState = "idle",
  onDragStateChange,
  onChange,
}: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const dragging = useRef<{ pointerId: number } | null>(null);
  const lastValue = useRef(value);
  const lastFeedbackAt = useRef(0);
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reduced = useReducedMotion();
  const fraction = max === min ? 0 : Math.min(1, Math.max(0, (value - min) / (max - min)));
  const tactileStep = Math.max(step, Math.ceil((max - min) / 16 / step) * step);
  const ticks = Math.min(
    20,
    Math.max(1, Math.round((max - min) / Math.max(step, (max - min) / 20))),
  );
  const midpointIndex = Math.round(((midpoint - min) / (max - min)) * ticks);
  const point = stadiumTrackPoint(fraction, radius);
  const formatValue = (v: number) => (unit === "%" ? `${v}%` : unit ? `${v} ${unit}` : `${v}`);

  useEffect(() => {
    lastValue.current = value;
  }, [value]);
  useEffect(
    () => () => {
      if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    },
    [],
  );

  function pulseDetent() {
    const element = svg.current;
    if (element) {
      element.classList.remove("is-detent");
      void element.getBoundingClientRect();
      element.classList.add("is-detent");
      if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
      feedbackTimer.current = setTimeout(() => element.classList.remove("is-detent"), 115);
    }
    const now = typeof performance !== "undefined" ? performance.now() : Date.now();
    if (now - lastFeedbackAt.current > 35) {
      lastFeedbackAt.current = now;
      if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
        try {
          navigator.vibrate(4);
        } catch {
          /* Optional haptics */
        }
      }
    }
  }

  function commit(rawValue: number) {
    const next = Math.min(max, Math.max(min, min + Math.round((rawValue - min) / step) * step));
    const previous = lastValue.current;
    if (next === previous) return;
    if (
      Math.floor((next - min) / tactileStep) !== Math.floor((previous - min) / tactileStep) ||
      next === min ||
      next === max
    )
      pulseDetent();
    lastValue.current = next;
    onChange(next);
  }

  function update(e: Pick<PointerEvent, "clientX" | "clientY">) {
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
    const t = stadiumTrackProject(localX, localY, radius);
    commit(min + t * (max - min));
  }

  function beginDrag(e: ReactPointerEvent<SVGElement>) {
    e.preventDefault();
    e.stopPropagation();
    if (dragging.current) return;
    dragging.current = { pointerId: e.pointerId };
    onDragStateChange?.(true);
    try {
      svg.current?.setPointerCapture(e.pointerId);
    } catch {
      /* synthetic test events */
    }
    update(e);
  }

  function finishDrag(e: ReactPointerEvent<SVGElement>) {
    if (dragging.current?.pointerId !== e.pointerId) return;
    dragging.current = null;
    onDragStateChange?.(false);
    try {
      if (svg.current?.hasPointerCapture(e.pointerId))
        svg.current.releasePointerCapture(e.pointerId);
    } catch {
      /* browser release */
    }
  }

  const isExiting = transitionState === "exiting";
  const isEntering = transitionState === "entering";

  return (
    <motion.div
      className={`adjustment-layer ${isExiting ? "is-exiting" : ""}`}
      initial={isEntering ? { opacity: 0 } : false}
      animate={{ opacity: isExiting ? 0 : 1 }}
      transition={{ duration: reduced ? 0.1 : isExiting ? 0.18 : 0.32, ease: "easeOut" }}
    >
      <svg
        ref={svg}
        className="track-svg"
        viewBox="0 0 860 480"
        onPointerDown={beginDrag}
        onPointerMove={(e) => {
          if (dragging.current?.pointerId === e.pointerId) update(e);
        }}
        onPointerUp={finishDrag}
        onPointerCancel={(e) => {
          if (dragging.current?.pointerId === e.pointerId) finishDrag(e);
        }}
        onLostPointerCapture={() => {
          dragging.current = null;
          onDragStateChange?.(false);
        }}
      >
        {/* Rail draws / fades in first */}
        <motion.g
          initial={isEntering ? { opacity: 0 } : false}
          animate={{ opacity: 1 }}
          transition={{ duration: reduced ? 0.1 : 0.2 }}
        >
          <path d={stadiumTrackPath(0, 1, radius)} className="track-base" />
          <path
            d={stadiumTrackPath(0, fraction, radius)}
            className="track-active"
            style={{ stroke: accent, filter: `drop-shadow(0 0 5px ${accent}88)` }}
          />

          {Array.from({ length: ticks + 1 }, (_, i) => {
            const t = i / ticks;
            const frame = stadiumTrackFrame(t, radius);
            const p = { x: frame.x - frame.nx * 9, y: frame.y - frame.ny * 9 };
            const q = { x: frame.x + frame.nx * 9, y: frame.y + frame.ny * 9 };
            // Tick label placed radially along tick normal with extra clearance at end stops (preventing handle overlap)
            const isEnd = i === 0 || i === ticks;
            const offsetDist = isEnd ? 35 : 26;
            const label = {
              x: frame.x + frame.nx * offsetDist,
              y: frame.y + frame.ny * offsetDist,
            };
            const isLabelled = i === 0 || i === midpointIndex || i === ticks;
            const labelValue = i === 0 ? min : i === ticks ? max : midpoint;
            return (
              <g
                key={i}
                className="track-tick"
                onPointerDown={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  commit(min + t * (max - min));
                }}
              >
                <path
                  d={`M ${p.x} ${p.y} L ${q.x} ${q.y}`}
                  className={t <= fraction ? "tick-active" : "tick-inactive"}
                />
                {isLabelled && (
                  <text
                    x={label.x}
                    y={label.y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    className="tick-label"
                  >
                    {formatValue(labelValue)}
                  </text>
                )}
              </g>
            );
          })}
        </motion.g>

        {/* Rail hit area */}
        <path d={stadiumTrackPath(0, 1, radius)} className="track-hit" onPointerDown={beginDrag} />

        {/* Handle ONLY appears once the rail is already visible (delay: 0.18s), never before the rail */}
        <motion.g
          initial={isEntering ? { opacity: 0, scale: 0.7 } : false}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: reduced ? 0 : 0.18, duration: 0.18 }}
        >
          <circle
            aria-hidden="true"
            cx={point.x}
            cy={point.y}
            r={22}
            className="track-handle-hit"
            onPointerDown={beginDrag}
          />
          <circle
            role="slider"
            aria-label={title}
            aria-valuemin={min}
            aria-valuemax={max}
            aria-valuenow={value}
            aria-valuetext={formatValue(value)}
            tabIndex={0}
            cx={point.x}
            cy={point.y}
            r={10.5}
            className="track-handle"
            style={{ fill: accent, filter: `drop-shadow(0 0 7px ${accent})` }}
            onPointerDown={beginDrag}
            onKeyDown={(e) => {
              if (
                ["ArrowUp", "ArrowRight", "ArrowDown", "ArrowLeft", "Home", "End"].includes(e.key)
              ) {
                e.preventDefault();
                commit(
                  e.key === "Home"
                    ? min
                    : e.key === "End"
                      ? max
                      : value + (["ArrowUp", "ArrowRight"].includes(e.key) ? step : -step),
                );
              }
            }}
          />
          {/* Current value badge attached directly to the handle */}
          <g className="track-handle-badge" pointerEvents="none">
            <rect
              x={point.x - 24}
              y={point.y - 32}
              width={48}
              height={20}
              rx={10}
              fill="rgba(6, 11, 18, 0.94)"
              stroke={accent}
              strokeWidth={1}
            />
            <text
              x={point.x}
              y={point.y - 21}
              textAnchor="middle"
              dominantBaseline="central"
              fill="#ffffff"
              fontSize={12}
              fontWeight={600}
              fontFamily="'Courier New', monospace"
            >
              {formatValue(value)}
            </text>
          </g>
        </motion.g>
      </svg>

      {/* Adjustment readout header: centered at 50% with x: -50% to prevent transform clobber */}
      <motion.div
        className="adjustment-header"
        initial={isEntering ? { opacity: 0, x: "-50%", y: -6 } : { x: "-50%" }}
        animate={{ opacity: 1, x: "-50%", y: 0 }}
        style={{ left: "50%" }}
        transition={{ delay: reduced ? 0 : 0.16, duration: 0.2 }}
      >
        <span>
          {title}
          {["Glass", "Matte", "Translucent"].includes(title) ? " intensity" : ""}
        </span>
        <strong aria-live="polite">{formatValue(value)}</strong>
      </motion.div>
    </motion.div>
  );
}
