import type { ButtonHTMLAttributes, ReactNode } from "react";

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

export function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`block text-sm ${className}`}>
      <span className="text-ink/80">{label}</span>
      {children}
    </label>
  );
}
