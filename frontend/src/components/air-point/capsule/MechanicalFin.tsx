import React from "react";
import type { MechanicalFinProps, CapsuleState } from "./types";
import { getFinTargetAngle } from "./types";

/**
 * MechanicalFin: Articulated Metallic Wing / Control Surface Assembly.
 *
 * Engineered multi-axis 3D mechanical fin for the AirPoint interactive capsule.
 * Features:
 * - Substantial, broad surface area with aerodynamic winglet facets (no needle points).
 * - Layered structural under-carriage for visible physical depth.
 * - Primary machined titanium armor plate with anisotropic specular edge sheens.
 * - Inset laser-machined energy light channel (Electric Cyan / Hyper Violet / Eco Amber).
 * - Robust dual-collar hinge knuckle with bearing boss and hex socket.
 * - Trailing edge ventilation louvers and counter-sunk micro-fasteners.
 * - Mirrored left/right mathematical kinematics with hardware-accelerated 3D transforms.
 */
export const MechanicalFin: React.FC<MechanicalFinProps> = ({
  orientation,
  state,
  deploymentAngle,
  sweepDeg,
  pitchDeg,
  accent = "dual",
  className = "",
  testId,
}) => {
  const isLeft = orientation === "left";
  const defaultTestId = isLeft ? "mechanical-fin-left" : "mechanical-fin-right";

  // 1. Kinematic Target Resolution
  const targetAngle = deploymentAngle ?? getFinTargetAngle(state);

  // Subtle 3D perspective pitch and aerodynamic sweep
  const effectivePitch = pitchDeg ?? targetAngle * 0.1; // Up to ~9° 3D tilt
  const effectiveSweep = sweepDeg ?? targetAngle * 0.04; // Up to ~3.6° aerodynamic cant

  // 2. Resolve Energy Lighting Conduits
  const resolveEnergyColor = () => {
    if (state === "POWER_SAVE") {
      return {
        conduitColor: "#fbbf24", // Eco Amber beacon
        glowFilter: "drop-shadow(0 0 5px rgba(251, 191, 36, 0.5))",
        opacity: 0.35,
      };
    }

    if (accent === "cyan") {
      return {
        conduitColor: "#22d3ee",
        glowFilter: "drop-shadow(0 0 8px rgba(34, 211, 238, 0.85))",
        opacity: state === "IDLE" ? 0.35 : 0.95,
      };
    }

    if (accent === "violet") {
      return {
        conduitColor: "#a876ff",
        glowFilter: "drop-shadow(0 0 8px rgba(168, 118, 255, 0.85))",
        opacity: state === "IDLE" ? 0.35 : 0.95,
      };
    }

    // Default 'dual': Left is Electric Cyan, Right is Hyper Violet
    if (isLeft) {
      return {
        conduitColor: "#22d3ee",
        glowFilter:
          state === "ACTIVE"
            ? "drop-shadow(0 0 10px rgba(34, 211, 238, 0.95))"
            : "drop-shadow(0 0 6px rgba(34, 211, 238, 0.65))",
        opacity: state === "IDLE" ? 0.3 : state === "ARMED" ? 0.7 : 1.0,
      };
    }

    return {
      conduitColor: "#a876ff",
      glowFilter:
        state === "ACTIVE"
          ? "drop-shadow(0 0 10px rgba(168, 118, 255, 0.95))"
          : "drop-shadow(0 0 6px rgba(168, 118, 255, 0.65))",
      opacity: state === "IDLE" ? 0.3 : state === "ARMED" ? 0.7 : 1.0,
    };
  };

  const energy = resolveEnergyColor();

  // 3. Mathematical 3D Transform Definition
  const signedRotationZ = isLeft ? -targetAngle : targetAngle;
  const signedPitchY = isLeft ? effectivePitch : -effectivePitch;

  // Pivot origin sits precisely at the center of the hinge knuckle (7px from root edge)
  const pivotOrigin = isLeft ? "calc(100% - 7px) 50%" : "7px 50%";

  // Handle WAKE keyframe burst animation vs inline CSS transition
  const isWake = state === "WAKE";
  const wakeClass = isWake
    ? isLeft
      ? "mechanical-fin-wake-left"
      : "mechanical-fin-wake-right"
    : "";

  const dynamicTransformStyle = isWake
    ? {}
    : {
        transform: `rotateZ(${signedRotationZ}deg) rotateY(${signedPitchY}deg) rotateX(${effectiveSweep}deg)`,
      };

  return (
    <div
      aria-hidden="true"
      data-testid={testId ?? defaultTestId}
      data-orientation={orientation}
      data-fin-state={state}
      data-deployment-angle={targetAngle}
      className={`
        mechanical-fin-root absolute top-1/2 -translate-y-1/2 z-10
        w-[98px] sm:w-[114px] h-[58px] sm:h-[66px] select-none pointer-events-none
        ${isLeft ? "right-[calc(100%-14px)]" : "left-[calc(100%-14px)]"}
        ${wakeClass}
        ${className}
      `}
      style={{
        transformOrigin: pivotOrigin,
        ...dynamicTransformStyle,
      }}
    >
      {/* Precision Multi-Layered Vector Assembly */}
      <svg
        viewBox="0 0 114 66"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full overflow-visible"
        style={{
          transform: isLeft ? "none" : "scaleX(-1)",
          transformOrigin: "center center",
        }}
      >
        <defs>
          {/* Layer 1: Recessed Carbon Under-Carriage Gradient */}
          <linearGradient
            id={`fin-understructure-${orientation}`}
            x1="106"
            y1="8"
            x2="6"
            y2="58"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="#141722" />
            <stop offset="50%" stopColor="#0b0d13" />
            <stop offset="100%" stopColor="#050609" />
          </linearGradient>

          {/* Layer 2: Machined Titanium Armor Plate Gradient */}
          <linearGradient
            id={`fin-titanium-${orientation}`}
            x1="102"
            y1="10"
            x2="8"
            y2="56"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="#2c3346" />
            <stop offset="28%" stopColor="#1b202c" />
            <stop offset="65%" stopColor="#10131b" />
            <stop offset="100%" stopColor="#07080c" />
          </linearGradient>

          {/* Layer 3: Stepped Dorsal Stiffener Gradient */}
          <linearGradient
            id={`fin-stiffener-${orientation}`}
            x1="96"
            y1="16"
            x2="30"
            y2="28"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="#384259" />
            <stop offset="50%" stopColor="#222838" />
            <stop offset="100%" stopColor="#141722" />
          </linearGradient>

          {/* Layer 4: Titanium Chamfer Bevel Highlight Rim */}
          <linearGradient
            id={`fin-bevel-${orientation}`}
            x1="102"
            y1="6"
            x2="0"
            y2="66"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="rgba(255, 255, 255, 0.55)" />
            <stop offset="25%" stopColor="rgba(255, 255, 255, 0.2)" />
            <stop offset="70%" stopColor="rgba(255, 255, 255, 0.05)" />
            <stop offset="100%" stopColor="rgba(0, 0, 0, 0.75)" />
          </linearGradient>

          {/* Cylindrical Hinge Knuckle Gradient */}
          <linearGradient
            id={`fin-hinge-${orientation}`}
            x1="100"
            y1="0"
            x2="114"
            y2="0"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="#252b3d" />
            <stop offset="35%" stopColor="#5d6985" />
            <stop offset="65%" stopColor="#323a4f" />
            <stop offset="100%" stopColor="#121520" />
          </linearGradient>
        </defs>

        {/* ====================================================================
            LAYER 1: DARK RECESSED STRUCTURAL UNDER-CARRIAGE (VISIBLE DEPTH)
            ==================================================================== */}
        <polygon
          points="106,9 23,16 10,23 6,25 6,41 14,50 106,57"
          fill={`url(#fin-understructure-${orientation})`}
          stroke="rgba(255, 255, 255, 0.12)"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />

        {/* Ambient shadow cast by top armor plate onto understructure */}
        <path
          d="M102 12 L25 19 L12 26 L8 28 L8 40 L16 49 L102 56 Z"
          fill="rgba(0, 0, 0, 0.45)"
        />

        {/* ====================================================================
            LAYER 2: PRIMARY MACHINED TITANIUM ARMOR PLATE (BROAD WINGLET)
            ==================================================================== */}
        <polygon
          points="102,11 25,18 12,25 8,27 8,39 16,48 102,55"
          fill={`url(#fin-titanium-${orientation})`}
          stroke={`url(#fin-bevel-${orientation})`}
          strokeWidth="1.2"
          strokeLinejoin="round"
        />

        {/* Top Anisotropic Specular Highlight Sheen along leading edge */}
        <path
          d="M100 12 L26 19 L13 26 L9 28"
          stroke="rgba(255, 255, 255, 0.45)"
          strokeWidth="1"
          strokeLinecap="round"
        />

        {/* Outer Winglet Facet Highlight */}
        <line
          x1="8"
          y1="27"
          x2="8"
          y2="39"
          stroke="rgba(255, 255, 255, 0.35)"
          strokeWidth="1.2"
          strokeLinecap="round"
        />

        {/* ====================================================================
            LAYER 3: STEPPED DORSAL STIFFENER SPAR & MICRO-FASTENERS
            ==================================================================== */}
        <polygon
          points="96,16 40,21 30,25 40,27 96,23"
          fill={`url(#fin-stiffener-${orientation})`}
          stroke="rgba(255, 255, 255, 0.16)"
          strokeWidth="0.8"
        />

        {/* Counter-sunk titanium Allen bolts */}
        <circle cx="88" cy="19" r="1.3" fill="#718096" />
        <circle cx="88" cy="19" r="0.6" fill="#1a202c" />
        <circle cx="66" cy="21" r="1.2" fill="#718096" />
        <circle cx="66" cy="21" r="0.5" fill="#1a202c" />
        <circle cx="46" cy="23" r="1.1" fill="#4a5568" />
        <circle cx="46" cy="23" r="0.5" fill="#1a202c" />

        {/* Lower spar rivets */}
        <circle cx="92" cy="48" r="1.1" fill="#4a5568" />
        <circle cx="70" cy="46" r="1.0" fill="#4a5568" />
        <circle cx="38" cy="43" r="0.9" fill="#2d3748" />

        {/* ====================================================================
            LAYER 4: INSET RECESSED PRECISION ENERGY CONDUIT
            ==================================================================== */}
        {/* Recessed dark groove */}
        <polygon
          points="98,30 32,32 18,33 32,34 98,36"
          fill="#040507"
          stroke="rgba(255, 255, 255, 0.08)"
          strokeWidth="0.6"
        />

        {/* Glowing frosted light channel */}
        <path
          d="M96 33 L20 33"
          stroke={energy.conduitColor}
          strokeWidth="2.4"
          strokeLinecap="round"
          style={{
            filter: energy.glowFilter,
            opacity: energy.opacity,
            transition: "opacity 400ms ease, stroke 400ms ease",
          }}
        />

        {/* Laser-etched optical hash marks along energy guide */}
        <g stroke="rgba(255, 255, 255, 0.35)" strokeWidth="0.75" strokeLinecap="round">
          <line x1="82" y1="31.5" x2="82" y2="34.5" />
          <line x1="68" y1="31.5" x2="68" y2="34.5" />
          <line x1="54" y1="31.5" x2="54" y2="34.5" />
          <line x1="40" y1="31.5" x2="40" y2="34.5" />
        </g>

        {/* ====================================================================
            LAYER 5: TRAILING-EDGE COOLING LOUVERS (AERODYNAMIC VENTS)
            ==================================================================== */}
        <g strokeLinecap="round">
          {/* Louver dark cavity shadows */}
          <line x1="38" y1="38" x2="33" y2="45" stroke="#000000" strokeWidth="2.2" />
          <line x1="50" y1="39" x2="45" y2="47" stroke="#000000" strokeWidth="2.2" />
          <line x1="62" y1="40" x2="57" y2="49" stroke="#000000" strokeWidth="2.2" />

          {/* Louver metallic bevel highlights */}
          <line x1="38" y1="38" x2="33" y2="45" stroke="rgba(255, 255, 255, 0.22)" strokeWidth="1" />
          <line x1="50" y1="39" x2="45" y2="47" stroke="rgba(255, 255, 255, 0.22)" strokeWidth="1" />
          <line x1="62" y1="40" x2="57" y2="49" stroke="rgba(255, 255, 255, 0.22)" strokeWidth="1" />
        </g>

        {/* ====================================================================
            LAYER 6: ROBUST DUAL-COLLAR HINGE KNUCKLE & BEARING ASSEMBLY
            ==================================================================== */}
        {/* Stationary clevis flange base plate */}
        <rect
          x="100"
          y="10"
          width="14"
          height="46"
          rx="4"
          fill={`url(#fin-hinge-${orientation})`}
          stroke="rgba(255, 255, 255, 0.3)"
          strokeWidth="1.2"
        />

        {/* Upper and lower machined collar relief grooves */}
        <line x1="100" y1="20" x2="114" y2="20" stroke="rgba(0, 0, 0, 0.7)" strokeWidth="1.2" />
        <line x1="100" y1="21" x2="114" y2="21" stroke="rgba(255, 255, 255, 0.3)" strokeWidth="0.8" />
        <line x1="100" y1="45" x2="114" y2="45" stroke="rgba(0, 0, 0, 0.7)" strokeWidth="1.2" />
        <line x1="100" y1="46" x2="114" y2="46" stroke="rgba(255, 255, 255, 0.3)" strokeWidth="0.8" />

        {/* Central Rotational Bearing Boss (Pivot Axis at (107, 33)) */}
        <circle
          cx="107"
          cy="33"
          r="5.5"
          fill="#161a25"
          stroke="rgba(255, 255, 255, 0.4)"
          strokeWidth="1.2"
        />

        {/* Inner bearing raceway */}
        <circle cx="107" cy="33" r="3.5" fill="#0f121a" stroke="rgba(255, 255, 255, 0.2)" strokeWidth="0.75" />

        {/* Core hex socket indent */}
        <polygon
          points="107,31 108.7,32 108.7,34 107,35 105.3,34 105.3,32"
          fill="#050608"
        />
      </svg>
    </div>
  );
};
