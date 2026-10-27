import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion, type MotionStyle } from "framer-motion";
import { accentValue, fonts, type Settings } from "./studio";
import type { CapsuleDefinition } from "./capsules";

interface Props {
  capsule: CapsuleDefinition;
  settings: Settings;
  resting: boolean;
  onClick: () => void;
  isDragging?: boolean;
  direction?: number;
  dragOffset?: number;
}

export function CentralCapsule({
  capsule,
  settings,
  resting,
  onClick,
  isDragging = false,
  direction = 0,
  dragOffset = 0,
}: Props) {
  const reduced = useReducedMotion();
  const accent = accentValue(settings);
  const prevAccent = useRef(accent);
  const [isPulsing, setIsPulsing] = useState(false);
  const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (prevAccent.current !== accent) {
      prevAccent.current = accent;
      if (!isDragging) {
        setIsPulsing(true);
        if (pulseTimer.current) clearTimeout(pulseTimer.current);
        pulseTimer.current = setTimeout(() => setIsPulsing(false), 360);
      }
    }
  }, [accent, isDragging]);

  useEffect(
    () => () => {
      if (pulseTimer.current) clearTimeout(pulseTimer.current);
    },
    [],
  );

  const intensityVal =
    (settings.texture === "Matte"
      ? settings.matteIntensity
      : settings.texture === "Translucent"
        ? settings.translucentIntensity
        : settings.intensity) / 100;

  const Icon = capsule.icon;

  // Content transition variants (slides ~24px with fade, 320ms ease-out)
  const contentVariants = {
    enter: (dir: number) => ({
      x: reduced ? 0 : dir > 0 ? 24 : dir < 0 ? -24 : 0,
      opacity: 0,
    }),
    center: {
      x: 0,
      opacity: 1,
    },
    exit: (dir: number) => ({
      x: reduced ? 0 : dir > 0 ? -24 : dir < 0 ? 24 : 0,
      opacity: 0,
    }),
  };

  return (
    <motion.button
      data-testid="central-capsule"
      className={`central-capsule texture-${settings.texture.toLowerCase()} style-${settings.style.toLowerCase()} ${isPulsing ? "is-pulse" : ""}`}
      aria-label={
        resting ? `${capsule.name} — open main options` : `${capsule.name} — go back one level`
      }
      onClick={onClick}
      initial={{ opacity: 0, y: reduced ? 0 : 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduced ? 0.1 : 0.4 }}
      style={
        {
          "--capsule-accent": accent,
          "--intensity": intensityVal,
          "--matte-intensity": settings.matteIntensity / 100,
          "--glass-intensity": settings.intensity / 100,
          "--translucent-intensity": settings.translucentIntensity / 100,
          "--roundness": `${settings.roundness}px`,
          "--capsule-font-size": `${settings.fontSize}px`,
        } as MotionStyle
      }
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <span className="capsule-preview-badge capsule-preview-on-capsule">Preview</span>
      <span className="capsule-sheen" aria-hidden="true" />
      <span className="capsule-content-clipper">
        <AnimatePresence mode="popLayout" initial={false} custom={direction}>
          <motion.span
            key={capsule.id}
            custom={direction}
            variants={contentVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{
              duration: reduced ? 0.1 : 0.34,
              ease: [0.16, 1, 0.3, 1],
            }}
            className="capsule-content"
            style={{
              transform: dragOffset ? `translateX(${dragOffset}px)` : undefined,
            }}
          >
            <span className="activity-mark">
              <Icon size={24} strokeWidth={1.5} />
            </span>
            <span
              className="capsule-name"
              style={{
                fontFamily: fonts[settings.font],
                fontSize: "var(--capsule-font-size, 23px)",
                fontWeight: settings.weight,
              }}
            >
              {capsule.name}
            </span>
            <span className="capsule-meta-group">
              <span className="status-light" style={{ opacity: 0.75 }} />
            </span>
          </motion.span>
        </AnimatePresence>
      </span>
    </motion.button>
  );
}
