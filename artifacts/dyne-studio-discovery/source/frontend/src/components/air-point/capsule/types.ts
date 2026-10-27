/**
 * Types and interfaces for the Futuristic Interactive Capsule (AirPoint V3).
 */

import type { ReactNode } from "react";

/**
 * Operating and visual states of the capsule.
 * - IDLE: Compact rest posture, subtle ambient breathing.
 * - ARMED: Primed ready state, slight fin separation, violet energy standby.
 * - COUNTDOWN: Active timer sweep, fin deployment, dynamic radial countdown indicator.
 * - ACTIVE: Full operational deployment, maximum energy rails, live telemetry flow.
 * - POWER_SAVE: Aerodynamic low-profile tuck, power saving beacon, reduced update rate.
 * - WAKE: Kinetic transition flare recovering from power-save to active/armed.
 */
export type CapsuleState =
  | "IDLE"
  | "ARMED"
  | "COUNTDOWN"
  | "ACTIVE"
  | "POWER_SAVE"
  | "WAKE";

/**
 * Lighting accent mode for energy guides and ambient viewport illumination.
 */
export type CapsuleAccent = "cyan" | "violet" | "dual" | "amber" | "emerald";

/**
 * Spatial orientation for articulated mechanical fins.
 */
export type FinOrientation = "left" | "right";

/**
 * Explicit state-to-angle mapping for mechanical fin kinematics.
 * Visual target angles:
 * - IDLE: 0° (compact, parked along chassis)
 * - ARMED: 18° (cracked open ready posture)
 * - COUNTDOWN: 45° (deliberate mid-flight extension)
 * - ACTIVE: 90° (fully deployed horizontal wing span)
 * - POWER_SAVE: 5° (low-profile retracted tuck)
 * - WAKE: 105° (kinetic burst overshoot before settling to 90°)
 */
export const FIN_DEPLOYMENT_ANGLES: Record<CapsuleState, number> = {
  IDLE: 0,
  ARMED: 18,
  COUNTDOWN: 45,
  ACTIVE: 90,
  POWER_SAVE: 5,
  WAKE: 105,
} as const;

/**
 * Target settled angle for states with overshoot (e.g. WAKE settles to 90° ACTIVE).
 */
export const FIN_SETTLED_ANGLES: Partial<Record<CapsuleState, number>> = {
  WAKE: 90,
};

/**
 * Returns the target deployment angle in degrees for a given capsule state.
 */
export function getFinTargetAngle(state: CapsuleState): number {
  return FIN_DEPLOYMENT_ANGLES[state] ?? 0;
}

/**
 * Kinematic configuration and posture parameters for mechanical fins.
 * Establishes bounds and properties for Phase 3 articulation.
 */
export interface FinPosture {
  orientation: FinOrientation;
  /** Angle in degrees (0 = flush parked, 90 = fully deployed, 105 = overshoot flare) */
  angleDeg: number;
  /** Deployment percentage [0.0 - 1.0] */
  deploymentFraction: number;
  /** Intensity of energy illumination [0.0 - 1.0] */
  glowIntensity: number;
  /** Optional secondary pitch angle in degrees */
  pitchDeg?: number;
}

/**
 * Properties for the articulated MechanicalFin component.
 */
export interface MechanicalFinProps {
  /** Spatial side of the fin: left or right */
  orientation: FinOrientation;
  /** Operating state of the capsule */
  state: CapsuleState;
  /** Explicit deployment angle in degrees override */
  deploymentAngle?: number;
  /** Aerodynamic sweep adjustment in degrees */
  sweepDeg?: number;
  /** 3D perspective pitch angle in degrees */
  pitchDeg?: number;
  /** Visual lighting accent mode */
  accent?: CapsuleAccent;
  /** Additional CSS class names */
  className?: string;
  /** Test identifier */
  testId?: string;
}

/**
 * Base properties for the 3D capsule viewport container.
 */
export interface CapsuleStageProps {
  /** Current operating state */
  state?: CapsuleState;
  /** Visual lighting accent mode */
  accent?: CapsuleAccent;
  /** Stage headline or mode title */
  label?: string;
  /** Secondary telemetry or status subtitle */
  sublabel?: string;
  /** Optional badge text displayed on the stage */
  badge?: string;
  /** Additional projected components (e.g. countdown ring, fin assemblies in later phases) */
  children?: ReactNode;
  /** Additional CSS class names */
  className?: string;
  /** Whether to render volumetric lighting cones/ambient glows behind the stage */
  showLightingRigs?: boolean;
  /** Accessible label for screen readers */
  ariaLabel?: string;
  /** Test identifier */
  testId?: string;
}

/**
 * Properties for the core metallic capsule chassis component.
 */
export interface CapsuleBodyProps {
  /** Operating state driving chassis glow and posture */
  state: CapsuleState;
  /** Accent lighting mode */
  accent?: CapsuleAccent;
  /** Primary label displayed within or above the capsule */
  label?: string;
  /** Secondary status text */
  sublabel?: string;
  /** Optional numerical badge or state chip */
  badge?: string;
  /** Custom icon or status glyph override */
  icon?: ReactNode;
  /** Click/press handler for interactive preview/inspection */
  onClick?: () => void;
  /** Additional CSS class names */
  className?: string;
  /** Whether the chassis is in an interactive state */
  interactive?: boolean;
  /** Accessible test ID */
  testId?: string;
}
