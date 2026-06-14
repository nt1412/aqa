"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

/* ---------- status / verdict color maps ---------- */

const STATUS_COLOR: Record<string, string> = {
  pass: "var(--color-pass)",
  fail: "var(--color-fail)",
  blocked: "var(--color-blocked)",
  not_run: "var(--color-notrun)",
  in_progress: "var(--color-progress)",
  confirmed: "var(--color-confirmed)",
  refuted: "var(--color-refuted)",
  inconclusive: "var(--color-inconclusive)",
};

export function statusColor(s: string): string {
  return STATUS_COLOR[s] ?? "var(--color-text-faint)";
}

export function StatusBadge({ status }: { status: string }) {
  const color = statusColor(status);
  const pulsing = status === "in_progress";
  return (
    <span className="inline-flex items-center gap-1.5 mono text-[0.6875rem] uppercase tracking-wider">
      <span
        className={`inline-block h-2 w-2 rounded-full ${pulsing ? "pulse" : ""}`}
        style={{ background: color, boxShadow: `0 0 8px -1px ${color}` }}
      />
      <span style={{ color }}>{status.replace("_", " ")}</span>
    </span>
  );
}

/* ---------- panel ---------- */

export function Panel({
  title,
  actions,
  children,
  className = "",
  pad = true,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  pad?: boolean;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className={`border bg-[var(--color-bg-elev)] ${className}`}
      style={{ borderColor: "var(--color-border)" }}
    >
      {title && (
        <header className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-2.5">
          <h2 className="label !text-[var(--color-text-dim)]">{title}</h2>
          {actions}
        </header>
      )}
      <div className={pad ? "p-4" : ""}>{children}</div>
    </motion.section>
  );
}

/* ---------- buttons ---------- */

export function Button({
  children,
  onClick,
  variant = "primary",
  type = "button",
  disabled,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "danger";
  type?: "button" | "submit";
  disabled?: boolean;
  className?: string;
}) {
  const base =
    "mono text-[0.75rem] uppercase tracking-wider px-3.5 py-2 transition-colors disabled:opacity-40 disabled:cursor-not-allowed border";
  const styles: Record<string, string> = {
    primary:
      "bg-[var(--color-accent)] text-black border-[var(--color-accent)] hover:bg-[var(--color-accent-dim)] hover:border-[var(--color-accent-dim)] font-semibold",
    ghost:
      "bg-transparent text-[var(--color-text-dim)] border-[var(--color-border-bright)] hover:text-[var(--color-text)] hover:border-[var(--color-text-faint)]",
    danger:
      "bg-transparent text-[var(--color-fail)] border-[var(--color-fail)] hover:bg-[var(--color-fail)] hover:text-black",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`${base} ${styles[variant]} ${className}`}>
      {children}
    </button>
  );
}

/* ---------- stat tile ---------- */

export function Stat({
  label,
  value,
  color,
  hint,
}: {
  label: string;
  value: ReactNode;
  color?: string;
  hint?: string;
}) {
  return (
    <div className="border border-[var(--color-border)] bg-[var(--color-bg-elev)] px-4 py-3">
      <div className="label">{label}</div>
      <div className="mono mt-1 text-2xl font-semibold" style={{ color: color ?? "var(--color-text)" }}>
        {value}
      </div>
      {hint && <div className="mono mt-0.5 text-[0.6875rem] text-[var(--color-text-faint)]">{hint}</div>}
    </div>
  );
}

/* ---------- table ---------- */

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border-bright)]">
            {head.map((h) => (
              <th key={h} className="label py-2 px-3 text-left font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Row({ children, onClick }: { children: ReactNode; onClick?: () => void }) {
  return (
    <tr
      onClick={onClick}
      className={`border-b border-[var(--color-border)] transition-colors hover:bg-[var(--color-bg-elev-2)] ${
        onClick ? "cursor-pointer" : ""
      }`}
    >
      {children}
    </tr>
  );
}

export function Cell({ children, mono = false, className = "" }: { children: ReactNode; mono?: boolean; className?: string }) {
  return <td className={`py-2.5 px-3 ${mono ? "mono text-[0.8125rem]" : ""} ${className}`}>{children}</td>;
}

/* ---------- form fields ---------- */

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}

const inputCls =
  "w-full bg-[var(--color-bg)] border border-[var(--color-border-bright)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)] transition-colors";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputCls} ${props.className ?? ""}`} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${inputCls} font-[family-name:var(--font-sans)] ${props.className ?? ""}`} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputCls} ${props.className ?? ""}`} />;
}

/* ---------- misc ---------- */

export function Tag({ children, color }: { children: ReactNode; color?: string }) {
  return (
    <span
      className="mono inline-block border px-1.5 py-0.5 text-[0.625rem] uppercase tracking-wider"
      style={{ borderColor: color ?? "var(--color-border-bright)", color: color ?? "var(--color-text-dim)" }}
    >
      {children}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-10 justify-center text-[var(--color-text-faint)]">
      <span className="inline-block h-3 w-3 animate-spin border border-[var(--color-accent)] border-t-transparent rounded-full" />
      <span className="label">{label ?? "loading"}</span>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="border border-dashed border-[var(--color-border-bright)] py-12 text-center">
      <div className="mono text-sm text-[var(--color-text-dim)]">{title}</div>
      {hint && <div className="mono mt-1 text-[0.6875rem] text-[var(--color-text-faint)]">{hint}</div>}
    </div>
  );
}

export function Grid({ children, cols = 3 }: { children: ReactNode; cols?: number }) {
  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: 0.06 } } }}
      className="grid gap-3"
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
    >
      {children}
    </motion.div>
  );
}
