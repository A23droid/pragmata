const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface HealthStatus {
  status: string;
  version: string;
  environment: string;
  database: string;
}

export interface ConversationReference {
  id: string;
  issue_id: string;
  room_id: string;
  channel_type: "INVESTIGATION" | "RESOLUTION" | "IMPLEMENTATION" | "GENERAL";
  external_thread_id?: string;
  metadata_json: Record<string, any>;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  issue_id: string;
  event_type: string;
  from_state?: string | null;
  to_state?: string | null;
  actor: string;
  payload: Record<string, any>;
  created_at: string;
}

export interface Approval {
  id: string;
  issue_id: string;
  decision: string;
  target_stage: string;
  actor: string;
  notes?: string;
  created_at: string;
}

export interface Issue {
  id: string;
  project_id: string;
  title: string;
  description: string;
  expected_behavior?: string;
  steps_attempted?: string;
  reporter_environment?: Record<string, any>;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface IssueDetail extends Issue {
  project?: {
    id: string;
    name: string;
    repo_url: string;
    default_branch: string;
  };
  approvals: Approval[];
  audit_events: AuditEvent[];
  conversations?: ConversationReference[];
}

export interface SwitchStatus {
  switch_base_url: string;
  connected: boolean;
  registered_agents: string[];
  active_rooms: string[];
}

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchIssues(status?: string): Promise<Issue[]> {
  const url = new URL(`${API_BASE}/api/v1/issues`);
  if (status) {
    url.searchParams.set("status", status);
  }
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to fetch issues: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchIssueDetail(id: string): Promise<IssueDetail> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch issue details: ${res.statusText}`);
  }
  return res.json();
}

export async function createIssue(data: {
  title: string;
  description: string;
  expected_behavior?: string;
  steps_attempted?: string;
  reporter_environment?: Record<string, any>;
}): Promise<Issue> {
  const res = await fetch(`${API_BASE}/api/v1/issues`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to create issue");
  }
  return res.json();
}

export async function triageIssue(
  id: string,
  decision: "ACCEPTED" | "REJECTED" | "REQUEST_INFORMATION" | "DEFERRED",
  actor: string,
  notes?: string
): Promise<Issue> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(id)}/triage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, actor, notes }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Triage failed");
  }
  return res.json();
}

export async function transitionIssue(
  id: string,
  targetStatus: string,
  actor: string,
  reason?: string
): Promise<Issue> {
  const res = await fetch(
    `${API_BASE}/api/v1/issues/${encodeURIComponent(id)}/transition`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_status: targetStatus, actor, reason }),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Transition failed");
  }
  return res.json();
}

export async function fetchSwitchStatus(): Promise<SwitchStatus> {
  const res = await fetch(`${API_BASE}/api/v1/switch/status`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error("Failed to fetch Switch status");
  }
  return res.json();
}

export async function fetchIssueRooms(id: string): Promise<any[]> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(id)}/rooms`, {
    cache: "no-store",
  });
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export interface RepoInspectionResult {
  commit_sha: string;
  branch: string;
  total_files: number;
  detected_languages: string[];
  detected_frameworks: string[];
  test_commands: string[];
  file_tree: Array<{ path: string; name: string; size_bytes: number; depth: number }>;
  readme_snippet?: string;
  config_files: string[];
  search_results: Array<{ file_path: string; line_number: number; line_content: string }>;
}

export interface SandboxExecutionResult {
  command: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_seconds: number;
  timed_out: boolean;
  error_message?: string;
}

export interface EvidenceItem {
  id: string;
  issue_id: string;
  investigation_id?: string;
  evidence_type: string;
  content: string;
  tool_name?: string;
  exit_code?: number;
  file_path?: string;
  provenance: string;
  created_at: string;
}

export async function inspectRepository(
  issueId: string,
  searchQuery?: string
): Promise<RepoInspectionResult> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/inspect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ search_query: searchQuery || undefined }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Repository inspection failed");
  }
  return res.json();
}

