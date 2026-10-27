import React from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  Hand,
  Info,
  Layers,
  Moon,
  MousePointer,
  Pause,
  Play,
  Power,
  RotateCw,
  Sun,
  Home,
  Sparkles,
  Zap,
} from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { useAirPointEngine } from "./engine";

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: Activity, crumb: "Overview" },
  { to: "/gestures", label: "Gestures", icon: Hand, crumb: "Gestures" },
  {
    to: "/cursor",
    label: "Cursor & Controls",
    icon: MousePointer,
    crumb: "Cursor & Controls",
  },
  { to: "/island", label: "Dynamic Island", icon: Sparkles, crumb: "Dynamic Island" },
  { to: "/appearance", label: "Appearance", icon: Layers, crumb: "Appearance" },
  { to: "/about", label: "About Air Point", icon: Info, crumb: "About Air Point" },
] as const;

export const DesktopShell: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const engine = useAirPointEngine();
  const routerState = useRouterState();
  const currentPath = routerState.location.pathname;

  const currentNavItem =
    NAV_ITEMS.find((item) =>
      item.to === "/" ? currentPath === "/" : currentPath.startsWith(item.to)
    ) ?? NAV_ITEMS[0];

  const isLight = engine.preferences.theme === "titanium";

  return (
    <div className="min-h-screen text-[var(--text)] selection:bg-[var(--accent)] selection:text-white relative">
      {/* Ambient mist & atmospheric gradient overlay over mountain wallpaper */}
      <div className="wallpaper-overlay" aria-hidden="true" />

      {/* Floating macOS-Style Translucent Frosted Glass Window Shell */}
      <div className="window-shell">
        {/* Top Window Instrument Bar */}
        <header className="window-topbar">
          {/* Breadcrumb with Home Icon */}
          <div className="topbar-crumb">
            <Home className="w-3.5 h-3.5" />
            <span className="sep">›</span>
            <span className="active" id="crumb">{currentNavItem.crumb}</span>
          </div>

          {/* Right Action Tools: Connection Status, Theme Switcher, Window Dots */}
          <div className="topbar-actions">
            {/* Live Bridge Connection Pill */}
            <div className={`status-pill ${engine.connected ? "connected" : ""}`}>
              <span className="dot" />
              <span id="top-status">
                {engine.connected
                  ? `BRIDGE ONLINE · 127.0.0.1:8765 (${engine.fps} FPS)`
                  : "BRIDGE OFFLINE"}
              </span>
            </div>

            {/* Sun/Moon Theme Toggle */}
            <div className="theme-pill-toggle" role="group" aria-label="Theme switcher">
              <button
                type="button"
                className={isLight ? "active" : ""}
                onClick={() => engine.setTheme("titanium")}
                aria-label="Light theme"
                title="Light frosted glass"
              >
                <Sun className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                className={!isLight ? "active" : ""}
                onClick={() =>
                  engine.setTheme(engine.preferences.lastDarkTheme || "obsidian")
                }
                aria-label="Dark theme"
                title={`Dark theme (${engine.preferences.lastDarkTheme || "obsidian"})`}
              >
                <Moon className="w-3.5 h-3.5" />
              </button>
            </div>

            {/* Window Controls (macOS 3-dot preview) */}
            <div className="window-dots" aria-hidden="true">
              <span className="dot dot-close" />
              <span className="dot dot-minimize" />
              <span className="dot dot-maximize" />
            </div>
          </div>
        </header>

        {/* Window Body: Sidebar + Main Content View */}
        <div className="window-body">
          {/* Left Translucent Sidebar */}
          <aside className="window-sidebar">
            <div className="sidebar-brand">
              <div className="sidebar-logo" aria-hidden="true">
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                >
                  <path d="M8 11V5a1.7 1.7 0 0 1 3.4 0v5M11.4 10V3.8a1.7 1.7 0 0 1 3.4 0V11M14.8 10V6a1.7 1.7 0 0 1 3.4 0v9c0 4.2-2.6 6.7-6.5 6.7h-1.4c-2.3 0-3.4-.9-4.5-2.8L3.5 15a1.8 1.8 0 0 1 3-2l1.5 2" />
                </svg>
              </div>
              <div>
                <div className="sidebar-wordmark">
                  AIR POINT
                </div>
                <div className="sidebar-tagline">Gesture Control for Windows</div>
              </div>
            </div>

            <nav className="sidebar-nav" aria-label="Primary workspace navigation">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const isActive =
                  item.to === "/"
                    ? currentPath === "/"
                    : currentPath.startsWith(item.to);

                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={`nav-pill ${isActive ? "active" : ""}`}
                  >
                    <Icon />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>

            <div className="flex-1" />

            {/* Python Bridge Telemetry Status Card in Sidebar */}
            <div className="sidebar-bridge-card">
              <div className="bridge-label">PYTHON BRIDGE</div>
              <div className={`bridge-status-row ${engine.connected ? "connected" : ""}`}>
                <span className="dot" />
                <span>
                  {engine.connected
                    ? `Connected (${engine.trackingStatus})`
                    : "Not connected"}
                </span>
              </div>
              <div className="bridge-description">
                {engine.connected
                  ? engine.running
                    ? `Engine running at ${engine.fps} FPS · Win32 SendInput operational.`
                    : "Engine stopped · Tracking suspended. Win32 actions inactive."
                  : "Frontend preview mode. Windows actions are unavailable."}
              </div>

              <div className="mt-2.5">
                {engine.connected ? (
                  engine.running ? (
                    <button
                      type="button"
                      onClick={() => engine.shutdownEngine()}
                      disabled={Boolean(engine.pendingMutation)}
                      className="w-full px-2.5 py-1.5 rounded-lg text-[10.5px] font-mono font-semibold border border-[var(--status-danger)]/40 bg-[var(--status-danger-bg)] text-[var(--status-danger)] hover:border-[var(--status-danger)] hover:bg-[var(--status-danger-bg)] transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Shutdown tracking engine"
                      aria-label="Shutdown tracking"
                    >
                      {engine.pendingMutation === "Shutting down tracking" ? (
                        <>
                          <RotateCw className="w-3 h-3 animate-spin text-[var(--status-danger)]" />
                          <span>Shutting down...</span>
                        </>
                      ) : (
                        <>
                          <Power className="w-3 h-3 text-[var(--status-danger)]" />
                          <span>Shutdown</span>
                        </>
                      )}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => engine.startEngine()}
                      disabled={Boolean(engine.pendingMutation)}
                      className="w-full px-2.5 py-1.5 rounded-lg text-[10.5px] font-mono font-semibold border border-[var(--status-healthy)]/40 bg-[var(--status-healthy-bg)] text-[var(--status-healthy)] hover:border-[var(--status-healthy)] hover:bg-[var(--status-healthy-bg)] transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Start tracking engine"
                      aria-label="Start tracking"
                    >
                      {engine.pendingMutation === "Starting tracking" ? (
                        <>
                          <RotateCw className="w-3 h-3 animate-spin text-[var(--status-healthy)]" />
                          <span>Starting...</span>
                        </>
                      ) : (
                        <>
                          <Play className="w-3 h-3 text-[var(--status-healthy)]" />
                          <span>Start</span>
                        </>
                      )}
                    </button>
                  )
                ) : (
                  <button
                    type="button"
                    disabled
                    className="w-full px-2.5 py-1.5 rounded-lg text-[10.5px] font-mono font-semibold border border-[var(--line-divider)] bg-[var(--surface-soft)] text-[var(--text-muted)] opacity-50 cursor-not-allowed flex items-center justify-center gap-1.5"
                    title="Python bridge offline — start python main.py"
                    aria-label="Bridge offline"
                  >
                    <Power className="w-3 h-3 text-[var(--text-muted)]" />
                    <span>Bridge offline</span>
                  </button>
                )}
              </div>

              <div className="mt-3 pt-2.5 border-t border-[var(--line-divider)]">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <Zap className={`w-3.5 h-3.5 ${engine.powerSave ? "text-amber-400" : "text-[var(--text-muted)]"}`} />
                    <span className="text-[11px] font-mono font-medium text-[var(--text-primary)]">
                      Power Saver
                    </span>
                  </div>
                  <Switch
                    checked={engine.powerSave}
                    onCheckedChange={(checked) => engine.setPowerSave(checked)}
                    disabled={!engine.connected || !engine.running || Boolean(engine.pendingMutation)}
                    aria-label="Toggle Power Saver mode"
                  />
                </div>
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-[var(--text-muted)]">
                    {engine.powerSave ? "Auto-idle (2 Hz)" : "Normal (Full rate)"}
                  </span>
                  <span
                    className={`px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider ${
                      engine.powerState === "POWER_SAVE"
                        ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                        : "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                    }`}
                  >
                    {engine.powerState === "POWER_SAVE" ? "Idle" : "Normal"}
                  </span>
                </div>
              </div>

              <Link
                to="/about"
                className="bridge-action-link"
              >
                <span>Connection Details</span>
                <span>→</span>
              </Link>
            </div>
          </aside>

          {/* Dynamic Route View Content Area */}
          <main className="window-content min-w-0">{children}</main>
        </div>
      </div>
    </div>
  );
};
