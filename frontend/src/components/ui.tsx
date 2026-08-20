import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * Small "i" affordance that reveals a fly-out on hover *and* keyboard focus.
 * The panel is portaled to document.body with position:fixed so overflow and
 * stacking contexts (tables, backdrop-blur panels) cannot clip or cover it.
 */
export function InfoTip({
  label = "More information",
  children,
}: {
  label?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLSpanElement>(null);
  const hideTimer = useRef<number | null>(null);

  function show() {
    if (hideTimer.current !== null) {
      window.clearTimeout(hideTimer.current);
      hideTimer.current = null;
    }
    setOpen(true);
  }

  function hideSoon() {
    if (hideTimer.current !== null) window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => setOpen(false), 120);
  }

  useLayoutEffect(() => {
    return () => {
      if (hideTimer.current !== null) window.clearTimeout(hideTimer.current);
    };
  }, []);

  useLayoutEffect(() => {
    if (!open) return;

    const place = () => {
      const button = buttonRef.current;
      const tooltip = tooltipRef.current;
      if (!button || !tooltip) return;
      const anchor = button.getBoundingClientRect();
      const width = tooltip.offsetWidth;
      const height = tooltip.offsetHeight;
      let left = anchor.left;
      if (left + width > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - width - 8);
      }
      if (left < 8) left = 8;
      let top = anchor.bottom + 8;
      if (top + height > window.innerHeight - 8 && anchor.top - height - 8 >= 8) {
        top = anchor.top - height - 8;
      }
      tooltip.style.top = `${top}px`;
      tooltip.style.left = `${left}px`;
    };

    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, children]);

  return (
    <span className="inline-flex align-middle">
      <button
        ref={buttonRef}
        type="button"
        aria-label={label}
        aria-expanded={open}
        onMouseEnter={show}
        onMouseLeave={hideSoon}
        onFocus={show}
        onBlur={hideSoon}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-ink/40 text-[10px] font-bold leading-none text-ink/60 transition hover:border-signal hover:text-signal focus:outline-none focus-visible:ring-2 focus-visible:ring-signal"
      >
        i
      </button>
      {open &&
        createPortal(
          <span
            ref={tooltipRef}
            role="tooltip"
            onMouseEnter={show}
            onMouseLeave={hideSoon}
            className="pointer-events-auto fixed z-[9999] w-72 max-w-[80vw] rounded border border-ink/15 bg-panel p-3 text-left text-xs font-normal leading-relaxed text-ink/80 shadow-soft"
            style={{ top: 0, left: 0 }}
          >
            {children}
          </span>,
          document.body,
        )}
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
