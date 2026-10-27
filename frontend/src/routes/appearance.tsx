import React from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  Check,
} from "lucide-react";
import { useAirPointEngine } from "@/components/air-point/engine";
import {
  ACCENT_OPTIONS,
  THEME_OPTIONS,
} from "@/lib/air-point-model";

export const AppearancePage: React.FC = () => {
  const engine = useAirPointEngine();

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <div className="page-head">
        <div>
          <h1 className="page-title">Appearance</h1>
          <p className="page-sub">Personalize the Air Point experience.</p>
        </div>

        <div className="flex items-center gap-2">
          <span className="badge active">
            <i className="dot" />
            <span>{engine.preferences.theme.toUpperCase()} · {engine.preferences.accent.toUpperCase()}</span>
          </span>
        </div>
      </div>

      {/* Section 1: Themes Grid */}
      <section className="glass page-panel p-6 rounded-[22px]">
        <div className="flex items-center justify-between gap-3 mb-4 pb-2.5 border-b border-[var(--line)]">
          <div>
            <h2 className="text-sm font-bold m-0 tracking-tight">Appearance themes</h2>
            <p className="text-[10px] text-[var(--muted)] m-0 mt-0.5">
              Choose the atmosphere for your workspace.
            </p>
          </div>
          <span className="badge">LOCAL PREVIEW</span>
        </div>

        <div className="theme-grid">
          {THEME_OPTIONS.map((theme) => {
            const selected = engine.preferences.theme === theme.id;
            const artClass =
              theme.id === "titanium"
                ? "light"
                : theme.id === "oled"
                ? "oled"
                : theme.id === "slate"
                ? "slate"
                : "dark";

            return (
              <button
                key={theme.id}
                type="button"
                data-testid={`theme-card-${theme.id}`}
                aria-pressed={selected}
                onClick={() => engine.setTheme(theme.id)}
                className={`theme-preview ${selected ? "selected" : ""}`}
              >
                <div className={`theme-art ${artClass}`}>
                  <div className="art-side" />
                  <div className="art-main">
                    <div className="art-line" />
                    <div className="art-line short" />
                    <div className="art-line" />
                  </div>
                </div>

                <div className="flex items-center justify-between mt-2.5">
                  <span className="theme-name">{theme.name}</span>
                  {selected && (
                    <Check className="w-3.5 h-3.5 text-[var(--accent)]" />
                  )}
                </div>
                <p className="theme-description">{theme.subtitle}</p>
              </button>
            );
          })}
        </div>

        {/* Section 2: Accent Swatches */}
        <div className="mt-8 pt-5 border-t border-[var(--line)]">
          <div className="mb-3">
            <h2 className="text-sm font-bold m-0 tracking-tight">Accent color</h2>
            <p className="text-[10px] text-[var(--muted)] m-0 mt-0.5">
              Used for focus, selection and tracking highlights.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {ACCENT_OPTIONS.map((accent) => {
              const selected = engine.preferences.accent === accent.id;
              return (
                <button
                  key={accent.id}
                  type="button"
                  data-testid={`accent-card-${accent.id}`}
                  aria-pressed={selected}
                  onClick={() => engine.setAccent(accent.id)}
                  className={`p-3 rounded-xl border text-left flex items-center gap-3 cursor-pointer transition-all ${
                    selected
                      ? "border-[var(--accent)] bg-[var(--surface-strong)]"
                      : "border-[var(--line)] bg-[var(--surface)] hover:border-[var(--line-strong)]"
                  }`}
                >
                  <span
                    style={{ backgroundColor: accent.swatchHex }}
                    className="w-6 h-6 rounded-full shrink-0 border border-white/20"
                  />
                  <div className="min-w-0">
                    <div className="text-xs font-bold truncate">
                      {accent.name}
                    </div>
                    <div className="text-[10px] text-[var(--muted)] truncate">
                      {accent.description}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Section 3: Layout Density & Reduced Motion */}
        <div className="mt-8 pt-5 border-t border-[var(--line)] grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <div className="mb-3">
              <h2 className="text-sm font-bold m-0 tracking-tight">Layout density</h2>
              <p className="text-[10px] text-[var(--muted)] m-0 mt-0.5">
                Adjust spacing throughout the interface.
              </p>
            </div>

            <div className="flex gap-2">
              {(["comfortable", "compact"] as const).map((density) => {
                const selected = engine.preferences.density === density;
                return (
                  <button
                    key={density}
                    type="button"
                    data-testid={`density-${density}`}
                    aria-pressed={selected}
                    onClick={() => engine.setDensity(density)}
                    className={`btn ${selected ? "primary" : ""}`}
                  >
                    {density.charAt(0).toUpperCase() + density.slice(1)}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div className="mb-3">
              <h2 className="text-sm font-bold m-0 tracking-tight">Reduced motion</h2>
              <p className="text-[10px] text-[var(--muted)] m-0 mt-0.5">
                Honors accessibility guidelines and eliminates non-essential animations.
              </p>
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl border border-[var(--line)] bg-[var(--surface)]">
              <span className="text-xs font-semibold">Disable UI motion</span>
              <button
                type="button"
                role="switch"
                aria-label="Reduced motion"
                aria-checked={engine.preferences.reducedMotion}
                onClick={() =>
                  engine.setReducedMotion(!engine.preferences.reducedMotion)
                }
                className="toggle"
              >
                <span />
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export const Route = createFileRoute("/appearance")({
  component: AppearancePage,
});