export async function runSandbox(
  issueId: string,
  command: string,
  timeoutSeconds: number = 30
): Promise<SandboxExecutionResult> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/sandbox`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, timeout_seconds: timeoutSeconds }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Sandbox execution failed");
  }
  return res.json();
}

export async function fetchEvidence(issueId: string): Promise<EvidenceItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/evidence`, {
    cache: "no-store",
  });
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export interface AgentTaskItem {
  id: string;
  issue_id: string;
  agent_role: string;
  status: string;
  task_input: Record<string, any>;
  task_output?: Record<string, any> | null;
  error_message?: string | null;
  timeout_seconds: number;
  retry_count: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
}

export interface InvestigationLeadReport {
  issue_id: string;
  outcome: string;
  summary: string;
  structured_report: {
    title: string;
    summary: string;
    expected_behaviour: string;
    actual_behaviour: string;
    missing_context: boolean;
    clarification_questions: string[];
    tags: string[];
  };
  code_investigation?: {
    relevant_files: string[];
    suspected_symbols: string[];
    citations: Array<{
      file_path: string;
      line_start?: number;
      line_end?: number;
      snippet?: string;
      relevance_note: string;
    }>;
    execution_path_summary: string;
    suspected_root_cause_hypothesis?: string;
    confidence_score: number;
  };
  reproduction_plan?: {
    reproduction_strategy: string;
    command_to_run: string;
    expected_failure_pattern: string;
    prerequisites_or_dependencies: string[];
    can_run_offline: boolean;
  };
  sandbox_execution_performed: boolean;
  evidence_validation?: {
    outcome: string;
    is_valid_reproduction: boolean;
    evidence_summary: string;
    actual_failure_matches_expected: boolean;
    distinction_explanation: string;
    missing_context_or_dependencies: string[];
  };
  triage_recommendation: string;
  evidence_ids: string[];
  next_step: string;
}

export async function runInvestigation(issueId: string): Promise<InvestigationLeadReport> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/investigate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Investigation workflow failed");
  }
  return res.json();
}

export async function fetchAgentTasks(issueId: string): Promise<AgentTaskItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/tasks`, {
    cache: "no-store",
  });
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export interface SolutionItem {
  id: string;
  proposal_id: string;
  title: string;
  strategy_type?: string;
  description: string;
  rationale: string;
  affected_files: string[];
  complexity_score: number;
  rank?: number;
  is_recommended?: boolean;
  critique?: Record<string, any>;
  evaluation?: Record<string, any>;
  scope_assessment?: Record<string, any>;
}

export async function triggerResolution(issueId: string, developerToken = "dev_secret_token"): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/resolution`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Developer-Token": developerToken,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Resolution debate failed");
  }
  return res.json();
}

export async function fetchSolutions(issueId: string): Promise<SolutionItem[]> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/solutions`, {
    cache: "no-store",
  });
  if (!res.ok) {
    return [];
  }
  return res.json();
}

export async function approveFixStrategy(
  issueId: string,
  solutionId?: string,
  customStrategy?: string,
  developerToken = "dev_secret_token"
): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/approve-fix`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Developer-Token": developerToken,
    },
    body: JSON.stringify({
      decision: solutionId ? "FIX_APPROVED" : "CUSTOM_STRATEGY_APPROVED",
      solution_id: solutionId,
      custom_strategy: customStrategy,
      notes: "Approved via Developer Dashboard",
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Fix approval failed");
  }
  return res.json();
}

export async function triggerImplementation(issueId: string, developerToken = "dev_secret_token"): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/implement`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Developer-Token": developerToken,
    },
    body: JSON.stringify({ developer_token: developerToken, push_to_remote: false }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Implementation failed");
  }
  return res.json();
}

export async function triggerVerification(issueId: string, developerToken = "dev_secret_token"): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Developer-Token": developerToken,
    },
    body: JSON.stringify({ run_test_suite: true }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Verification failed");
  }
  return res.json();
}

export async function fetchImplementation(issueId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/v1/issues/${encodeURIComponent(issueId)}/implementation`, {
    cache: "no-store",
  });
  if (!res.ok) {
    return { has_implementation: false };
  }
  return res.json();
}


