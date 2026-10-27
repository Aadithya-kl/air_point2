import React, { type CSSProperties } from "react";

export type CapsulePhase = "disarmed" | "armed" | "holding" | "complete";

export interface WakandaCapsuleProps {
  phase: CapsulePhase;
  progress: number;
  reducedMotion?: boolean;
}

/**
 * Presentation-only capsule: the sole interior text is WAKANDA FOREVER.
 * Conforms to Air Point Aero Obsidian visual spec and V3 design constraints.
 */
export const WakandaCapsule: React.FC<WakandaCapsuleProps> = ({
  phase,
  progress,
  reducedMotion = false,
}) => {
  const boundedProgress = Math.max(
    0,
    Math.min(100, Number.isFinite(progress) ? progress : 0)
  );

  return (
    <div
      className={`wakanda-capsule phase-${phase}${reducedMotion ? " reduced-motion" : ""}`}
      role="img"
      aria-label={`Wakanda Forever capsule, ${
        phase === "holding" ? "confirmation in progress" : phase
      }`}
      data-testid="wakanda-capsule"
    >
      <span className="capsule-top-reflection" aria-hidden="true" />
      <span className="capsule-side-glow" aria-hidden="true" />
      <div className="capsule-wordmark">WAKANDA FOREVER</div>
      <span className="capsule-word-underline" aria-hidden="true" />
      <div className="capsule-progress-track" aria-hidden="true">
        <div
          className="capsule-progress-fill"
          style={{ "--progress": `${boundedProgress}%` } as CSSProperties}
        />
      </div>
    </div>
  );
};
