import { motion, useReducedMotion } from "framer-motion";
import { perimeterPath, stadiumPoint, shellPoint, shellSegmentPath, fonts } from "./studio";
import { Type, Grid3X3, type LucideIcon } from "lucide-react";

export type ShellOption = {
  label: string;
  icon?: LucideIcon | undefined;
  colour?: string | undefined;
  selected?: boolean | undefined;
  disabled?: boolean | undefined;
  onSelect: () => void;
};

// Perimeter length and normalized landmark coordinates
const L = 640 + 300 * Math.PI;
const T1 = 320 / L; // ~0.202215 (top-right corner)
const T_top_mid = T1 / 2; // ~0.101107 (top-center)
const T2 = 0.5; // (bottom-right corner)
const T3 = (640 + 150 * Math.PI) / L; // ~0.702215 (bottom-left corner)
const T_bottom_mid = T2 + T_top_mid; // ~0.601107 (bottom-center)
const T_right_mid = T1 + (T2 - T1) / 2; // ~0.351107 (right midpoint)
const T_left_mid = T3 + (1.0 - T3) / 2; // ~0.851107 (left midpoint)

const BOUNDS_6 = [0, T_top_mid, T1, T2, T_bottom_mid, T3, 1.0];
const BOUNDS_5 = [0, T_top_mid, T1, T2 + T1 / 3, T2 + 2 * T1 / 3, 1.0];
const BOUNDS_3 = [0, T_top_mid, T1, 1.0];
const BOUNDS_2: [number, number][] = [
  [T_left_mid, T_right_mid],
  [T_right_mid, T_left_mid],
];

const BOUNDS_10 = [
  0,
  0.2022 / 4,
  (2 * 0.2022) / 4,
  (3 * 0.2022) / 4,
  0.2022,
  0.5,
  0.5 + 0.2022 / 4,
  0.5 + (2 * 0.2022) / 4,
  0.5 + (3 * 0.2022) / 4,
  0.7022,
  1.0,
];

const BOUNDS_18 = [
  0,
  0.22 / 6,
  (2 * 0.22) / 6,
  (3 * 0.22) / 6,
  (4 * 0.22) / 6,
  (5 * 0.22) / 6,
  0.22,
  0.22 + (0.45 - 0.22) / 2,
  0.45,
  0.45 + (0.75 - 0.45) / 8,
  0.45 + (2 * (0.75 - 0.45)) / 8,
  0.45 + (3 * (0.75 - 0.45)) / 8,
  0.45 + (4 * (0.75 - 0.45)) / 8,
  0.45 + (5 * (0.75 - 0.45)) / 8,
  0.45 + (6 * (0.75 - 0.45)) / 8,
  0.45 + (7 * (0.75 - 0.45)) / 8,
  0.75,
  0.75 + (1.0 - 0.75) / 2,
  1.0,
];

// Mathematically computed true 2D centroids for every segment geometry
const CENTROIDS_2 = [
  { cx: 430.0, cy: 118.5 }, // Top option (Surface, Notifications: On)
  { cx: 430.0, cy: 361.5 }, // Bottom option (Lighting, Completion-message duration)
];

const CENTROIDS_3 = [
  { cx: 350.0, cy: 118.5 }, // Top-left option (Classic, Font, Matte, Luminous, System)
  { cx: 510.0, cy: 118.5 }, // Top-right option (Soft square, Font Boldness, Glass, Balanced, Mono)
  { cx: 430.0, cy: 361.5 }, // Bottom option (Roundness, Font Size, Translucent, Quiet, Humanist)
];

const CENTROIDS_5 = [
  { cx: 350.0, cy: 118.5 }, // Top-left (Show HUD)
  { cx: 510.0, cy: 118.5 }, // Top-right (Countdown badge)
  { cx: 540.0, cy: 361.5 }, // Bottom-right (Auto-hide)
  { cx: 430.0, cy: 361.5 }, // Bottom-center (HUD duration)
  { cx: 320.0, cy: 361.5 }, // Bottom-left (Test countdown)
];

