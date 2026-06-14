"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "@/app/providers";

const NAV: { group: string; items: { href: string; label: string; glyph: string }[] }[] = [
  {
    group: "Design",
    items: [
      { href: "/", label: "Dashboard", glyph: "◉" },
      { href: "/suites", label: "Suites", glyph: "⊟" },
      { href: "/plans", label: "Plans", glyph: "◫" },
      { href: "/requirements", label: "Requirements", glyph: "❡" },
    ],
  },
  {
    group: "Supervision",
    items: [
      { href: "/activity", label: "Activity", glyph: "≋" },
      { href: "/evidence", label: "Evidence", glyph: "❖" },
      { href: "/claims", label: "Claims", glyph: "⊕" },
    ],
  },
  {
    group: "Insight",
    items: [
      { href: "/traceability", label: "Traceability", glyph: "⊞" },
      { href: "/reports", label: "Reports", glyph: "▤" },
    ],
  },
  { group: "System", items: [{ href: "/admin", label: "Admin", glyph: "⚙" }] },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, projects, currentProject, setCurrentProject, logout } = useApp();

  return (
    <div className="flex min-h-screen">
      {/* nav rail */}
      <aside className="fixed left-0 top-0 z-20 flex h-screen w-[220px] flex-col border-r border-[var(--color-border)] bg-[var(--color-bg-elev)]">
        <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-4 py-4">
          <span
            className="mono text-lg font-bold"
            style={{ color: "var(--color-accent)", textShadow: "0 0 12px var(--color-accent-dim)" }}
          >
            ▰
          </span>
          <span className="mono text-sm font-bold tracking-widest">AGENTQA</span>
        </div>
        <nav className="flex-1 overflow-y-auto py-3">
          {NAV.map((g) => (
            <div key={g.group} className="mb-4">
              <div className="label px-4 pb-1.5 !text-[0.625rem] !text-[var(--color-text-faint)]">{g.group}</div>
              {g.items.map((it) => {
                const active = pathname === it.href || (it.href !== "/" && pathname.startsWith(it.href));
                return (
                  <Link
                    key={it.href}
                    href={it.href}
                    className={`flex items-center gap-3 px-4 py-2 text-sm transition-colors ${
                      active
                        ? "bg-[var(--color-bg-elev-2)] text-[var(--color-accent)]"
                        : "text-[var(--color-text-dim)] hover:bg-[var(--color-bg-elev-2)] hover:text-[var(--color-text)]"
                    }`}
                    style={active ? { boxShadow: "inset 2px 0 0 var(--color-accent)" } : undefined}
                  >
                    <span className="w-4 text-center text-base leading-none">{it.glyph}</span>
                    <span className="mono text-[0.8125rem] tracking-wide">{it.label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="border-t border-[var(--color-border)] px-4 py-3">
          <div className="label !text-[0.625rem]">operator</div>
          <div className="mono mt-0.5 truncate text-sm text-[var(--color-text)]">{user?.login ?? "—"}</div>
          <button
            onClick={logout}
            className="label mt-2 text-[var(--color-text-faint)] hover:text-[var(--color-fail)]"
          >
            sign out →
          </button>
        </div>
      </aside>

      {/* main */}
      <div className="ml-[220px] flex w-[calc(100%-220px)] flex-col">
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-[var(--color-border)] bg-[color-mix(in_srgb,var(--color-bg)_85%,transparent)] px-6 py-3 backdrop-blur">
          <div className="flex items-center gap-3">
            <span className="label">project</span>
            <select
              value={currentProject?.id ?? ""}
              onChange={(e) => {
                const p = projects.find((x) => x.id === Number(e.target.value));
                if (p) setCurrentProject(p);
              }}
              className="mono border border-[var(--color-border-bright)] bg-[var(--color-bg)] px-2 py-1 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
            >
              {projects.length === 0 && <option value="">no projects</option>}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.prefix} · {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-[var(--color-pass)] pulse" style={{ boxShadow: "0 0 8px var(--color-pass)" }} />
            <span className="label">online</span>
          </div>
        </header>
        <main className="flex-1 px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
