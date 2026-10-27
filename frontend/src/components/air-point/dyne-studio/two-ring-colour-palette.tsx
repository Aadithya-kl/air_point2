import { motion, useReducedMotion } from "framer-motion";
import { innerRingColours, outerRingColours, type Settings } from "./studio";

export type TwoRingPaletteProps = {
  settings: Settings;
  transitionState?: "entering" | "exiting" | "idle";
  onSelect: (colourName: string) => void;
  onBack?: () => void;
};

type SegmentDef = {
  name: string;
  colour: string;
  path: string;
  cx: number;
  cy: number;
};

// Stage origin: 0 0, dimensions 860x480
const YC = 240;
const XL = 266; // left stadium arc center
const XR = 594; // right stadium arc center

// Inner ring radii (mid = 91, thickness = 46)
const R1_IN = 68;
const R1_OUT = 114;

// Outer ring radii (mid = 156, thickness = 56)
const R2_IN = 128;
const R2_OUT = 184;

// Dividers & insets
const GAP = 1.4;
const c45 = Math.SQRT1_2; // cos(45 deg) = sin(45 deg)

export function TwoRingColourPalette({
  settings,
  transitionState = "idle",
  onSelect,
  onBack,
}: TwoRingPaletteProps) {
  const reduced = useReducedMotion();

  // Inner ring corners at 45 / 135 / 225 / 315 deg
  const r1OutEff = R1_OUT - GAP;
  const r1InEff = R1_IN + GAP;

  // Outer ring corners at 45 / 135 / 225 / 315 deg
  const r2OutEff = R2_OUT - GAP;
  const r2InEff = R2_IN + GAP;

  // Inner column boundaries: [XL, 348, 430, 512, XR]
  const iX1 = 348;
  const iX2 = 430;
  const iX3 = 512;

  // Outer top column boundaries: balanced cell widths across the top row
  const oX1 = 312;
  const oX2 = 430;
  const oX3 = 548;

  // ----------------------------------------------------
  // 1. INNER RING SEGMENTS (4 Top, 4 Bottom = 8 total)
  // ----------------------------------------------------
  const innerSegments: SegmentDef[] = [
    // Brown (top left, wraps 135 deg to iX1)
    {
      name: innerRingColours[0][0],
      colour: innerRingColours[0][1],
      path: `
        M ${XL - r1OutEff * c45} ${YC - r1OutEff * c45}
        A ${r1OutEff} ${r1OutEff} 0 0 1 ${XL} ${YC - r1OutEff}
        L ${iX1 - GAP} ${YC - r1OutEff}
        L ${iX1 - GAP} ${YC - r1InEff}
        L ${XL} ${YC - r1InEff}
        A ${r1InEff} ${r1InEff} 0 0 0 ${XL - r1InEff * c45} ${YC - r1InEff * c45}
        Z
      `,
      cx: 295,
      cy: YC - 91,
    },
    // Red (top mid-left, iX1 to iX2)
    {
      name: innerRingColours[1][0],
      colour: innerRingColours[1][1],
      path: `
        M ${iX1 + GAP} ${YC - r1OutEff}
        L ${iX2 - GAP} ${YC - r1OutEff}
        L ${iX2 - GAP} ${YC - r1InEff}
        L ${iX1 + GAP} ${YC - r1InEff}
        Z
      `,
      cx: (iX1 + iX2) / 2,
      cy: YC - 91,
    },
    // Blue (top mid-right, iX2 to iX3)
    {
      name: innerRingColours[2][0],
      colour: innerRingColours[2][1],
      path: `
        M ${iX2 + GAP} ${YC - r1OutEff}
        L ${iX3 - GAP} ${YC - r1OutEff}
        L ${iX3 - GAP} ${YC - r1InEff}
        L ${iX2 + GAP} ${YC - r1InEff}
        Z
      `,
      cx: (iX2 + iX3) / 2,
      cy: YC - 91,
    },
    // Neon (top right, iX3 wraps to 45 deg)
    {
      name: innerRingColours[3][0],
      colour: innerRingColours[3][1],
      path: `
        M ${iX3 + GAP} ${YC - r1OutEff}
        L ${XR} ${YC - r1OutEff}
        A ${r1OutEff} ${r1OutEff} 0 0 1 ${XR + r1OutEff * c45} ${YC - r1OutEff * c45}
        L ${XR + r1InEff * c45} ${YC - r1InEff * c45}
        A ${r1InEff} ${r1InEff} 0 0 0 ${XR} ${YC - r1InEff}
        L ${iX3 + GAP} ${YC - r1InEff}
        Z
      `,
      cx: 565,
      cy: YC - 91,
    },

    // Purple (bottom left, wraps 225 deg to iX1)
    {
      name: innerRingColours[4][0],
      colour: innerRingColours[4][1],
      path: `
        M ${XL - r1OutEff * c45} ${YC + r1OutEff * c45}
        A ${r1OutEff} ${r1OutEff} 0 0 0 ${XL} ${YC + r1OutEff}
        L ${iX1 - GAP} ${YC + r1OutEff}
        L ${iX1 - GAP} ${YC + r1InEff}
        L ${XL} ${YC + r1InEff}
        A ${r1InEff} ${r1InEff} 0 0 1 ${XL - r1InEff * c45} ${YC + r1InEff * c45}
        Z
      `,
      cx: 295,
      cy: YC + 91,
    },
    // Gold (bottom mid-left, iX1 to iX2)
    {
      name: innerRingColours[5][0],
      colour: innerRingColours[5][1],
      path: `
        M ${iX1 + GAP} ${YC + r1InEff}
        L ${iX2 - GAP} ${YC + r1InEff}
        L ${iX2 - GAP} ${YC + r1OutEff}
        L ${iX1 + GAP} ${YC + r1OutEff}
        Z
      `,
      cx: (iX1 + iX2) / 2,
      cy: YC + 91,
    },
    // Green (bottom mid-right, iX2 to iX3)
    {
      name: innerRingColours[6][0],
      colour: innerRingColours[6][1],
      path: `
        M ${iX2 + GAP} ${YC + r1InEff}
        L ${iX3 - GAP} ${YC + r1InEff}
        L ${iX3 - GAP} ${YC + r1OutEff}
        L ${iX2 + GAP} ${YC + r1OutEff}
        Z
      `,
      cx: (iX2 + iX3) / 2,
      cy: YC + 91,
    },
    // Orange (bottom right, iX3 wraps to 315 deg)
    {
      name: innerRingColours[7][0],
      colour: innerRingColours[7][1],
      path: `
        M ${iX3 + GAP} ${YC + r1InEff}
        L ${XR} ${YC + r1InEff}
        A ${r1InEff} ${r1InEff} 0 0 0 ${XR + r1InEff * c45} ${YC + r1InEff * c45}
        L ${XR + r1OutEff * c45} ${YC + r1OutEff * c45}
        A ${r1OutEff} ${r1OutEff} 0 0 1 ${XR} ${YC + r1OutEff}
        L ${iX3 + GAP} ${YC + r1OutEff}
        Z
      `,
      cx: 565,
      cy: YC + 91,
    },
  ];

  // ----------------------------------------------------
  // 2. OUTER RING SEGMENTS (4 Top, 2 Right, 2 Bottom, 2 Left = 10 total)
  // ----------------------------------------------------
  const outerSegments: SegmentDef[] = [
    // Cyan (top left, wraps 135 deg to oX1)
    {
      name: outerRingColours[0][0],
      colour: outerRingColours[0][1],
      path: `
        M ${XL - r2OutEff * c45} ${YC - r2OutEff * c45}
        A ${r2OutEff} ${r2OutEff} 0 0 1 ${XL} ${YC - r2OutEff}
        L ${oX1 - GAP} ${YC - r2OutEff}
        L ${oX1 - GAP} ${YC - r2InEff}
        L ${XL} ${YC - r2InEff}
        A ${r2InEff} ${r2InEff} 0 0 0 ${XL - r2InEff * c45} ${YC - r2InEff * c45}
        Z
      `,
      cx: 236,
      cy: YC - 156,
    },
    // Teal (top mid-left, oX1 to oX2)
    {
      name: outerRingColours[1][0],
      colour: outerRingColours[1][1],
      path: `
        M ${oX1 + GAP} ${YC - r2OutEff}
        L ${oX2 - GAP} ${YC - r2OutEff}
        L ${oX2 - GAP} ${YC - r2InEff}
        L ${oX1 + GAP} ${YC - r2InEff}
        Z
      `,
      cx: (oX1 + oX2) / 2,
      cy: YC - 156,
    },
    // Mint (top mid-right, oX2 to oX3)
    {
      name: outerRingColours[2][0],
      colour: outerRingColours[2][1],
      path: `
        M ${oX2 + GAP} ${YC - r2OutEff}
        L ${oX3 - GAP} ${YC - r2OutEff}
        L ${oX3 - GAP} ${YC - r2InEff}
        L ${oX2 + GAP} ${YC - r2InEff}
        Z
      `,
      cx: (oX2 + oX3) / 2,
      cy: YC - 156,
    },
    // Lime (top right, oX3 wraps to 45 deg)
    {
      name: outerRingColours[3][0],
      colour: outerRingColours[3][1],
      path: `
        M ${oX3 + GAP} ${YC - r2OutEff}
        L ${XR} ${YC - r2OutEff}
        A ${r2OutEff} ${r2OutEff} 0 0 1 ${XR + r2OutEff * c45} ${YC - r2OutEff * c45}
        L ${XR + r2InEff * c45} ${YC - r2InEff * c45}
        A ${r2InEff} ${r2InEff} 0 0 0 ${XR} ${YC - r2InEff}
        L ${oX3 + GAP} ${YC - r2InEff}
        Z
      `,
      cx: 624,
      cy: YC - 156,
    },

    // Yellow (right curve, 45 deg to 0 deg horizontal)
    {
      name: outerRingColours[4][0],
      colour: outerRingColours[4][1],
      path: `
        M ${XR + r2OutEff * c45} ${YC - r2OutEff * c45}
        A ${r2OutEff} ${r2OutEff} 0 0 1 ${XR + r2OutEff} ${YC - GAP}
        L ${XR + r2InEff} ${YC - GAP}
        A ${r2InEff} ${r2InEff} 0 0 0 ${XR + r2InEff * c45} ${YC - r2InEff * c45}
        Z
      `,
      cx: 756.5,
      cy: 180,
    },
    // Amber (right curve, 0 deg horizontal to 315 deg)
    {
      name: outerRingColours[5][0],
      colour: outerRingColours[5][1],
      path: `
        M ${XR + r2OutEff} ${YC + GAP}
        A ${r2OutEff} ${r2OutEff} 0 0 1 ${XR + r2OutEff * c45} ${YC + r2OutEff * c45}
        L ${XR + r2InEff * c45} ${YC + r2InEff * c45}
        A ${r2InEff} ${r2InEff} 0 0 0 ${XR + r2InEff} ${YC + GAP}
        Z
      `,
      cx: 756.5,
      cy: 300,
    },

    // Coral (bottom right, oX2=430 to 315 deg)
    {
      name: outerRingColours[6][0],
      colour: outerRingColours[6][1],
      path: `
        M ${oX2 + GAP} ${YC + r2InEff}
        L ${XR} ${YC + r2InEff}
        A ${r2InEff} ${r2InEff} 0 0 0 ${XR + r2InEff * c45} ${YC + r2InEff * c45}
        L ${XR + r2OutEff * c45} ${YC + r2OutEff * c45}
        A ${r2OutEff} ${r2OutEff} 0 0 1 ${XR} ${YC + r2OutEff}
        L ${oX2 + GAP} ${YC + r2OutEff}
        Z
      `,
      cx: 560,
      cy: YC + 156,
    },
    // Crimson (bottom left, wraps 225 deg to oX2=430)
    {
      name: outerRingColours[7][0],
      colour: outerRingColours[7][1],
      path: `
        M ${XL - r2OutEff * c45} ${YC + r2OutEff * c45}
        A ${r2OutEff} ${r2OutEff} 0 0 0 ${XL} ${YC + r2OutEff}
        L ${oX2 - GAP} ${YC + r2OutEff}
        L ${oX2 - GAP} ${YC + r2InEff}
        L ${XL} ${YC + r2InEff}
        A ${r2InEff} ${r2InEff} 0 0 1 ${XL - r2InEff * c45} ${YC + r2InEff * c45}
        Z
      `,
      cx: 300,
      cy: YC + 156,
    },

    // Rose (left curve, 180 deg horizontal to 225 deg)
    {
      name: outerRingColours[8][0],
      colour: outerRingColours[8][1],
      path: `
        M ${XL - r2OutEff} ${YC + GAP}
        A ${r2OutEff} ${r2OutEff} 0 0 0 ${XL - r2OutEff * c45} ${YC + r2OutEff * c45}
        L ${XL - r2InEff * c45} ${YC + r2InEff * c45}
        A ${r2InEff} ${r2InEff} 0 0 1 ${XL - r2InEff} ${YC + GAP}
        Z
      `,
      cx: 103.5,
      cy: 300,
    },
    // Magenta (left curve, 135 deg to 180 deg horizontal)
    {
      name: outerRingColours[9][0],
      colour: outerRingColours[9][1],
      path: `
        M ${XL - r2OutEff * c45} ${YC - r2OutEff * c45}
        A ${r2OutEff} ${r2OutEff} 0 0 0 ${XL - r2OutEff} ${YC - GAP}
        L ${XL - r2InEff} ${YC - GAP}
        A ${r2InEff} ${r2InEff} 0 0 1 ${XL - r2InEff * c45} ${YC - r2InEff * c45}
        Z
      `,
      cx: 103.5,
      cy: 180,
    },
  ];

  // Inner ring left & right dark-glass end caps
  const innerLeftEndPath = `
    M ${XL - r1OutEff * c45} ${YC - r1OutEff * c45}
    A ${r1OutEff} ${r1OutEff} 0 0 0 ${XL - r1OutEff * c45} ${YC + r1OutEff * c45}
    L ${XL - r1InEff * c45} ${YC + r1InEff * c45}
    A ${r1InEff} ${r1InEff} 0 0 1 ${XL - r1InEff * c45} ${YC - r1InEff * c45}
    Z
  `;
  const innerRightEndPath = `
    M ${XR + r1OutEff * c45} ${YC - r1OutEff * c45}
    A ${r1OutEff} ${r1OutEff} 0 0 1 ${XR + r1OutEff * c45} ${YC + r1OutEff * c45}
    L ${XR + r1InEff * c45} ${YC + r1InEff * c45}
    A ${r1InEff} ${r1InEff} 0 0 0 ${XR + r1InEff * c45} ${YC - r1InEff * c45}
    Z
  `;

  const allSegments = [...innerSegments, ...outerSegments];

  const isExiting = transitionState === "exiting";
  const isEntering = transitionState === "entering";

  return (
    <motion.div
      className={`two-ring-colour-palette ${isExiting ? "is-exiting" : ""}`}
      aria-label="Two-ring extended colour palette"
      initial={isEntering ? { opacity: 0, scale: reduced ? 1 : 0.96 } : false}
      animate={{ opacity: isExiting ? 0 : 1, scale: isExiting ? (reduced ? 1 : 0.96) : 1 }}
      transition={{ duration: reduced ? 0.1 : isExiting ? 0.18 : 0.32, ease: "easeOut" }}
    >
      <svg
        className="shell-svg two-ring-svg"
        viewBox="0 0 860 480"
        aria-label="Two concentric stadium colour rings"
      >
        <defs>
          <linearGradient id="two-ring-glass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1a2736" />
            <stop offset="30%" stopColor="#0a1017" />
            <stop offset="70%" stopColor="#04070b" />
            <stop offset="100%" stopColor="#0d141e" />
          </linearGradient>

          <filter id="two-ring-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Outer stadium contour blue rim */}
        <path
          d={`M ${XL} ${YC - R2_OUT} L ${XR} ${YC - R2_OUT} A ${R2_OUT} ${R2_OUT} 0 0 1 ${XR} ${YC + R2_OUT} L ${XL} ${YC + R2_OUT} A ${R2_OUT} ${R2_OUT} 0 0 1 ${XL} ${YC - R2_OUT} Z`}
          fill="none"
          stroke="rgba(120, 190, 255, 0.65)"
          strokeWidth="1.5"
          style={{ filter: "drop-shadow(0 0 8px rgba(100, 180, 255, 0.45))" }}
          pointerEvents="none"
        />

        {/* Inner ring outer contour blue rim */}
        <path
          d={`M ${XL} ${YC - R1_OUT} L ${XR} ${YC - R1_OUT} A ${R1_OUT} ${R1_OUT} 0 0 1 ${XR} ${YC + R1_OUT} L ${XL} ${YC + R1_OUT} A ${R1_OUT} ${R1_OUT} 0 0 1 ${XL} ${YC - R1_OUT} Z`}
          fill="none"
          stroke="rgba(120, 190, 255, 0.45)"
          strokeWidth="1"
          style={{ filter: "drop-shadow(0 0 5px rgba(100, 180, 255, 0.35))" }}
          pointerEvents="none"
        />

        {/* Inner ring curved dark-glass end caps */}
        <path
          d={innerLeftEndPath}
          fill="url(#two-ring-glass)"
          stroke="rgba(85, 125, 165, 0.5)"
          strokeWidth="1"
        />
        <path
          d={innerRightEndPath}
          fill="url(#two-ring-glass)"
          stroke="rgba(85, 125, 165, 0.5)"
          strokeWidth="1"
        />

        {/* 18 Interactive Colour Segments */}
        {allSegments.map((segment) => {
          const isSelected = settings.accent === segment.name;
          const isSideCurve = ["Yellow", "Amber", "Rose", "Magenta"].includes(segment.name);
          const dotRadius = 3.6;
          const dotGap = 6.0;
          const textAdvance = 7.0;
          const textWidth = segment.name.length * textAdvance;
          const totalWidth = dotRadius * 2 + dotGap + textWidth;
          const groupLeft = segment.cx - totalWidth / 2;

          return (
            <motion.g
              key={segment.name}
              className={`shell-option ${isSelected ? "selected" : ""}`}
              role="button"
              tabIndex={0}
              aria-label={segment.name}
              aria-pressed={isSelected}
              onClick={() => onSelect(segment.name)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(segment.name);
                }
              }}
              initial={isEntering ? { opacity: 0 } : false}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.2 }}
            >
              <path
                d={segment.path}
                fill="url(#two-ring-glass)"
                stroke={isSelected ? "#a2cded" : "rgba(85, 125, 165, 0.45)"}
                strokeWidth={isSelected ? 1.5 : 1}
              />

              <g pointerEvents="none">
                {isSideCurve ? (
                  <>
                    {/* Vertically stacked swatch & label to stay strictly inside curved segment boundaries */}
                    <circle
                      cx={segment.cx}
                      cy={segment.cy - 10}
                      r={dotRadius}
                      fill={segment.colour}
                      style={{
                        filter: `drop-shadow(0 0 5px ${segment.colour}) drop-shadow(0 0 10px ${segment.colour}88)`,
                      }}
                    />
                    <text
                      x={segment.cx}
                      y={segment.cy + 10}
                      textAnchor="middle"
                      className="segment-label"
                      style={{
                        fontSize: "12px",
                        fill: isSelected ? "#ffffff" : "#f0f4fa",
                        fontWeight: isSelected ? 600 : 400,
                      }}
                    >
                      {segment.name}
                    </text>
                  </>
                ) : (
                  <>
                    {/* Horizontal swatch & label along straights */}
                    <circle
                      cx={groupLeft + dotRadius}
                      cy={segment.cy}
                      r={dotRadius}
                      fill={segment.colour}
                      style={{
                        filter: `drop-shadow(0 0 5px ${segment.colour}) drop-shadow(0 0 10px ${segment.colour}88)`,
                      }}
                    />
                    <text
                      x={groupLeft + dotRadius * 2 + dotGap}
                      y={segment.cy + 4.5}
                      textAnchor="start"
                      className="segment-label"
                      style={{
                        fontSize: "13px",
                        fill: isSelected ? "#ffffff" : "#f0f4fa",
                        fontWeight: isSelected ? 600 : 400,
                      }}
                    >
                      {segment.name}
                    </text>
                  </>
                )}

                {/* Selected indicator pip */}
                {isSelected && (
                  <circle
                    cx={segment.cx}
                    cy={segment.cy + (isSideCurve ? 21 : 16)}
                    r="2.5"
                    fill="#b8dfff"
                    style={{ filter: "drop-shadow(0 0 4px #b8dfff)" }}
                  />
                )}
              </g>
            </motion.g>
          );
        })}
      </svg>
    </motion.div>
  );
}
