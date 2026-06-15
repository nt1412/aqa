// Typed fetch client for the AQA backend. All calls go to same-origin /api
// (proxied to FastAPI by next.config.mjs). The bearer token is read from
// localStorage on each call so it survives reloads.

import type {
  Artifact,
  Assignment,
  Build,
  Claim,
  CoverageGap,
  EvidenceBundle,
  Execution,
  FailureContext,
  Milestone,
  Plan,
  Platform,
  Project,
  Requirement,
  ReqSpec,
  RunManifestEntry,
  SimilarFailure,
  Suite,
  SuiteNode,
  TestCase,
  TraceabilityRow,
  User,
} from "./types";

const TOKEN_KEY = "aqa_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  params?: Record<string, string | number | undefined>,
): Promise<T> {
  const token = getToken();
  const qs = params
    ? "?" +
      Object.entries(params)
        .filter(([, v]) => v !== undefined)
        .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
        .join("&")
    : "";
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token) headers["authorization"] = `Bearer ${token}`;
  const res = await fetch(`/api/v1${path}${qs}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  // auth
  login: (login: string, password: string) =>
    request<{ access_token: string }>("POST", "/auth/login", { login, password }),
  me: () => request<User>("GET", "/auth/me"),
  issueKey: () => request<{ api_key: string }>("POST", "/auth/token"),

  // projects / structure
  projects: () => request<Project[]>("GET", "/projects"),
  project: (id: number) => request<Project>("GET", `/projects/${id}`),
  createProject: (name: string, prefix: string) =>
    request<Project>("POST", "/projects", { name, prefix }),
  suites: (projectId: number) => request<Suite[]>("GET", `/projects/${projectId}/suites`),
  suiteTree: (suiteId: number) => request<SuiteNode[]>("GET", `/suites/${suiteId}/tree`),
  suiteCases: (suiteId: number) => request<TestCase[]>("GET", `/suites/${suiteId}/cases`),
  createSuite: (projectId: number, name: string, parentId?: number) =>
    request<Suite>("POST", `/projects/${projectId}/suites`, { name, parent_id: parentId ?? null }),
  case: (id: number) => request<TestCase>("GET", `/cases/${id}`),
  caseExecutions: (id: number) => request<Execution[]>("GET", `/cases/${id}/executions`),
  platforms: (projectId: number) => request<Platform[]>("GET", `/projects/${projectId}/platforms`),

  // plans / builds
  plans: (projectId: number) => request<Plan[]>("GET", `/projects/${projectId}/plans`),
  createPlan: (projectId: number, name: string) =>
    request<Plan>("POST", `/projects/${projectId}/plans`, { name }),
  planCases: (planId: number) => request<unknown[]>("GET", `/plans/${planId}/cases`),
  builds: (planId: number) => request<Build[]>("GET", `/plans/${planId}/builds`),
  milestones: (planId: number) => request<Milestone[]>("GET", `/plans/${planId}/milestones`),
  planExecutions: (planId: number) => request<Execution[]>("GET", `/plans/${planId}/executions`),
  addCases: (planId: number, caseIds: number[], urgency = 2) =>
    request<unknown[]>("POST", `/plans/${planId}/cases`, { case_ids: caseIds, urgency }),
  runManifest: (planId: number, buildId?: number) =>
    request<RunManifestEntry[]>("GET", `/plans/${planId}/manifest`, undefined, {
      build_id: buildId,
    }),
  addDependency: (caseId: number, dependsOnCaseId: number) =>
    request<{ case_id: number; depends_on_case_id: number }>(
      "POST",
      `/cases/${caseId}/dependencies`,
      { depends_on_case_id: dependsOnCaseId },
    ),

  // executions
  execution: (id: number) => request<Execution>("GET", `/executions/${id}`),
  artifacts: (executionId: number) =>
    request<Artifact[]>("GET", `/executions/${executionId}/artifacts`),

  // evidence / claims
  evidence: (caseId: number) => request<EvidenceBundle>("GET", `/cases/${caseId}/evidence`),
  failureContext: (caseId: number) =>
    request<FailureContext>("GET", `/cases/${caseId}/failure-context`),
  similarFailures: (caseId: number) =>
    request<SimilarFailure[]>("GET", `/cases/${caseId}/similar-failures`),
  unverifiedClaims: (planId?: number) =>
    request<Claim[]>("GET", "/claims/unverified", undefined, { plan_id: planId }),
  claims: (projectId?: number, planId?: number) =>
    request<Claim[]>("GET", "/claims", undefined, { project_id: projectId, plan_id: planId }),
  verifyClaim: (claimId: number, verdict: string, reasoning?: Record<string, unknown>) =>
    request<unknown>("POST", `/claims/${claimId}/verify`, { verdict, reasoning }),
  agentHistory: (agentId: number) =>
    request<Execution[]>("GET", `/agents/${agentId}/executions`),

  // requirements / traceability
  reqSpecs: (projectId: number) => request<ReqSpec[]>("GET", `/projects/${projectId}/req-specs`),
  requirements: (specId: number) =>
    request<Requirement[]>("GET", `/req-specs/${specId}/requirements`),
  traceability: (projectId: number) =>
    request<TraceabilityRow[]>("GET", `/projects/${projectId}/traceability`),
  coverageGaps: (projectId: number) =>
    request<CoverageGap[]>("GET", `/projects/${projectId}/coverage-gaps`),

  // assignments
  assignments: (planId?: number) =>
    request<Assignment[]>("GET", "/assignments", undefined, { plan_id: planId }),
};