const CENTROIDS_6 = [
  { cx: 350.0, cy: 118.5 }, // Colour — top-left
  { cx: 510.0, cy: 118.5 }, // Text — top-right
  { cx: 700.0, cy: 240.0 }, // Material — right
  { cx: 510.0, cy: 361.5 }, // Notifications — bottom-right
  { cx: 350.0, cy: 361.5 }, // Behaviour & Timing — bottom-left
  { cx: 160.0, cy: 240.0 }, // Shape — left
];

const CENTROIDS_10 = [
  { cx: 310.0, cy: 118.5 }, // Brown
  { cx: 390.0, cy: 118.5 }, // Red
  { cx: 470.0, cy: 118.5 }, // Blue
  { cx: 550.0, cy: 118.5 }, // Neon
  { cx: 698.0, cy: 240.0 }, // More Colours (centred on segment with >= 16px clearance to capsule & shell edge)
  { cx: 550.0, cy: 361.5 }, // White
  { cx: 470.0, cy: 361.5 }, // Grey
  { cx: 390.0, cy: 361.5 }, // Gold
  { cx: 310.0, cy: 361.5 }, // Purple
  { cx: 156.0, cy: 240.0 }, // Custom (positioned with >= 20px clearance to capsule & outer ring)
];

export function SegmentedCapsuleShell({
  options,
  transitionState = "idle",
}: {
  options: ShellOption[];
  transitionState?: "entering" | "exiting" | "idle";
}) {
  const reduced = useReducedMotion();
  const extended = options.length > 10;
  const is10 = options.length === 10;

  const getSegmentBounds = (index: number): [number, number] => {
    if (options.length === 2) {
      return BOUNDS_2[index] ?? [0, 0.5];
    }
    const b = extended
      ? BOUNDS_18
      : is10
        ? BOUNDS_10
        : options.length === 6
          ? BOUNDS_6
          : options.length === 5
            ? BOUNDS_5
            : options.length === 3
              ? BOUNDS_3
              : Array.from({ length: options.length + 1 }, (_, k) => k / options.length);
    return [b[index] ?? 0, b[index + 1] ?? 1];
  };

  // Segment centroid lookup
  const getCentroid = (index: number) => {
    if (options.length === 2) return CENTROIDS_2[index] ?? { cx: 430, cy: 240 };
    if (options.length === 3) return CENTROIDS_3[index] ?? { cx: 430, cy: 240 };
    if (options.length === 5) return CENTROIDS_5[index] ?? { cx: 430, cy: 240 };
    if (options.length === 6) return CENTROIDS_6[index] ?? { cx: 430, cy: 240 };
    if (options.length === 10) return CENTROIDS_10[index] ?? { cx: 430, cy: 240 };
    const [start, end] = getSegmentBounds(index);
    const mid = end >= start ? (start + end) / 2 : (start + end + 1.0) / 2 % 1.0;
    const p = shellPoint(mid, 121.5);
    return { cx: p.x, cy: p.y };
  };

  // Animation values
  const isExiting = transitionState === "exiting";
  const isEntering = transitionState === "entering";

  return (
    <motion.svg
      className={`shell-svg ${extended ? "extended-shell" : ""} ${isExiting ? "is-exiting" : ""}`}
      viewBox="0 0 860 480"
      aria-label="Capsule options"
      initial={isEntering ? { opacity: 0.7 } : false}
      animate={{
        opacity: isExiting ? 0 : 1,
      }}
      transition={{ duration: reduced ? 0.08 : isExiting ? 0.14 : 0.22, ease: "easeOut" }}
    >
      <defs>
        <linearGradient id="shell-surface" x1="0" y1="0" x2=".3" y2="1">
          <stop stopColor="#17222e" />
          <stop offset=".3" stopColor="#070c12" />
          <stop offset=".65" stopColor="#030507" />
          <stop offset="1" stopColor="#0d1620" />
        </linearGradient>
      </defs>

      {options.map((option, i) => {
        const gapFrac = extended ? 0.0015 : 0.002;
        const [rawStart, rawEnd] = getSegmentBounds(i);
        const start = (rawStart + gapFrac) % 1.0;
        const end = (rawEnd - gapFrac + 1.0) % 1.0;

        const { cx, cy } = getCentroid(i);
        const Icon = option.icon;

        const pathD = shellSegmentPath(start, end, extended ? 166 : 165, 78);

        return (
          <motion.g
            key={option.label}
            className={`shell-option ${option.selected ? "selected" : ""}`}
            role="button"
            tabIndex={option.disabled ? -1 : 0}
            aria-disabled={option.disabled || undefined}
            aria-label={option.label}
            aria-pressed={option.selected}
            onClick={() => {
              if (!option.disabled) option.onSelect();
            }}
            onKeyDown={(e) => {
              if (option.disabled) return;
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                option.onSelect();
              }
            }}
            initial={isEntering ? { opacity: 0.8 } : false}
            animate={{ opacity: 1 }}
            transition={{ duration: reduced ? 0.08 : 0.16 }}
          >
            <path d={pathD} fill="url(#shell-surface)" strokeWidth="1" />
            {/* Minimum 44x44px touch target on mobile viewports */}
            <rect
              x={cx - 60}
              y={cy - 60}
              width={120}
              height={120}
              fill="transparent"
              pointerEvents="all"
              aria-hidden="true"
            />

            <g pointerEvents="auto">
              {/* Option Rendering by Type */}
              {extended && option.colour ? (
                (() => {
                  const fontSize = 12;
                  const dotDiameter = 6;
                  const gap = 5;
                  const textWidth = option.label.length * 6.0;
                  const groupWidth = dotDiameter + gap + textWidth;
                  const left = cx - groupWidth / 2;
                  return (
                    <g>
                      <circle
                        cx={left + dotDiameter / 2}
                        cy={cy}
                        r={dotDiameter / 2}
                        fill={option.colour}
                      />
                      {option.selected && (
                        <circle
                          cx={left + dotDiameter / 2}
                          cy={cy}
                          r={dotDiameter / 2 + 1.8}
                          fill="none"
                          stroke="#ffffff"
                          strokeWidth="1.2"
                        />
                      )}
                      <text
                        x={left + dotDiameter + gap}
                        y={cy + 4}
                        textAnchor="start"
                        className="segment-label"
                        style={{ fontSize }}
                      >
                        {option.label}
                      </text>
                    </g>
                  );
                })()
              ) : is10 && option.colour ? (
                (() => {
                  const fontSize = 13.5;
                  const dotDiameter = 7;
                  const gap = 6;
                  const textWidth = option.label.length * 7.2;
                  const groupWidth = dotDiameter + gap + textWidth;
                  const left = cx - groupWidth / 2;
                  return (
                    <g>
                      <circle
                        cx={left + dotDiameter / 2}
                        cy={cy}
                        r={dotDiameter / 2}
                        fill={option.colour}
                      />
                      {option.selected && (
                        <circle
                          cx={left + dotDiameter / 2}
                          cy={cy}
                          r={dotDiameter / 2 + 2}
                          fill="none"
                          stroke="#ffffff"
                          strokeWidth="1.2"
                        />
                      )}
                      <text
                        x={left + dotDiameter + gap}
                        y={cy + 4.5}
                        textAnchor="start"
                        className="segment-label"
                        style={{ fontSize }}
                      >
                        {option.label}
                      </text>
                    </g>
                  );
                })()
              ) : option.label === "Custom" ? (
                <g>
                  {/* Symmetric Tri-dot Icon: icon bottom at cy - 6, text top at cy + 4 (10px clear) */}
                  <g transform={`translate(${cx - 9} ${cy - 24})`}>
                    <circle cx="7" cy="3.5" r="3.8" fill="#ff5964" />
                    <circle cx="3" cy="11.5" r="3.8" fill="#54df94" />
                    <circle cx="11" cy="11.5" r="3.8" fill="#5a9dff" />
                  </g>
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Custom
                  </text>
                </g>
              ) : option.label === "More Colours" ? (
                <g>
                  <Grid3X3
                    x={cx - 9}
                    y={cy - 31.5}
                    width={18}
                    height={18}
                    strokeWidth={1.4}
                    className="segment-icon"
                  />
                  <text
                    x={cx}
                    y={cy + 8.5}
                    textAnchor="middle"
                    className="segment-label more-colours-label"
                    aria-label="More Colours"
                    style={{ pointerEvents: "auto" }}
                  >
                    <tspan x={cx} dy="0">
                      More{" "}
                    </tspan>
                    <tspan x={cx} dy="17">
                      Colours
                    </tspan>
                  </text>
                </g>
              ) : ["System", "Mono", "Humanist"].includes(option.label) ? (
                <g>
                  <text
                    x={cx}
                    y={cy - 6}
                    textAnchor="middle"
                    fill="#8ec6f5"
                    fontFamily={fonts[option.label]}
                    fontSize="17"
                    fontWeight="600"
                  >
                    Aa
                  </text>
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    {option.label}
                  </text>
                </g>
              ) : option.label === "Font" ? (
                <g>
                  <Type
                    x={cx - 10}
                    y={cy - 24}
                    width={20}
                    height={20}
                    strokeWidth={1.4}
                    className="segment-icon"
                  />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Font
                  </text>
                </g>
              ) : option.label === "Font Size" ? (
                <g>
                  <text
                    x={cx - 7}
                    y={cy - 6}
                    textAnchor="middle"
                    fill="#78b0e4"
                    fontSize="12"
                    fontWeight="400"
                  >
                    A
                  </text>
                  <text
                    x={cx + 7}
                    y={cy - 6}
                    textAnchor="middle"
                    fill="#95d0ff"
                    fontSize="18"
                    fontWeight="700"
                  >
                    A
                  </text>
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Font Size
                  </text>
                </g>
              ) : option.label === "Font Boldness" ? (
                <g>
                  <Type
                    x={cx - 10}
                    y={cy - 24}
                    width={20}
                    height={20}
                    strokeWidth={1.6}
                    className="segment-icon"
                  />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Font Boldness
                  </text>
                </g>
              ) : option.label === "Luminous" ? (
                <g>
                  <rect
                    x={cx - 15}
                    y={cy - 24}
                    width="30"
                    height="13"
                    rx="6.5"
                    fill="#0d1928"
                    stroke="#9ed0ff"
                    strokeWidth="1.5"
                    style={{ filter: "drop-shadow(0 0 6px #74b8ff)" }}
                  />
                  <circle
                    cx={cx}
                    cy={cy - 17.5}
                    r="2.5"
                    fill="#f0a83b"
                    style={{ filter: "drop-shadow(0 0 4px #f0a83b)" }}
                  />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Luminous
                  </text>
                </g>
              ) : option.label === "Balanced" ? (
                <g>
                  <rect
                    x={cx - 15}
                    y={cy - 24}
                    width="30"
                    height="13"
                    rx="6.5"
                    fill="#080e15"
                    stroke="#5b82a6"
                    strokeWidth="1.2"
                  />
                  <circle cx={cx} cy={cy - 17.5} r="2" fill="#f0a83b" />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Balanced
                  </text>
                </g>
              ) : option.label === "Quiet" ? (
                <g>
                  <rect
                    x={cx - 15}
                    y={cy - 24}
                    width="30"
                    height="13"
                    rx="6.5"
                    fill="#0a121c"
                    stroke="#5a7d9e"
                    strokeWidth="1.2"
                  />
                  <circle cx={cx} cy={cy - 17.5} r="2" fill="#d99f45" />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Quiet
                  </text>
                </g>
              ) : option.label === "Classic" ? (
                <g>
                  <rect
                    x={cx - 15}
                    y={cy - 24}
                    width="30"
                    height="14"
                    rx="7"
                    fill="none"
                    stroke="#7bb7eb"
                    strokeWidth="1.4"
                  />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Classic
                  </text>
                </g>
              ) : option.label === "Soft square" ? (
                <g>
                  <rect
                    x={cx - 12}
                    y={cy - 24}
                    width="24"
                    height="14"
                    rx="3"
                    fill="none"
                    stroke="#7bb7eb"
                    strokeWidth="1.4"
                  />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Soft square
                  </text>
                </g>
              ) : option.label === "Roundness" ? (
                <g>
                  <rect
                    x={cx - 15}
                    y={cy - 24}
                    width="30"
                    height="14"
                    rx="7"
                    fill="none"
                    stroke="#7bb7eb"
                    strokeWidth="1.4"
                    strokeDasharray="3 2"
                  />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Roundness
                  </text>
                </g>
              ) : option.label === "Glass" ? (
                <g>
                  <path
                    d="M 0,-13 C 3.5,-7 6.5,-3 6.5,1 A 6.5 6.5 0 0 1 -6.5,1 C -6.5,-3 -3.5,-7 0,-13 Z"
                    transform={`translate(${cx}, ${cy - 10})`}
                    fill="none"
                    stroke="#8ac2f2"
                    strokeWidth="1.3"
                  />
                  <path
                    d="M -2,-2 A 3.5 3.5 0 0 1 2.5,1"
                    transform={`translate(${cx}, ${cy - 10})`}
                    fill="none"
                    stroke="#ffffff"
                    strokeWidth="1"
                    strokeLinecap="round"
                  />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Glass
                  </text>
                </g>
              ) : option.label === "Translucent" ? (
                <g>
                  <rect
                    x={cx - 10}
                    y={cy - 22}
                    width="13"
                    height="13"
                    rx="2"
                    fill="rgba(100, 160, 220, 0.25)"
                    stroke="#74aede"
                    strokeWidth="1.2"
                  />
                  <rect
                    x={cx - 3}
                    y={cy - 16}
                    width="13"
                    height="13"
                    rx="2"
                    fill="rgba(140, 190, 255, 0.35)"
                    stroke="#a0ceff"
                    strokeWidth="1.2"
                  />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Translucent
                  </text>
                </g>
              ) : option.label === "Matte" ? (
                <g>
                  <circle
                    cx={cx}
                    cy={cy - 14}
                    r="7"
                    fill="#202c3a"
                    stroke="#688ca8"
                    strokeWidth="1.3"
                  />
                  <circle cx={cx} cy={cy - 14} r="4" fill="#131a22" />
                  <text x={cx} y={cy + 18} textAnchor="middle" className="segment-label">
                    Matte
                  </text>
                </g>
              ) : option.label === "Behaviour & Timing" && Icon ? (
                <g pointerEvents="auto">
                  <Icon
                    x={cx - 9}
                    y={cy - 24}
                    width={18}
                    height={18}
                    strokeWidth={1.4}
                    className="segment-icon"
                  />
                  <text x={cx} y={cy + 8} textAnchor="middle" className="segment-label">
                    <tspan x={cx} dy="0">
                      Behaviour
                    </tspan>
                    <tspan x={cx} dy="16">
                      &amp; Timing
                    </tspan>
                  </text>
                </g>
              ) : option.label === "Completion-message duration" && Icon ? (
                <g pointerEvents="auto">
                  <Icon
                    x={cx - 9}
                    y={cy - 24}
                    width={18}
                    height={18}
                    strokeWidth={1.4}
                    className="segment-icon"
                  />
                  <text x={cx} y={cy + 8} textAnchor="middle" className="segment-label">
                    <tspan x={cx} dy="0">
                      Completion-message
                    </tspan>
                    <tspan x={cx} dy="16">
                      duration
                    </tspan>
                  </text>
                </g>
              ) : Icon ? (
                <g pointerEvents="auto">
                  <Icon
                    x={cx - 9}
                    y={cy - 20}
                    width={18}
                    height={18}
                    strokeWidth={1.4}
                    className="segment-icon"
                  />
                  <text x={cx} y={cy + 16} textAnchor="middle" className="segment-label">
                    {option.label}
                  </text>
                </g>
              ) : null}

              {/* Fallback for other standard options */}
              {!(extended && option.colour) && !is10 && option.colour && (
                <circle
                  cx={cx - option.label.length * 3.7 - 10}
                  cy={cy - 1}
                  r={4.5}
                  fill={option.colour}
                />
              )}
              {!(extended && option.colour) &&
                !is10 &&
                !Icon &&
                option.label !== "Custom" &&
                option.label !== "More Colours" && (
                  <text
                    x={cx + (option.colour ? 5 : 0)}
                    y={cy + 4}
                    textAnchor="middle"
                    className="segment-label"
                  >
                    {option.label}
                  </text>
                )}

              {/* Selection indicator: placed below text baseline, never overlaps icon or text */}
              {option.selected && !option.colour && (
                <circle
                  cx={cx}
                  cy={
                    option.label === "Behaviour & Timing" ||
                    option.label === "Completion-message duration"
                      ? cy + 30
                      : cy + 27
                  }
                  r="2.5"
                  fill="#b8dfff"
                  style={{ filter: "drop-shadow(0 0 3px #8cc2f8)" }}
                />
              )}
            </g>
          </motion.g>
        );
      })}
    </motion.svg>
  );
}
