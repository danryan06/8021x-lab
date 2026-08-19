import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { useState } from "react";

/**
 * Small "i" affordance that reveals a fly-out on hover *and* keyboard focus.
 * Accessible: the trigger is a real button, the panel is role="tooltip", and
 * `group-focus-within` keeps it open for keyboard/touch users. The panel is a
 * DOM descendant of the group, so hovering the panel itself keeps it open.
 */
export function InfoTip({
  label = "More information",
  children,
}: {
  label?: string;
  children: ReactNode;
}) {
  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-label={label}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-ink/40 text-[10px] font-bold leading-none text-ink/60 transition hover:border-signal hover:text-signal focus:outline-none focus-visible:ring-2 focus-visible:ring-signal"
      >
        i
      </button>
      <span
        role="tooltip"
        className="invisible absolute left-0 top-6 z-30 w-72 max-w-[80vw] rounded border border-ink/15 bg-panel p-3 text-left text-xs font-normal leading-relaxed text-ink/80 opacity-0 shadow-soft transition duration-150 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
      >
        {children}
      </span>
    </span>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <section className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-3xl font-bold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-ink/70">{subtitle}</p>}
      </div>
      {actions}
    </section>
  );
}

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`ui-panel p-5 ${className}`}>{children}</section>;
}

export function StatusBanner({
  tone,
  children,
}: {
  tone: "ok" | "error" | "info";
  children: ReactNode;
}) {
  const styles =
    tone === "ok"
      ? "border-signal/30 bg-signal/10 text-signal"
      : tone === "error"
        ? "border-fail/30 bg-fail/10 text-fail"
        : "border-ink/10 bg-panel/70 text-ink/80";
  return <p className={`border px-3 py-2 text-sm ${styles}`}>{children}</p>;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "signal" | "ghost";
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonProps) {
  const base =
    variant === "signal"
      ? "ui-btn-signal"
      : variant === "ghost"
        ? "ui-btn-ghost"
        : "ui-btn-primary";
  return <button type={props.type || "button"} className={`${base} ${className}`} {...props} />;
}

const VLAN_ATTRIBUTE = "tunnel-private-group-id";
const ROLE_ATTRIBUTE = "filter-id";
// Plumbing that carries the VLAN assignment but says nothing on its own.
const VLAN_PLUMBING = ["tunnel-type", "tunnel-medium-type"];

/**
 * Reply attributes FreeRADIUS returned with an Access-Accept.
 * Simple mode reads them as "VLAN 20 · role guest-acl"; Advanced mode lists every
 * attribute under its real RADIUS name.
 */
export function ReplyAttributes({
  attributes,
  verbose = false,
}: {
  attributes: Record<string, string> | null | undefined;
  verbose?: boolean;
}) {
  const entries = Object.entries(attributes || {});
  if (entries.length === 0) return <span className="text-ink/50">—</span>;

  if (verbose) {
    return (
      <ul className="space-y-0.5 font-mono text-xs">
        {entries.map(([name, value]) => (
          <li key={name}>
            <span className="text-ink/60">{name}</span> = {value}
          </li>
        ))}
      </ul>
    );
  }

  const chips = entries
    .filter(([name]) => !VLAN_PLUMBING.includes(name.toLowerCase()))
    .map(([name, value]) => {
      const key = name.toLowerCase();
      if (key === VLAN_ATTRIBUTE) return { key: name, label: `VLAN ${value}` };
      if (key === ROLE_ATTRIBUTE) return { key: name, label: `role ${value}` };
      return { key: name, label: `${name} ${value}` };
    });

  if (chips.length === 0) return <span className="text-ink/50">—</span>;

  return (
    <span className="flex flex-wrap gap-1">
      {chips.map((chip) => (
        <span
          key={chip.key}
          className="border border-signal/40 bg-signal/10 px-1.5 py-0.5 text-xs text-ink/80"
        >
          {chip.label}
        </span>
      ))}
    </span>
  );
}

export function Field({
  label,
  tip,
  children,
  className = "",
}: {
  label: string;
  tip?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`block text-sm ${className}`}>
      <span className="inline-flex items-center gap-1.5 text-ink/80">
        {label}
        {tip}
      </span>
      {children}
    </label>
  );
}

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

/**
 * Password field with the same Reveal/Hide control used for RADIUS shared secrets.
 * Masked while typing; Reveal shows the value without leaving the field.
 */
export function PasswordInput({ className = "ui-input", ...props }: PasswordInputProps) {
  const [revealed, setRevealed] = useState(false);
  return (
    <span className="flex items-center gap-2">
      <input
        {...props}
        type={revealed ? "text" : "password"}
        className={`min-w-0 flex-1 ${className}`}
      />
      <button
        type="button"
        className="mt-1 shrink-0 text-xs text-signal underline-offset-2 hover:underline"
        aria-pressed={revealed}
        aria-label={revealed ? "Hide password" : "Reveal password"}
        onClick={(event) => {
          event.preventDefault();
          setRevealed((value) => !value);
        }}
      >
        {revealed ? "Hide" : "Reveal"}
      </button>
    </span>
  );
}
