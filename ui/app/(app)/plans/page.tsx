"use client";

import { useEffect, useState } from "react";
import { useApp } from "@/app/providers";
import { api } from "@/lib/api";
import type {
  Build,
  Execution,
  Milestone,
  Plan,
  RunManifestEntry,
  Suite,
  TestCase,
} from "@/lib/types";
import {
  Button,
  Cell,
  EmptyState,
  Field,
  Grid,
  Input,
  Panel,
  Row,
  Select,
  Spinner,
  Stat,
  StatusBadge,
  Table,
  Tag,
} from "@/components/ui";

const URGENCY = { 1: "low", 2: "med", 3: "high" } as const;

export default function PlansPage() {
  const { currentProject } = useApp();

  const [plans, setPlans] = useState<Plan[]>([]);
  const [loadingPlans, setLoadingPlans] = useState(true);
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);

  // right-pane data
  const [manifest, setManifest] = useState<RunManifestEntry[]>([]);
  const [builds, setBuilds] = useState<Build[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loadingRight, setLoadingRight] = useState(false);

  // case-picker + dependency state
  const [suites, setSuites] = useState<Suite[]>([]);
  const [pickSuite, setPickSuite] = useState<number | "">("");
  const [suiteCases, setSuiteCases] = useState<TestCase[]>([]);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [urgency, setUrgency] = useState(2);
  const [depFrom, setDepFrom] = useState<number | "">("");
  const [depTo, setDepTo] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!currentProject) return;
    setLoadingPlans(true);
    setSelectedPlan(null);
    api
      .plans(currentProject.id)
      .then((ps) => {
        setPlans(ps);
        setLoadingPlans(false);
      })
      .catch(() => setLoadingPlans(false));
    api.suites(currentProject.id).then(setSuites).catch(() => setSuites([]));
  }, [currentProject]);

  async function refreshManifest(planId: number) {
    setManifest(await api.runManifest(planId).catch(() => [] as RunManifestEntry[]));
  }

  useEffect(() => {
    if (!selectedPlan) return;
    setLoadingRight(true);
    setExecutions([]);
    setErr(null);
    Promise.all([
      refreshManifest(selectedPlan.id),
      api.builds(selectedPlan.id).catch(() => [] as Build[]),
      api.milestones(selectedPlan.id).catch(() => [] as Milestone[]),
      api.planExecutions(selectedPlan.id).catch(() => [] as Execution[]),
    ]).then(([, b, m, e]) => {
      setBuilds(b);
      setMilestones(m);
      setExecutions(e);
      setLoadingRight(false);
    });
  }, [selectedPlan]);

  useEffect(() => {
    if (pickSuite === "") {
      setSuiteCases([]);
      return;
    }
    api.suiteCases(Number(pickSuite)).then(setSuiteCases).catch(() => setSuiteCases([]));
    setPicked(new Set());
  }, [pickSuite]);

  async function handleCreatePlan() {
    if (!currentProject || !newName.trim()) return;
    setCreating(true);
    try {
      await api.createPlan(currentProject.id, newName.trim());
      setNewName("");
      setPlans(await api.plans(currentProject.id));
    } finally {
      setCreating(false);
    }
  }

  async function handleAddCases() {
    if (!selectedPlan || picked.size === 0) return;
    setBusy(true);
    setErr(null);
    try {
      await api.addCases(selectedPlan.id, [...picked], urgency);
      setPicked(new Set());
      await refreshManifest(selectedPlan.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed to add cases");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddDependency() {
    if (!selectedPlan || depFrom === "" || depTo === "" || depFrom === depTo) return;
    setBusy(true);
    setErr(null);
    try {
      await api.addDependency(Number(depFrom), Number(depTo));
      setDepFrom("");
      setDepTo("");
      await refreshManifest(selectedPlan.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed to add dependency (cycle? cross-project?)");
    } finally {
      setBusy(false);
    }
  }

  if (!currentProject) return <EmptyState title="no project selected" hint="create one in Admin" />;
  if (loadingPlans) return <Spinner label="loading plans" />;

  const runnable = manifest.filter((m) => m.runnable).length;
  const blocked = manifest.length - runnable;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mono text-lg font-semibold tracking-wide">TEST PLAN MANAGER</h1>
        <p className="label mt-0.5">
          {currentProject.name} · build the ordered, dependency-gated run list agents execute
        </p>
      </div>

      <div className="grid grid-cols-[280px_1fr] gap-6">
        {/* LEFT: plan list + new plan */}
        <div className="space-y-4">
          <Panel title="plans">
            {plans.length === 0 ? (
              <EmptyState title="no plans yet" />
            ) : (
              <div className="space-y-1">
                {plans.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setSelectedPlan(p)}
                    className={`w-full border px-3 py-2.5 text-left transition-colors ${
                      selectedPlan?.id === p.id
                        ? "border-[var(--color-accent)] bg-[var(--color-bg-elev-2)]"
                        : "border-[var(--color-border)] hover:border-[var(--color-border-bright)] bg-transparent"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="mono text-sm text-[var(--color-text)]">{p.name}</span>
                      <span className="label">{p.is_open ? "open" : "closed"}</span>
                    </div>
                    <div className="mono mt-0.5 text-[0.6875rem] text-[var(--color-text-faint)]">
                      #{p.id} · {p.active ? "active" : "inactive"}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="new plan">
            <div className="space-y-3">
              <Field label="plan name">
                <Input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreatePlan()}
                  placeholder="e.g. sprint-42"
                />
              </Field>
              <Button onClick={handleCreatePlan} disabled={creating || !newName.trim()} className="w-full">
                {creating ? "creating…" : "create plan"}
              </Button>
            </div>
          </Panel>
        </div>

        {/* RIGHT: selected plan */}
        {!selectedPlan ? (
          <div className="flex items-center justify-center">
            <EmptyState title="select a plan" hint="choose a plan to manage its run list" />
          </div>
        ) : loadingRight ? (
          <Spinner label="loading plan data" />
        ) : (
          <div className="space-y-4">
            <Grid cols={4}>
              <Stat label="run list" value={manifest.length} />
              <Stat label="runnable" value={runnable} color="var(--color-pass)" />
              <Stat label="blocked" value={blocked} color="var(--color-blocked)" />
              <Stat label="executions" value={executions.length} />
            </Grid>

            {err && (
              <div
                className="mono text-[0.75rem] border px-3 py-2"
                style={{ borderColor: "var(--color-fail)", color: "var(--color-fail)" }}
              >
                {err}
              </div>
            )}

            {/* RUN MANIFEST — the centerpiece */}
            <Panel title={`run manifest · ${selectedPlan.name}`} pad={false}>
              {manifest.length === 0 ? (
                <div className="p-4">
                  <EmptyState title="empty run list" hint="add cases below to build the manifest" />
                </div>
              ) : (
                <Table head={["#", "case", "name", "imp", "urg", "last run", "gate"]}>
                  {manifest.map((m) => (
                    <Row key={m.case_id}>
                      <Cell mono className="text-[var(--color-text-faint)]">{m.order}</Cell>
                      <Cell mono>{m.external_id}</Cell>
                      <Cell className="text-[var(--color-text-dim)]">{m.name}</Cell>
                      <Cell mono className="text-[var(--color-text-faint)]">P{m.importance}</Cell>
                      <Cell mono>{URGENCY[m.urgency as 1 | 2 | 3] ?? m.urgency}</Cell>
                      <Cell>
                        {m.latest_status === "not_run" ? (
                          <span className="label">not run</span>
                        ) : (
                          <StatusBadge status={m.latest_status} />
                        )}
                      </Cell>
                      <Cell>
                        {m.runnable ? (
                          <span className="label" style={{ color: "var(--color-pass)" }}>
                            ready
                          </span>
                        ) : (
                          <span className="label" style={{ color: "var(--color-blocked)" }}>
                            blocked ← {m.blocked_by.join(", ")}
                          </span>
                        )}
                      </Cell>
                    </Row>
                  ))}
                </Table>
              )}
            </Panel>

            {/* ADD CASES + DEPENDENCY */}
            <div className="grid grid-cols-2 gap-4 items-start">
              <Panel title="add cases">
                <div className="space-y-3">
                  <Field label="suite">
                    <Select
                      value={pickSuite}
                      onChange={(e) => setPickSuite(e.target.value === "" ? "" : Number(e.target.value))}
                    >
                      <option value="">select a suite…</option>
                      {suites.map((s) => (
                        <option key={s.id} value={s.id}>{s.name}</option>
                      ))}
                    </Select>
                  </Field>

                  {pickSuite !== "" && (
                    <div className="max-h-52 overflow-y-auto border border-[var(--color-border)]">
                      {suiteCases.length === 0 ? (
                        <div className="p-3"><EmptyState title="no cases" /></div>
                      ) : (
                        suiteCases.map((c) => (
                          <label
                            key={c.id}
                            className="flex items-center gap-2 border-b border-[var(--color-border)] px-3 py-1.5 text-sm cursor-pointer hover:bg-[var(--color-bg-elev-2)]"
                          >
                            <input
                              type="checkbox"
                              checked={picked.has(c.id)}
                              onChange={(ev) => {
                                const next = new Set(picked);
                                ev.target.checked ? next.add(c.id) : next.delete(c.id);
                                setPicked(next);
                              }}
                            />
                            <span className="mono text-[0.75rem] text-[var(--color-text-faint)]">{c.external_id}</span>
                            <span className="truncate">{c.name}</span>
                          </label>
                        ))
                      )}
                    </div>
                  )}

                  <div className="flex items-end gap-2">
                    <Field label="urgency">
                      <Select value={urgency} onChange={(e) => setUrgency(Number(e.target.value))}>
                        <option value={1}>low</option>
                        <option value={2}>med</option>
                        <option value={3}>high</option>
                      </Select>
                    </Field>
                    <Button onClick={handleAddCases} disabled={busy || picked.size === 0} className="flex-1">
                      {busy ? "…" : `add ${picked.size || ""} to plan`}
                    </Button>
                  </div>
                </div>
              </Panel>

              <Panel title="add dependency">
                <p className="label mb-3">a case won&apos;t be runnable until its prerequisite passes</p>
                <div className="space-y-3">
                  <Field label="case">
                    <Select value={depFrom} onChange={(e) => setDepFrom(e.target.value === "" ? "" : Number(e.target.value))}>
                      <option value="">select case…</option>
                      {manifest.map((m) => (
                        <option key={m.case_id} value={m.case_id}>{m.external_id} · {m.name}</option>
                      ))}
                    </Select>
                  </Field>
                  <Field label="depends on (prerequisite)">
                    <Select value={depTo} onChange={(e) => setDepTo(e.target.value === "" ? "" : Number(e.target.value))}>
                      <option value="">select prerequisite…</option>
                      {manifest.filter((m) => m.case_id !== depFrom).map((m) => (
                        <option key={m.case_id} value={m.case_id}>{m.external_id} · {m.name}</option>
                      ))}
                    </Select>
                  </Field>
                  <Button
                    onClick={handleAddDependency}
                    disabled={busy || depFrom === "" || depTo === "" || depFrom === depTo}
                    className="w-full"
                  >
                    {busy ? "…" : "add dependency"}
                  </Button>
                </div>
              </Panel>
            </div>

            {/* builds + milestones */}
            <div className="grid grid-cols-2 gap-4 items-start">
              <Panel title="builds" pad={false}>
                {builds.length === 0 ? (
                  <div className="p-4"><EmptyState title="no builds" /></div>
                ) : (
                  <Table head={["name", "commit"]}>
                    {builds.map((b) => (
                      <Row key={b.id}>
                        <Cell mono>{b.name}</Cell>
                        <Cell mono className="text-[var(--color-text-faint)] text-[0.75rem]">
                          {b.commit_id ? b.commit_id.slice(0, 10) : "—"}
                        </Cell>
                      </Row>
                    ))}
                  </Table>
                )}
              </Panel>
              <Panel title="milestones" pad={false}>
                {milestones.length === 0 ? (
                  <div className="p-4"><EmptyState title="no milestones" /></div>
                ) : (
                  <Table head={["name", "target"]}>
                    {milestones.map((m) => (
                      <Row key={m.id}>
                        <Cell>{m.name}</Cell>
                        <Cell mono className="text-[var(--color-text-dim)]">{m.target_date ?? "—"}</Cell>
                      </Row>
                    ))}
                  </Table>
                )}
              </Panel>
            </div>

            {/* recent executions */}
            <Panel title="recent executions" pad={false}>
              {executions.length === 0 ? (
                <div className="p-4"><EmptyState title="no executions" /></div>
              ) : (
                <Table head={["id", "status", "version", "build", "created"]}>
                  {executions.slice(0, 10).map((e) => (
                    <Row key={e.id}>
                      <Cell mono className="text-[var(--color-text-faint)]">#{e.id}</Cell>
                      <Cell><StatusBadge status={e.status} /></Cell>
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
        )}
      </div>
    </div>
  );
}
