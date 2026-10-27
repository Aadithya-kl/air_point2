import React from "react";
import { CapsuleBody } from "./CapsuleBody";
import { MechanicalFin } from "./MechanicalFin";
import type { CapsuleStageProps } from "./types";

/**
 * CapsuleStage: Perspective Viewport & Volumetric Lighting Rig.
 *
 * Provides a controlled 3D spatial viewport with electric cyan and hyper-violet
 * volumetric lighting backplanes, depth horizons, and mechanical suspension rails.
 * Hosts the central CapsuleBody and establishes the stage coordinate system for
 * upcoming mechanical fins and radial countdown rings.
 */
export const CapsuleStage: React.FC<CapsuleStageProps> = ({
  state = "IDLE",
  accent = "dual",
  label,
  sublabel,
  badge,
  children,
  className = "",
  showLightingRigs = true,
  ariaLabel = "AirPoint Capsule 3D Stage",
  testId = "capsule-stage",
}) => {
  // Determine ambient glow colors based on state & accent
  const getGlowClasses = () => {
    switch (state) {
      case "POWER_SAVE":
        return {
          left: "bg-amber-500/10",
          right: "bg-violet-500/10",
        };
      case "ARMED":
        return {
          left: "bg-violet-500/18",
          right: "bg-violet-500/22",
        };
      case "COUNTDOWN":
        return {
          left: "bg-cyan-500/22",
          right: "bg-violet-500/22",
        };
      case "ACTIVE":
        return {
          left: "bg-emerald-500/20",
          right: "bg-cyan-500/20",
        };
      case "WAKE":
        return {
          left: "bg-sky-500/25",
          right: "bg-cyan-500/25",
        };
      case "IDLE":
      default:
        return {
          left: "bg-cyan-500/12",
          right: "bg-violet-500/12",
        };
    }
  };

  const glows = getGlowClasses();

  return (
    <section
      aria-label={ariaLabel}
      data-testid={testId}
      data-stage-state={state}
      data-stage-accent={accent}
      className={`
        relative w-full overflow-hidden
        rounded-2xl border border-white/10
        bg-gradient-to-b from-[#0e111a]/90 via-[#0a0c12]/95 to-[#06070a]
        shadow-[0_30px_70px_-15px_rgba(0,0,0,0.85)]
        backdrop-blur-xl select-none
        transition-colors duration-500
        ${className}
      `}
    >
      {/* 1. Volumetric Lighting Rigs (Electric Cyan & Hyper Violet Backlights) */}
      {showLightingRigs && (
        <div
          className="pointer-events-none absolute inset-0 overflow-hidden"
          aria-hidden="true"
        >
          {/* Left Volumetric Light Cone */}
          <div
            className={`
              absolute -top-16 left-1/4 w-72 h-44 rounded-full
              blur-3xl transition-all duration-700
              ${glows.left}
            `}
          />

          {/* Right Volumetric Light Cone */}
          <div
            className={`
              absolute -top-16 right-1/4 w-72 h-44 rounded-full
              blur-3xl transition-all duration-700
              ${glows.right}
            `}
          />

          {/* Central Specular Ground Reflection */}
          <div className="absolute bottom-0 inset-x-12 h-16 bg-gradient-to-t from-white/[0.02] to-transparent blur-md" />
        </div>
      )}

      {/* 2. Top Spatial Horizon / Mechanical Suspension Rail */}
      <div
        className="pointer-events-none absolute top-0 inset-x-0 h-[1.5px] bg-gradient-to-r from-transparent via-white/20 to-transparent"
        aria-hidden="true"
      />

      {/* 3. 3D Perspective Viewport Area */}
      <div
        className="
          capsule-viewport relative z-10
          flex flex-col items-center justify-center
          py-14 sm:py-16 px-6 sm:px-12 min-h-[250px]
        "
        style={{
          perspective: "1200px",
          transformStyle: "preserve-3d",
        }}
      >
        {/* Stage Center Plinth with 3D Depth */}
        <div
          className="relative flex flex-col items-center justify-center w-full transition-transform duration-500"
          style={{ transformStyle: "preserve-3d" }}
        >
          {/* Unified Capsule Chassis & Articulated Fins Assembly */}
          <div
            className="relative flex items-center justify-center w-full max-w-[420px]"
            style={{ transformStyle: "preserve-3d" }}
          >
            {/* Left Articulated Mechanical Fin */}
            <MechanicalFin
              orientation="left"
              state={state}
              accent={accent}
            />

            {/* Central Capsule Body Chassis */}
            <CapsuleBody
              state={state}
              accent={accent}
              label={label}
              sublabel={sublabel}
              badge={badge}
            />

            {/* Right Articulated Mechanical Fin */}
            <MechanicalFin
              orientation="right"
              state={state}
              accent={accent}
            />
          </div>

          {/* Optional Stage Projection Layer (Children: Fin assemblies, dials, or status docks) */}
          {children && (
            <div
              className="relative z-20 mt-4 w-full flex flex-col items-center justify-center"
              style={{ transformStyle: "preserve-3d" }}
            >
              {children}
            </div>
          )}
        </div>
      </div>

      {/* 4. Sub-stage Calibration Horizon */}
      <div
        className="relative z-10 flex items-center justify-between px-5 py-2.5 border-t border-white/5 bg-black/30 text-[11px] font-mono text-white/40"
      >
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400/80 animate-pulse" />
          <span className="uppercase tracking-wider">STAGE PERSPECTIVE 1200PX</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-white/30">KINEMATICS:</span>
          <span className="text-white/70 font-semibold uppercase">{state}</span>
        </div>
      </div>
    </section>
  );
};
