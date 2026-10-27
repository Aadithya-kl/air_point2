import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  Play,
  Pause,
  RotateCcw,
  Info,
  ShieldAlert,
  MousePointer,
  Hand,
  Camera,
  MessageSquare,
  Volume2,
  Lock,
} from "lucide-react";
import { type GestureId } from "@/lib/air-point-model";
import { GestureDiagram } from "@/components/air-point/illustrations";

export interface GestureVideoPlayerProps {
  gestureId: GestureId;
  reducedMotion?: boolean;
}

export interface VideoTutorialSpec {
  gestureId: GestureId;
  src: string;
  poster: string;
  title: string;
  subtitle: string;
  durationSeconds: number;
  icon: React.ReactNode;
  steps: Array<{
    step: string;
    title: string;
    desc: string;
  }>;
  note: string;
}

export const GESTURE_VIDEO_SPECS: Record<Exclude<GestureId, "mute">, VideoTutorialSpec> = {
  pointer: {
    gestureId: "pointer",
    src: "/videos/gestures/pointer-click.mp4",
    poster: "/videos/gestures/posters/pointer-click-poster.jpg",
    title: "How to steer & click",
    subtitle: "Use your right hand index fingertip to steer the cursor and pinch to click.",
    durationSeconds: 10,
    icon: <MousePointer className="w-4 h-4 text-[var(--accent)]" />,
    steps: [
      { step: "STEP 1", title: "Steer", desc: "Raise right hand and steer cursor with index fingertip." },
      { step: "STEP 2", title: "Pinch Click", desc: "Bring thumb and index fingertips together quickly for primary click." },
      { step: "STEP 3", title: "Double Click", desc: "Double-pinch within 350ms to perform a double-click." },
    ],
    note: "Filtered by OneEuroFilter to eliminate micro-jitter while maintaining sub-pixel precision.",
  },
  drag: {
    gestureId: "drag",
    src: "/videos/gestures/drag-drop.mp4",
    poster: "/videos/gestures/posters/drag-drop-poster.jpg",
    title: "How to drag & drop",
    subtitle: "Use your left hand pinch to grab items and release to drop.",
    durationSeconds: 10,
    icon: <Hand className="w-4 h-4 text-[var(--accent)]" />,
    steps: [
      { step: "STEP 1", title: "Pinch Hold", desc: "Pinch left thumb and index finger together over target item." },
      { step: "STEP 2", title: "Translate", desc: "Maintain pinch grip and translate your hand across the screen." },
      { step: "STEP 3", title: "Release Drop", desc: "Separate fingertips to release and drop the item into position." },
    ],
    note: "Hysteresis deadband inside the gesture engine prevents accidental drops during hand movement.",
  },
  screenshot: {
    gestureId: "screenshot",
    src: "/videos/gestures/screenshot.mp4",
    poster: "/videos/gestures/posters/screenshot-poster.jpg",
    title: "How to capture screenshot",
    subtitle: "Hold both open palms stationary facing the camera.",
    durationSeconds: 10,
    icon: <Camera className="w-4 h-4 text-[var(--accent)]" />,
    steps: [
      { step: "STEP 1", title: "Raise Palms", desc: "Raise both open palms facing the camera with thumbs inward." },
      { step: "STEP 2", title: "Hold Steady", desc: "Hold both hands stationary for the configured hold duration." },
      { step: "STEP 3", title: "Capture", desc: "Air Point captures full desktop and shows Dynamic Island confirmation." },
    ],
    note: "Hold duration is live-configurable between 1.0s and 5.0s using the slider below.",
  },
  whatsapp: {
    gestureId: "whatsapp",
    src: "/videos/gestures/whatsapp.mp4",
    poster: "/videos/gestures/posters/whatsapp-poster.jpg",
    title: "How to open WhatsApp",
    subtitle: "Form a two-hand 'W' shape with index fingers and thumbs.",
    durationSeconds: 5,
    icon: <MessageSquare className="w-4 h-4 text-[var(--accent)]" />,
    steps: [
      { step: "STEP 1", title: "Form 'W'", desc: "Touch thumbs together and angle index fingers upward in a 'W' pose." },
      { step: "STEP 2", title: "Hold Pose", desc: "Hold 'W' pose inside camera frame for brief validation." },
      { step: "STEP 3", title: "Launch App", desc: "Air Point launches or brings WhatsApp Desktop to focus." },
    ],
    note: "Built-in launch cooldown prevents rapid duplicate window launches.",
  },
  "volume-up": {
    gestureId: "volume-up",
    src: "/videos/gestures/volume-up.mp4",
    poster: "/videos/gestures/posters/volume-up-poster.jpg",
    title: "How to increase volume",
    subtitle: "Raise your right index fingertip near your right ear.",
    durationSeconds: 10,
    icon: <Volume2 className="w-4 h-4 text-[var(--accent)]" />,
    steps: [
      { step: "STEP 1", title: "Target Ear", desc: "Extend your right index finger toward your right ear anchor." },
      { step: "STEP 2", title: "Hold Proximity", desc: "Hold fingertip within proximity of facial landmark #234." },
      { step: "STEP 3", title: "Volume Up", desc: "Air Point steps Windows master volume upward continuously." },
    ],
    note: "Requires MediaPipe FaceMesh right ear landmark #234 visibility.",
  },
  "volume-down": {
    gestureId: "volume-down",
    src: "/videos/gestures/volume-down.mp4",
    poster: "/videos/gestures/posters/volume-down-poster.jpg",
    title: "How to decrease volume",
    subtitle: "Raise your left index fingertip near your left ear.",
    durationSeconds: 5,
    icon: <Volume2 className="w-4 h-4 text-[var(--accent)]" />,
    steps: [
      { step: "STEP 1", title: "Target Ear", desc: "Extend your left index finger toward your left ear anchor." },
      { step: "STEP 2", title: "Hold Proximity", desc: "Hold fingertip within proximity of facial landmark #454." },
      { step: "STEP 3", title: "Volume Down", desc: "Air Point steps Windows master volume downward continuously." },
    ],
    note: "Requires MediaPipe FaceMesh left ear landmark #454 visibility.",
  },
  "wakanda-forever": {
    gestureId: "wakanda-forever",
    src: "/videos/gestures/wakanda-forever.mp4",
    poster: "/videos/gestures/posters/wakanda-forever-poster.jpg",
    title: "How to lock workstation",
    subtitle: "Cross forearms over chest with closed fists and hold.",
    durationSeconds: 10,
    icon: <Lock className="w-4 h-4 text-[var(--accent)]" />,
    steps: [
      { step: "STEP 1", title: "Cross Forearms", desc: "Cross both forearms over chest with closed fists in an 'X' pose." },
      { step: "STEP 2", title: "Hold 2.0s", desc: "Hold crossed pose steadily for 2.0 continuous seconds." },
      { step: "STEP 3", title: "Lock Workstation", desc: "Air Point locks Windows workstation via Win32 LockWorkStation." },
    ],
    note: "Instructional tutorial only. Video playback never executes system lock.",
  },
};

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export const GestureVideoPlayer: React.FC<GestureVideoPlayerProps> = ({
  gestureId,
  reducedMotion = false,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [duration, setDuration] = useState<number>(0);
  const [loadError, setLoadError] = useState<boolean>(false);
  const [isSeeking, setIsSeeking] = useState<boolean>(false);

  // Mute / Unmute is handled exclusively by GestureTutorial (GIF)
  if (gestureId === "mute") {
    return null;
  }

  const spec = GESTURE_VIDEO_SPECS[gestureId as keyof typeof GESTURE_VIDEO_SPECS];
  if (!spec) {
    return null;
  }

  // Handle play/pause toggle
  const togglePlayPause = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;

    if (video.paused) {
      try {
        const p = video.play?.();
        if (p && typeof p.then === "function") {
          p.then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
        } else {
          setIsPlaying(true);
        }
      } catch {
        setIsPlaying(false);
      }
    } else {
      try {
        video.pause?.();
      } catch {}
      setIsPlaying(false);
    }
  }, []);

  // Handle replay from beginning
  const handleReplay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = 0;
    setCurrentTime(0);
    try {
      const p = video.play?.();
      if (p && typeof p.then === "function") {
        p.then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
      } else {
        setIsPlaying(true);
      }
    } catch {
      setIsPlaying(false);
    }
  }, []);

  // Handle seek bar interaction
  const handleSeekChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newTime = parseFloat(e.target.value);
    setCurrentTime(newTime);
    if (videoRef.current) {
      videoRef.current.currentTime = newTime;
    }
  }, []);

  // Autoplay or reset when gestureId or reducedMotion changes
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    // Reset playback position
    video.currentTime = 0;
    setCurrentTime(0);
    setLoadError(false);

    if (reducedMotion) {
      try {
        video.pause?.();
      } catch {}
      setIsPlaying(false);
      return;
    }

    // Autoplay when reducedMotion is disabled
    try {
      const playPromise = video.play?.();
      if (playPromise !== undefined && typeof playPromise.then === "function") {
        playPromise
          .then(() => setIsPlaying(true))
          .catch(() => {
            // Autoplay was prevented by browser policy
            setIsPlaying(false);
          });
      } else {
        setIsPlaying(true);
      }
    } catch {
      setIsPlaying(false);
    }

    // Cleanup: pause playback on unmount or before switching
    return () => {
      try {
        video.pause?.();
      } catch {}
    };
  }, [gestureId, reducedMotion]);

  return (
    <div
      data-testid={`gesture-video-tutorial-${gestureId}`}
      className="gesture-video-container mb-5"
    >
      {/* Nothing Glass Video Stage */}
      <div className="gesture-video-stage">
        {/* Status Pill Badge */}
        <div className="gesture-video-badge" aria-hidden="true">
          <span className={`dot ${isPlaying ? "playing" : ""}`} />
          <span>
            {reducedMotion
              ? "STATIC POSTER · REDUCED MOTION"
              : isPlaying
              ? "TUTORIAL · 24FPS HD"
              : "PAUSED · CLICK TO PLAY"}
          </span>
        </div>


        {/* Video Wrapper preserving 16:9 native aspect ratio */}
        <div className="gesture-video-media-wrap">
          {!loadError ? (
            <>
              <video
                ref={videoRef}
                src={spec.src}
                poster={spec.poster}
                muted
                playsInline
                loop
                preload="metadata"
                data-testid={`gesture-video-${gestureId}`}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onTimeUpdate={() => {
                  if (!isSeeking && videoRef.current) {
                    setCurrentTime(videoRef.current.currentTime);
                  }
                }}
                onLoadedMetadata={() => {
                  if (videoRef.current) {
                    setDuration(videoRef.current.duration || spec.durationSeconds);
                  }
                }}
                onError={() => setLoadError(true)}
                onClick={togglePlayPause}
                className="gesture-video-player"
              />

              {/* Big Center Play Overlay Button when paused */}
              {!isPlaying && (
                <button
                  type="button"
                  data-testid="gesture-video-overlay-play-btn"
                  onClick={togglePlayPause}
                  aria-label={`Play ${spec.title} tutorial`}
                  className="gesture-video-play-overlay"
                >
                  <Play className="w-6 h-6 fill-current text-white translate-x-0.5" />
                </button>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center p-6 text-center text-[var(--muted)] gap-2">
              <ShieldAlert className="w-8 h-8 text-amber-400" />
              <span className="text-xs font-mono">Video tutorial asset unavailable</span>
              <GestureDiagram gestureId={gestureId} size="lg" className="text-[var(--text)] mt-2" />
            </div>
          )}
        </div>

        {/* Video Controls Bar */}
        {!loadError && (
          <div className="gesture-video-controls" role="toolbar" aria-label="Video playback controls">
            <button
              type="button"
              data-testid="gesture-video-play-btn"
              onClick={togglePlayPause}
              aria-label={isPlaying ? "Pause tutorial" : "Play tutorial"}
              className="gesture-video-btn"
            >
              {isPlaying ? (
                <Pause className="w-3.5 h-3.5 text-[var(--text)]" />
              ) : (
                <Play className="w-3.5 h-3.5 text-[var(--text)] fill-current" />
              )}
            </button>

            <button
              type="button"
              onClick={handleReplay}
              aria-label="Replay tutorial from start"
              className="gesture-video-btn"
            >
              <RotateCcw className="w-3.5 h-3.5 text-[var(--text)]" />
            </button>

            {/* Scrub / Seek Slider */}
            <input
              type="range"
              min={0}
              max={duration || spec.durationSeconds}
              step={0.1}
              value={currentTime}
              onMouseDown={() => setIsSeeking(true)}
              onMouseUp={() => setIsSeeking(false)}
              onChange={handleSeekChange}
              aria-label="Seek video position"
              className="gesture-video-scrub"
            />

            {/* Time Readout */}
            <span className="gesture-video-time" aria-label="Video timestamp">
              {formatTime(currentTime)} / {formatTime(duration || spec.durationSeconds)}
            </span>
          </div>
        )}
      </div>

      {/* Structured Gesture Instructions */}
      <div className="tutorial-instructions-block">
        <div className="flex items-center gap-2 mb-2">
          {spec.icon}
          <h3 className="text-sm font-bold m-0 tracking-tight text-[var(--text)]">
            {spec.title}
          </h3>
        </div>

        <p className="text-xs text-[var(--muted)] leading-relaxed m-0 mb-3">
          {spec.subtitle}
        </p>

        {/* Three Clear Instructional Steps */}
        <div className="tutorial-steps-grid" role="list" aria-label="Gesture execution steps">
          {spec.steps.map((st) => (
            <div key={st.step} className="tutorial-step-card" role="listitem">
              <span className="tutorial-step-num">{st.step}</span>
              <strong className="tutorial-step-title">{st.title}</strong>
              <span className="tutorial-step-desc">{st.desc}</span>
            </div>
          ))}
        </div>

        <div className="flex items-center gap-2 text-[10px] text-[var(--muted)] font-mono mt-2 pt-2 border-t border-[var(--line-divider)]">
          <Info className="w-3.5 h-3.5 text-[var(--accent)] shrink-0" />
          <span>Note: {spec.note}</span>
        </div>
      </div>
    </div>
  );
};
