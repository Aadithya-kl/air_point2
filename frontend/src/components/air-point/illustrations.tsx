import React from "react";
import type { GestureId } from "@/lib/air-point-model";

interface GestureDiagramProps {
  gestureId: GestureId;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export const GestureDiagram: React.FC<GestureDiagramProps> = ({
  gestureId,
  size = "md",
  className = "",
}) => {
  const dimensions =
    size === "sm"
      ? "w-10 h-10"
      : size === "lg"
      ? "w-48 h-40"
      : "w-14 h-14";

  switch (gestureId) {
    case "screenshot":
      return (
        <svg
          viewBox="0 0 120 80"
          data-gesture-shape="open-palms-thumbs-inward"
          role="img"
          aria-label="Two open palms with thumbs inward for screenshot hold"
          className={`${dimensions} ${className}`}
        >
          {/* Left Open Palm */}
          <g stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round">
            <path d="M22 62 V30 M28 58 V22 M34 58 V20 M40 60 V25" />
            <path d="M20 62 C20 68, 42 68, 42 60 L48 44" />
            <circle cx="48" cy="44" r="2.5" fill="var(--accent-primary)" />
          </g>
          {/* Right Open Palm */}
          <g stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round">
            <path d="M98 62 V30 M92 58 V22 M86 58 V20 M80 60 V25" />
            <path d="M100 62 C100 68, 78 68, 78 60 L72 44" />
            <circle cx="72" cy="44" r="2.5" fill="var(--accent-primary)" />
          </g>
          {/* Inward Thumb Alignment Reticle */}
          <line
            x1="52"
            y1="44"
            x2="68"
            y2="44"
            stroke="var(--accent-primary)"
            strokeWidth="1.5"
            strokeDasharray="3 2"
          />
          <rect
            x="14"
            y="12"
            width="92"
            height="60"
            rx="6"
            fill="none"
            stroke="var(--accent-primary)"
            strokeWidth="1"
            strokeDasharray="4 4"
            opacity="0.55"
          />
        </svg>
      );

    case "whatsapp":
      return (
        <svg
          viewBox="0 0 120 80"
          data-gesture-shape="two-hand-w-pose"
          role="img"
          aria-label="Two-hand W pose gesture for launching WhatsApp"
          className={`${dimensions} ${className}`}
        >
          <path
            d="M26 22 L42 60 L60 34 L78 60 L94 22"
            fill="none"
            stroke="var(--accent-primary)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="26" cy="22" r="3.5" fill="currentColor" />
          <circle cx="42" cy="60" r="3.5" fill="var(--accent-primary)" />
          <circle cx="60" cy="34" r="4" fill="var(--accent-primary)" />
          <circle cx="78" cy="60" r="3.5" fill="var(--accent-primary)" />
          <circle cx="94" cy="22" r="3.5" fill="currentColor" />
        </svg>
      );

    case "pointer":
      return (
        <svg
          viewBox="0 0 80 80"
          data-gesture-shape="right-hand-pointer-pinch"
          role="img"
          aria-label="Right hand index fingertip cursor steering and thumb pinch click"
          className={`${dimensions} ${className}`}
        >
          <g stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round">
            <path d="M38 64 V20" />
            <path d="M46 62 V38 M54 62 V42 M62 64 V46" />
            <path d="M38 64 C38 70, 62 70, 62 64" />
            <path d="M38 52 L24 40" />
          </g>
          <circle cx="38" cy="18" r="4.5" fill="var(--accent-primary)" />
          <circle cx="24" cy="40" r="3" fill="var(--accent-primary)" />
          <line
            x1="24"
            y1="40"
            x2="38"
            y2="18"
            stroke="var(--accent-primary)"
            strokeWidth="1.5"
            strokeDasharray="3 2"
          />
        </svg>
      );

    case "drag":
      return (
        <svg
          viewBox="0 0 80 80"
          data-gesture-shape="left-hand-pinch-drag"
          role="img"
          aria-label="Left hand thumb-index pinch hold and drag translation"
          className={`${dimensions} ${className}`}
        >
          <g stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round">
            <path d="M34 30 L42 62 C42 68, 60 68, 60 60 V38" />
            <path d="M48 58 V36 M54 58 V38" />
            <path d="M34 30 L28 34" />
          </g>
          <circle cx="32" cy="31" r="5" fill="var(--accent-primary)" />
          <path
            d="M14 31 H22 M58 22 H68"
            stroke="var(--accent-primary)"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      );

    case "mute":
      return (
        <svg
          viewBox="0 0 80 80"
          data-gesture-shape="facial-lip-mute-anchor"
          role="img"
          aria-label="Index fingertip at lip center anchor to mute or unmute audio"
          className={`${dimensions} ${className}`}
        >
          <ellipse
            cx="40"
            cy="36"
            rx="20"
            ry="25"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
          />
          <path
            d="M32 46 Q40 50 48 46"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <line
            x1="40"
            y1="45"
            x2="40"
            y2="72"
            stroke="var(--accent-primary)"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <circle cx="40" cy="45" r="4" fill="var(--accent-primary)" />
        </svg>
      );

    case "volume-up":
      return (
        <svg
          viewBox="0 0 80 80"
          data-gesture-shape="facial-right-ear-volume-up"
          role="img"
          aria-label="Index fingertip at right ear anchor to increase volume"
          className={`${dimensions} ${className}`}
        >
          <ellipse
            cx="42"
            cy="40"
            rx="18"
            ry="23"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
          />
          <circle cx="22" cy="40" r="4.5" fill="var(--accent-primary)" />
          <path
            d="M12 56 L22 40"
            stroke="var(--accent-primary)"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <path
            d="M14 24 V16 M10 20 H18"
            stroke="var(--accent-primary)"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      );

    case "volume-down":
      return (
        <svg
          viewBox="0 0 80 80"
          data-gesture-shape="facial-left-ear-volume-down"
          role="img"
          aria-label="Index fingertip at left ear anchor to decrease volume"
          className={`${dimensions} ${className}`}
        >
          <ellipse
            cx="38"
            cy="40"
            rx="18"
            ry="23"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
          />
          <circle cx="58" cy="40" r="4.5" fill="var(--accent-primary)" />
          <path
            d="M68 56 L58 40"
            stroke="var(--accent-primary)"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <path
            d="M62 20 H70"
            stroke="var(--accent-primary)"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      );

    case "wakanda-forever":
      return (
        <svg
          viewBox="0 0 100 80"
          data-gesture-shape="crossed-arms-wakanda-forever"
          role="img"
          aria-label="Crossed forearms over chest with closed fists for Wakanda Forever workstation lock"
          className={`${dimensions} ${className}`}
        >
          {/* Torso/Chest Contour Frame */}
          <path
            d="M20 72 Q50 64 80 72"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="3 3"
            opacity="0.4"
          />
          {/* Left forearm crossed to screen-right */}
          <path
            d="M30 68 L66 28"
            stroke="var(--accent-primary)"
            strokeWidth="3.5"
            strokeLinecap="round"
          />
          {/* Right forearm crossed to screen-left */}
          <path
            d="M70 68 L34 28"
            stroke="currentColor"
            strokeWidth="3.5"
            strokeLinecap="round"
          />
          {/* Left fist at screen-right (over right collarbone) */}
          <circle cx="68" cy="26" r="6" fill="var(--accent-primary)" />
          {/* Right fist at screen-left (over left collarbone) */}
          <circle cx="32" cy="26" r="6" fill="currentColor" />
          {/* Crossed-X Intersection Reticle */}
          <circle cx="50" cy="48" r="3" fill="none" stroke="var(--accent-primary)" strokeWidth="1.5" />
          {/* Subtle Chest Shield Aura */}
          <path
            d="M50 16 L65 24 V44 C65 56 50 64 50 64 C50 64 35 56 35 44 V24 Z"
            fill="none"
            stroke="var(--accent-primary)"
            strokeWidth="1"
            strokeDasharray="2 2"
            opacity="0.35"
          />
        </svg>
      );
  }
};
