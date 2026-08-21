"use client";

import React from "react";
import { motion, HTMLMotionProps } from "framer-motion";

export interface AppShellProps {
  children: React.ReactNode;
  header?: React.ReactNode;
  sidebar?: React.ReactNode;
  className?: string;
}

export function AppShell({ children, header, sidebar, className = "" }: AppShellProps) {
  return (
    <main
      className={`min-h-screen flex flex-col font-[family-name:var(--font-family-body)] ${className}`}
      style={{ backgroundColor: "var(--color-background-body)", color: "var(--color-accent)" }}
    >
      {header && (
        <header
          className="border-b px-6 py-4 sticky top-0 z-40 flex items-center justify-between backdrop-blur-md"
          style={{
            backgroundColor: "color-mix(in srgb, var(--color-background-surface) 85%, transparent)",
            borderColor: "var(--color-border)",
          }}
        >
          {header}
        </header>
      )}
      <section className="flex-1 flex overflow-hidden">
        {sidebar && (
          <aside
            className="w-80 border-r p-4 overflow-y-auto flex flex-col gap-4"
            style={{
              backgroundColor: "color-mix(in srgb, var(--color-background-surface) 50%, transparent)",
              borderColor: "var(--color-border)",
            }}
          >
            {sidebar}
          </aside>
        )}
        <section className="flex-1 flex flex-col overflow-y-auto relative p-6 gap-6">
          {children}
        </section>
      </section>
    </main>
  );
}

export interface PanelProps extends HTMLMotionProps<"section"> {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  action?: React.ReactNode;
}

export function Panel({ children, title, subtitle, action, className = "", ...props }: PanelProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className={`border rounded-[var(--radius-container)] p-5 flex flex-col gap-4 ${className}`}
      style={{
        backgroundColor: "var(--color-background-surface)",
        borderColor: "var(--color-border)",
        boxShadow: "var(--elevation-medium)",
      }}
      {...props}
    >
      {(title || subtitle || action) && (
        <header
          className="flex items-center justify-between border-b pb-3"
          style={{ borderColor: "var(--color-border)" }}
        >
          <section className="flex flex-col">
            {title && (
              <h2 className="text-lg font-semibold tracking-wide font-[family-name:var(--font-family-display)] text-[var(--color-accent)]">
                {title}
              </h2>
            )}
            {subtitle && <p className="text-xs opacity-60 tracking-wider uppercase">{subtitle}</p>}
          </section>
          {action && <section>{action}</section>}
        </header>
      )}
      <section className="flex-1 flex flex-col gap-3">{children}</section>
    </motion.section>
  );
}

export interface StatusDotProps {
  status: "active" | "idle" | "error" | "alert" | string;
  label?: string;
}

export function StatusDot({ status, label }: StatusDotProps) {
  const getColorClass = () => {
    switch (status.toLowerCase()) {
      case "active":
      case "happy":
      case "online":
        return "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]";
      case "alert":
      case "drama":
      case "high":
        return "bg-[var(--color-accent)] shadow-[0_0_10px_var(--color-accent)] animate-pulse";
      case "idle":
      case "calm":
      case "contemplative":
        return "bg-[var(--color-accent-secondary)] shadow-[0_0_8px_var(--color-accent-secondary)]";
      default:
        return "bg-white/40";
    }
  };

  return (
    <span className="inline-flex items-center gap-2 text-xs font-medium tracking-wide text-white/80">
      <span className={`w-2 h-2 rounded-full inline-block ${getColorClass()}`} />
      {label && <span>{label}</span>}
    </span>
  );
}

export interface BadgeProps {
  count?: number | string;
  label?: string;
  variant?: "default" | "accent" | "secondary";
}

