import React, { useState } from "react";
import { Info, VolumeX, ShieldAlert } from "lucide-react";
import { type GestureId } from "@/lib/air-point-model";

export interface GestureTutorialProps {
  gestureId: GestureId;
  reducedMotion?: boolean;
}

export const GestureTutorial: React.FC<GestureTutorialProps> = ({
  gestureId,
  reducedMotion = false,
}) => {
  const [loadError, setLoadError] = useState(false);

  // Currently, the first approved animated tutorial is for Mute / Unmute
  if (gestureId !== "mute") {
    return null;
  }

  const gifPath = "/assets/gestures/mute-unmute.gif";
  const posterPath = "/assets/gestures/mute-unmute-poster.png";
  const altText =
    "Animated tutorial demonstrating the Mute / Unmute gesture: placing index fingertip vertically against lips to toggle system audio.";

  return (
    <div
      data-testid="mute-gesture-tutorial"
      className="gesture-tutorial-container mb-5"
    >
      {/* Polished Nothing Glass Stage Container */}
      <div className="gesture-tutorial-stage">
        {/* Status Pill Badge */}
        <div className="gesture-tutorial-badge" aria-hidden="true">
          <span className="dot" />
          <span>{reducedMotion ? "STATIC FRAME · REDUCED MOTION" : "TUTORIAL · 2s LOOP"}</span>
        </div>

        {/* Media Wrapper preserving 480x480 square aspect ratio */}
        <div className="gesture-tutorial-media-wrap">
          {!loadError ? (
            <img
              src={reducedMotion ? posterPath : gifPath}
              alt={altText}
              data-testid="mute-gesture-tutorial-gif"
              width={480}
              height={480}
              loading="eager"
              decoding="async"
              onError={() => setLoadError(true)}
              className="gesture-tutorial-gif"
            />
          ) : (
            <div className="flex flex-col items-center justify-center p-6 text-center text-[var(--muted)] gap-2">
              <ShieldAlert className="w-8 h-8 text-amber-400" />
              <span className="text-xs font-mono">Animated tutorial asset unavailable</span>
            </div>
          )}
        </div>
      </div>

      {/* Structured Gesture Instructions Outside the Animation */}
      <div className="tutorial-instructions-block">
        <div className="flex items-center gap-2 mb-2">
          <VolumeX className="w-4 h-4 text-[var(--accent)]" />
          <h3 className="text-sm font-bold m-0 tracking-tight text-[var(--text)]">
            How to perform Mute / Unmute
          </h3>
        </div>

        <p className="text-xs text-[var(--muted)] leading-relaxed m-0 mb-3">
          Place your index finger vertically on your lips to mute or unmute system audio.
        </p>

        {/* Three Clear Instructional Steps */}
        <div className="tutorial-steps-grid" role="list" aria-label="Gesture execution steps">
          <div className="tutorial-step-card" role="listitem">
            <span className="tutorial-step-num">STEP 1</span>
            <strong className="tutorial-step-title">Raise</strong>
            <span className="tutorial-step-desc">Extend your index finger.</span>
          </div>

          <div className="tutorial-step-card" role="listitem">
            <span className="tutorial-step-num">STEP 2</span>
            <strong className="tutorial-step-title">Hold</strong>
            <span className="tutorial-step-desc">
              Place your index fingertip vertically against your lips and hold briefly.
            </span>
          </div>

          <div className="tutorial-step-card" role="listitem">
            <span className="tutorial-step-num">STEP 3</span>
            <strong className="tutorial-step-title">Action</strong>
            <span className="tutorial-step-desc">
              Air Point toggles system audio mute/unmute.
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2 text-[10px] text-[var(--muted)] font-mono mt-2 pt-2 border-t border-[var(--line-divider)]">
          <Info className="w-3.5 h-3.5 text-[var(--accent)] shrink-0" />
          <span>Note: Use your index finger rather than the middle finger for reliable anatomical anchoring.</span>
        </div>
      </div>
    </div>
  );
};
