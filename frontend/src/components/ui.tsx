import type { ButtonHTMLAttributes, ReactNode } from "react";

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