export function Badge({ count, label, variant = "default" }: BadgeProps) {
  const getVariantStyles = () => {
    switch (variant) {
      case "accent":
        return "bg-[var(--color-accent)]/20 text-[var(--color-accent)] border-[var(--color-accent)]/40";
      case "secondary":
        return "bg-[var(--color-accent-secondary)]/20 text-[var(--color-accent-secondary)] border-[var(--color-accent-secondary)]/40";
      default:
        return "bg-white/10 text-white/80 border-white/20";
    }
  };

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono border ${getVariantStyles()}`}>
      {label && <span>{label}</span>}
      {count !== undefined && <span className="font-bold">{count}</span>}
    </span>
  );
}

export interface ProgressBarProps {
  value: number;
  label?: string;
  variant?: "default" | "accent" | "danger";
}

export function ProgressBar({ value, label, variant = "accent" }: ProgressBarProps) {
  const getGradient = () => {
    switch (variant) {
      case "danger":
        return "from-red-600 to-amber-500";
      case "accent":
        return "from-[var(--color-accent)] to-[var(--color-accent-secondary)]";
      default:
        return "from-blue-500 to-emerald-400";
    }
  };

  return (
    <section className="flex flex-col gap-1 w-full">
      {label && (
        <header className="flex justify-between items-center text-xs font-mono">
          <span className="text-white/70">{label}</span>
          <span className="font-bold text-[var(--color-accent)]">{Math.round(value)}%</span>
        </header>
      )}
      <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden p-0.5 border border-white/5">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, Math.max(0, value))}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className={`h-full rounded-full bg-gradient-to-r ${getGradient()} shadow-[0_0_10px_rgba(232,176,75,0.4)]`}
        />
      </div>
    </section>
  );
}

export interface TelemetryStatProps {
  label: string;
  value: string | number;
  unit?: string;
  subtext?: string;
  status?: "normal" | "warning" | "optimal";
}

export function TelemetryStat({ label, value, unit, subtext }: TelemetryStatProps) {
  return (
    <article className="p-3 bg-black/40 rounded border border-white/5 flex flex-col justify-between gap-1 hover:border-white/20 transition-all shadow-inner">
      <span className="text-[10px] font-mono text-white/50 uppercase tracking-widest block">{label}</span>
      <section className="flex items-baseline gap-1">
        <span className="text-xl md:text-2xl font-bold font-mono tracking-tight text-[var(--color-accent)]">{value}</span>
        {unit && <span className="text-xs font-mono text-white/60">{unit}</span>}
      </section>
      {subtext && <span className="text-[10px] font-mono text-white/40 italic">{subtext}</span>}
    </article>
  );
}

export interface FeaturedCardProps {
  title: string;
  subtitle?: string;
  description: string;
  badge?: string;
  icon?: React.ReactNode;
}

export function FeaturedCard({ title, subtitle, description, badge, icon }: FeaturedCardProps) {
  return (
    <article
      className="p-6 rounded-lg border flex flex-col justify-between gap-4 group"
      style={{
        backgroundColor: "var(--color-background-surface)",
        borderColor: "var(--color-border)",
        boxShadow: "var(--elevation-small)",
        transition: "transform 0.3s ease, box-shadow 0.3s ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = "translateY(-4px)";
        e.currentTarget.style.boxShadow = "var(--elevation-large)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = "translateY(0)";
        e.currentTarget.style.boxShadow = "var(--elevation-small)";
      }}
    >
      <header className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          {badge && <Badge label={badge} variant="accent" />}
          {icon && <span className="text-[var(--color-accent)] text-xl group-hover:scale-110 transition-transform">{icon}</span>}
        </div>
        <h3 className="font-[family-name:var(--font-family-display)] text-xl font-bold text-[var(--color-accent)] transition-colors">
          {title}
        </h3>
        {subtitle && <span className="text-xs font-mono opacity-60 uppercase tracking-wider">{subtitle}</span>}
      </header>
      <p className="text-sm opacity-80 font-[family-name:var(--font-family-body)] leading-relaxed">
        {description}
      </p>
    </article>
  );
}
