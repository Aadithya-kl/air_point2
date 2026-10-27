import React from "react";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

export interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: React.ReactNode;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  eyebrow,
  title,
  description,
  actions,
}) => (
  <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-[var(--border-subtle)]">
    <div>
      {eyebrow && (
        <div className="ap-label-tech text-[var(--accent-primary)] mb-1">
          {eyebrow}
        </div>
      )}
      <h1 className="text-2xl font-semibold tracking-tight text-[var(--text-primary)]">
        {title}
      </h1>
      <p className="text-sm text-[var(--text-secondary)] mt-0.5">
        {description}
      </p>
    </div>
    {actions && <div className="flex items-center gap-2.5">{actions}</div>}
  </header>
);

export type SemanticTone =
  | "healthy"
  | "warning"
  | "danger"
  | "info"
  | "neutral"
  | "accent";

export const StatusBadge: React.FC<{
  tone?: SemanticTone;
  label: string;
  pulse?: boolean;
  className?: string;
}> = ({ tone = "neutral", label, pulse = false, className = "" }) => {
  const toneStyles: Record<SemanticTone, string> = {
    healthy:
      "bg-[var(--status-healthy-bg)] text-[var(--status-healthy)] border-[var(--status-healthy)]/30",
    warning:
      "bg-[var(--status-warning-bg)] text-[var(--status-warning)] border-[var(--status-warning)]/30",
    danger:
      "bg-[var(--status-danger-bg)] text-[var(--status-danger)] border-[var(--status-danger)]/30",
    info: "bg-[var(--status-info-bg)] text-[var(--status-info)] border-[var(--status-info)]/30",
    accent:
      "bg-[var(--accent-muted)] text-[var(--accent-primary)] border-[var(--accent-border)]",
    neutral:
      "bg-[var(--bg-elevated)] text-[var(--text-secondary)] border-[var(--border-default)]",
  };

  const dotColors: Record<SemanticTone, string> = {
    healthy: "bg-[var(--status-healthy)]",
    warning: "bg-[var(--status-warning)]",
    danger: "bg-[var(--status-danger)]",
    info: "bg-[var(--status-info)]",
    accent: "bg-[var(--accent-primary)]",
    neutral: "bg-[var(--text-muted)]",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono font-medium border ${toneStyles[tone]} ${className}`}
    >
      <span
        className={`w-2 h-2 rounded-full ${dotColors[tone]} ${
          pulse ? "animate-pulse" : ""
        }`}
      />
      {label}
    </span>
  );
};

export const TelemetryCard: React.FC<{
  label: string;
  value: string;
  sublabel: string;
  tone?: SemanticTone;
  icon: React.ReactNode;
}> = ({ label, value, sublabel, tone = "neutral", icon }) => {
  const borderAccent =
    tone === "healthy"
      ? "border-l-2 border-l-[var(--status-healthy)]"
      : tone === "warning"
      ? "border-l-2 border-l-[var(--status-warning)]"
      : tone === "danger"
      ? "border-l-2 border-l-[var(--status-danger)]"
      : tone === "accent"
      ? "border-l-2 border-l-[var(--accent-primary)]"
      : "";

  return (
    <div
      className={`ap-panel ap-card-padding flex flex-col justify-between gap-2 ${borderAccent}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="ap-label-tech">{label}</span>
        <span className="text-[var(--text-secondary)]">{icon}</span>
      </div>
      <div>
        <div className="text-lg font-semibold font-mono tabular-nums text-[var(--text-primary)]">
          {value}
        </div>
        <div className="text-xs text-[var(--text-secondary)] mt-0.5">
          {sublabel}
        </div>
      </div>
    </div>
  );
};

export const MutationFeedbackBanner: React.FC<{
  pending: string | null;
  error: string | null;
  success: string | null;
  onDismiss?: () => void;
}> = ({ pending, error, success, onDismiss }) => {
  if (!pending && !error && !success) return null;

  if (pending) {
    return (
      <div
        role="status"
        className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-md border border-[var(--accent-border)] bg-[var(--accent-muted)] text-xs font-mono text-[var(--text-primary)]"
      >
        <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-primary)]" />
        <span>Syncing with Python engine: {pending}...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        className="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-md border border-[var(--status-danger)]/40 bg-[var(--status-danger-bg)] text-xs text-[var(--status-danger)]"
      >
        <div className="flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="underline font-mono text-xs hover:opacity-80"
          >
            Dismiss
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      role="status"
      className="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-md border border-[var(--status-healthy)]/40 bg-[var(--status-healthy-bg)] text-xs text-[var(--status-healthy)]"
    >
      <div className="flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 shrink-0" />
        <span>{success}</span>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="underline font-mono text-xs hover:opacity-80"
        >
          Dismiss
        </button>
      )}
    </div>
  );
};

export interface SettingSliderProps {
  id: string;
  label: string;
  description: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  formatValue?: (val: number) => string;
  minLabel?: string;
  maxLabel?: string;
  disabled?: boolean;
  onChange: (val: number) => void;
}

export const SettingSlider: React.FC<SettingSliderProps> = ({
  id,
  label,
  description,
  value,
  min,
  max,
  step,
  unit = "",
  formatValue,
  minLabel,
  maxLabel,
  disabled = false,
  onChange,
}) => {
  const display = formatValue ? formatValue(value) : `${value}${unit}`;

  return (
    <div className="ap-panel ap-card-padding flex flex-col gap-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <label
            htmlFor={id}
            className="text-base font-semibold text-[var(--text-primary)] block"
          >
            {label}
          </label>
          <p className="text-xs text-[var(--text-secondary)] mt-0.5">
            {description}
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            aria-label={`${label} numerical value`}
            min={min}
            max={max}
            step={step}
            disabled={disabled}
            value={value}
            onChange={(e) => {
              const parsed = parseFloat(e.target.value);
              if (!Number.isNaN(parsed)) {
                onChange(parsed);
              }
            }}
            className="w-20 px-2.5 py-1 text-right font-mono text-sm font-semibold rounded border border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-primary)]"
          />
          {unit && (
            <span className="text-xs font-mono text-[var(--text-secondary)]">
              {unit}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-1.5 pt-1">
        <input
          id={id}
          type="range"
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          aria-valuetext={display}
          className="w-full h-2 rounded-lg appearance-none cursor-pointer bg-[var(--bg-interactive)] accent-[var(--accent-primary)]"
        />
        <div className="flex items-center justify-between text-xs font-mono text-[var(--text-secondary)]">
          <span>{minLabel ?? `${min}${unit}`}</span>
          <span className="text-[var(--accent-primary)] font-semibold">
            Current: {display}
          </span>
          <span>{maxLabel ?? `${max}${unit}`}</span>
        </div>
      </div>
    </div>
  );
};
