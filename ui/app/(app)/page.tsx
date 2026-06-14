"use client";

import { useEffect, useState } from "react";
import { useApp } from "@/app/providers";
import { api } from "@/lib/api";
import type { Execution, Plan } from "@/lib/types";
import { Cell, EmptyState, Grid, Panel, Row, Spinner, Stat, StatusBadge, Table } from "@/components/ui";

interface Tally {
  pass: number;
  fail: number;
  blocked: number;
  other: number;
  total: number;
}

export default function Dashboard() {
  const { currentProject } = useApp();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [recent, setRecent] = useState<Execution[]>([]);
  const [tally, setTally] = useState<Tally>({ pass: 0, fail: 0, blocked: 0, other: 0, total: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!currentProject) return;
    setLoading(true);
    (async () => {
      const ps = await api.plans(currentProject.id);
      setPlans(ps);
      const execLists = await Promise.all(ps.map((p) => api.planExecutions(p.id).catch(() => [])));
      const all = execLists.flat();
      const t: Tally = { pass: 0, fail: 0, blocked: 0, other: 0, total: all.length };
      for (const e of all) {
        if (e.status === "pass") t.pass++;
        else if (e.status === "fail") t.fail++;
        else if (e.status === "blocked") t.blocked++;
        else t.other++;
      }
      setTally(t);
      setRecent(
        [...all].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)).slice(0, 12),
      );
      setLoading(false);
    })();
  }, [currentProject]);

  if (!currentProject) return <EmptyState title="no project selected" hint="create one in Admin" />;
  if (loading) return <Spinner label="loading dashboard" />;

  const passRate = tally.total ? Math.round((tally.pass / tally.total) * 100) : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mono text-lg font-semibold tracking-wide">{currentProject.name}</h1>
        <p className="label mt-0.5">{currentProject.prefix} · operational overview</p>
      </div>

      <Grid cols={5}>
        <Stat label="executions" value={tally.total} />
        <Stat label="pass rate" value={`${passRate}%`} color="var(--color-pass)" />
        <Stat label="passing" value={tally.pass} color="var(--color-pass)" />
        <Stat label="failing" value={tally.fail} color="var(--color-fail)" />
        <Stat label="blocked" value={tally.blocked} color="var(--color-blocked)" />
      </Grid>

      <div className="grid grid-cols-[1fr_1.4fr] gap-6">
        <Panel title="test plans">
          {plans.length === 0 ? (
            <EmptyState title="no plans yet" />
          ) : (
            <div className="space-y-3">
              {plans.map((p) => (
                <div key={p.id} className="border border-[var(--color-border)] px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="mono text-sm">{p.name}</span>
                    <span className="label">{p.is_open ? "open" : "closed"}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="recent executions" pad={false}>
          {recent.length === 0 ? (
            <div className="p-4">
              <EmptyState title="no executions recorded" />
            </div>
          ) : (
            <Table head={["exec", "status", "version", "build", "when"]}>
              {recent.map((e) => (
                <Row key={e.id}>
                  <Cell mono>#{e.id}</Cell>
                  <Cell>
                    <StatusBadge status={e.status} />
                  </Cell>
                  <Cell mono>v{e.version_id}</Cell>
                  <Cell mono>{e.build_id ? `b${e.build_id}` : "—"}</Cell>
                  <Cell mono className="text-[var(--color-text-faint)]">
                    {new Date(e.created_at).toLocaleString()}
                  </Cell>
                </Row>
              ))}
            </Table>
          )}
        </Panel>
      </div>
    </div>
  );
}
