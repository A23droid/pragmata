"use client";

import { useEffect, useState } from "react";
import {
  fetchHealth,
  fetchIssues,
  fetchIssueDetail,
  fetchSwitchStatus,
  createIssue,
  triageIssue,
  transitionIssue,
  inspectRepository,
  runSandbox,
  fetchEvidence,
  runInvestigation,
  fetchAgentTasks,
  triggerResolution,
  fetchSolutions,
  approveFixStrategy,
  triggerImplementation,
  triggerVerification,
  fetchImplementation,
  SolutionItem,
  HealthStatus,
  SwitchStatus,
  Issue,
  IssueDetail,
  RepoInspectionResult,
  SandboxExecutionResult,
  EvidenceItem,
  InvestigationLeadReport,
  AgentTaskItem,
} from "@/lib/api";
import {
  AlertCircle,
  ArrowRight,
  Bot,
  Bug,
  CheckCircle2,
  Clock,
  Code2,
  Database,
  ExternalLink,
  FileText,
  Filter,
  FolderGit2,
  GitBranch,
  HelpCircle,
  History,
  Layers,
  MessagesSquare,
  Play,
  PlusCircle,
  Radio,
  RefreshCw,
  Search,
  Server,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  User,
  X,
  Zap,
} from "lucide-react";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [switchStatus, setSwitchStatus] = useState<SwitchStatus | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);
  const [selectedIssueDetail, setSelectedIssueDetail] = useState<IssueDetail | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // New Issue Modal
  const [showNewModal, setShowNewModal] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newExpected, setNewExpected] = useState("");
  const [newSteps, setNewSteps] = useState("");
  const [newBrowser, setNewBrowser] = useState("");

  // Triage state
  const [triageActor, setTriageActor] = useState("developer@pragmata.internal");
  const [triageNotes, setTriageNotes] = useState("");

  // Phase 5 & 6 Investigation & Sandbox State
  const [inspection, setInspection] = useState<RepoInspectionResult | null>(null);
  const [sandboxResult, setSandboxResult] = useState<SandboxExecutionResult | null>(null);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [sandboxCommand, setSandboxCommand] = useState("pytest || python3 -m unittest");
  const [searchQuery, setSearchQuery] = useState("");
  const [isInspecting, setIsInspecting] = useState(false);
  const [isRunningSandbox, setIsRunningSandbox] = useState(false);

  // Phase 6 Full Multi-Agent Investigation State
  const [investigationReport, setInvestigationReport] = useState<InvestigationLeadReport | null>(null);
  const [agentTasks, setAgentTasks] = useState<AgentTaskItem[]>([]);
  const [isInvestigating, setIsInvestigating] = useState(false);

  // Phase 7 & 8 Resolution & Verification State
  const [solutions, setSolutions] = useState<SolutionItem[]>([]);
  const [isResolving, setIsResolving] = useState(false);
  const [selectedSolutionId, setSelectedSolutionId] = useState<string | null>(null);
  const [customStrategyText, setCustomStrategyText] = useState("");
  const [isApprovingFix, setIsApprovingFix] = useState(false);
  const [isImplementing, setIsImplementing] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [implementationInfo, setImplementationInfo] = useState<any>(null);
  const [verificationResult, setVerificationResult] = useState<any>(null);

  const refreshAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, sw, iss] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchSwitchStatus().catch(() => null),
        fetchIssues(statusFilter || undefined).catch(() => []),
      ]);
      setHealth(h);
      setSwitchStatus(sw);
      setIssues(iss);
      if (selectedIssueId) {
        await loadDetail(selectedIssueId);
      }
    } catch (err: any) {
      setError(err.message || "Failed to fetch dashboard data");
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (id: string) => {
    setDetailLoading(true);
    try {
      const [detail, ev, tasks, sols, impl] = await Promise.all([
        fetchIssueDetail(id),
        fetchEvidence(id).catch(() => []),
        fetchAgentTasks(id).catch(() => []),
        fetchSolutions(id).catch(() => []),
        fetchImplementation(id).catch(() => null),
      ]);
      setSelectedIssueDetail(detail);
      setSelectedIssueId(id);
      setEvidenceList(ev);
      setAgentTasks(tasks);
      setSolutions(sols);
      setImplementationInfo(impl);
    } catch (err: any) {
      setError(err.message || "Failed to load issue detail");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleRunResolution = async () => {
    if (!selectedIssueId) return;
    setIsResolving(true);
    setError(null);
    try {
      await triggerResolution(selectedIssueId);
      await refreshAll();
      await loadDetail(selectedIssueId);
    } catch (err: any) {
      setError(err.message || "Resolution debate failed");
    } finally {
      setIsResolving(false);
    }
  };

  const handleApproveFix = async () => {
    if (!selectedIssueId) return;
    setIsApprovingFix(true);
    setError(null);
    try {
      await approveFixStrategy(selectedIssueId, selectedSolutionId || undefined, customStrategyText || undefined);
      setSelectedSolutionId(null);
      setCustomStrategyText("");
      await refreshAll();
      await loadDetail(selectedIssueId);
    } catch (err: any) {
      setError(err.message || "Fix approval failed");
    } finally {
      setIsApprovingFix(false);
    }
  };

  const handleRunImplementation = async () => {
    if (!selectedIssueId) return;
    setIsImplementing(true);
    setError(null);
    try {
      await triggerImplementation(selectedIssueId);
      await refreshAll();
      await loadDetail(selectedIssueId);
    } catch (err: any) {
      setError(err.message || "Implementation failed");
    } finally {
      setIsImplementing(false);
    }
  };

  const handleRunVerification = async () => {
    if (!selectedIssueId) return;
    setIsVerifying(true);
    setError(null);
    try {
      const res = await triggerVerification(selectedIssueId);
      setVerificationResult(res);
      await refreshAll();
      await loadDetail(selectedIssueId);
    } catch (err: any) {
      setError(err.message || "Verification failed");
    } finally {
      setIsVerifying(false);
    }
  };

  const handleRunInvestigation = async () => {
    if (!selectedIssueId) return;
    setIsInvestigating(true);
    setError(null);
    try {
      const report = await runInvestigation(selectedIssueId);
      setInvestigationReport(report);
      await refreshAll();
      await loadDetail(selectedIssueId);
    } catch (err: any) {
      setError(err.message || "Investigation workflow failed");
    } finally {
      setIsInvestigating(false);
    }
  };

  const handleInspect = async () => {
    if (!selectedIssueId) return;
    setIsInspecting(true);
    setError(null);
    try {
      const res = await inspectRepository(selectedIssueId, searchQuery || undefined);
      setInspection(res);
      if (res.test_commands && res.test_commands.length > 0) {
        setSandboxCommand(res.test_commands[0]);
      }
    } catch (err: any) {
      setError(err.message || "Repository inspection failed");
    } finally {
      setIsInspecting(false);
    }
  };

  const handleRunSandbox = async () => {
    if (!selectedIssueId || !sandboxCommand.trim()) return;
    setIsRunningSandbox(true);
    setError(null);
    try {
      const res = await runSandbox(selectedIssueId, sandboxCommand.trim());
      setSandboxResult(res);
      const updatedEv = await fetchEvidence(selectedIssueId);
      setEvidenceList(updatedEv);
    } catch (err: any) {
      setError(err.message || "Sandbox execution failed");
    } finally {
      setIsRunningSandbox(false);
    }
  };

  useEffect(() => {
    refreshAll();
  }, [statusFilter]);

  const handleCreateIssue = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newDescription.trim()) return;

    setActionLoading(true);
    setError(null);
    try {
      const created = await createIssue({
        title: newTitle.trim(),
        description: newDescription.trim(),
        expected_behavior: newExpected.trim() || undefined,
        steps_attempted: newSteps.trim() || undefined,
        reporter_environment: newBrowser ? { browser: newBrowser } : undefined,
      });
      setShowNewModal(false);
      setNewTitle("");
      setNewDescription("");
      setNewExpected("");
      setNewSteps("");
      setNewBrowser("");
      await refreshAll();
      await loadDetail(created.id);
    } catch (err: any) {
      setError(err.message || "Failed to submit issue");
    } finally {
      setActionLoading(false);
    }
  };

  const handleTriage = async (
    decision: "ACCEPTED" | "REJECTED" | "REQUEST_INFORMATION" | "DEFERRED"
  ) => {
    if (!selectedIssueId || !triageActor.trim()) return;
    setActionLoading(true);
    setError(null);
    try {
      await triageIssue(selectedIssueId, decision, triageActor.trim(), triageNotes.trim());
      setTriageNotes("");
      await refreshAll();
      await loadDetail(selectedIssueId);
    } catch (err: any) {
      setError(err.message || "Triage failed");
    } finally {
      setActionLoading(false);
    }
  };

  const handleTransition = async (targetStatus: string, reason: string) => {
    if (!selectedIssueId) return;
    setActionLoading(true);
    setError(null);
    try {
      await transitionIssue(selectedIssueId, targetStatus, "orchestrator", reason);
      await refreshAll();
      await loadDetail(selectedIssueId);
    } catch (err: any) {
      setError(err.message || "Transition failed");
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "RECEIVED":
        return "bg-slate-800 text-slate-300 border-slate-700";
      case "INVESTIGATING":
        return "bg-blue-950/60 text-blue-400 border-blue-800/60";
      case "REPRODUCING":
        return "bg-purple-950/60 text-purple-300 border-purple-800/60";
      case "REPRODUCED":
        return "bg-amber-950/60 text-amber-300 border-amber-800/60";
      case "AWAITING_DEVELOPER_TRIAGE":
        return "bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse";
      case "ACCEPTED":
        return "bg-emerald-950/60 text-emerald-300 border-emerald-800/60";
      case "ROOT_CAUSE_ANALYSIS":
      case "FIX_STRATEGY_DISCUSSION":
        return "bg-indigo-950/60 text-indigo-300 border-indigo-800/60";
      case "AWAITING_FIX_APPROVAL":
        return "bg-cyan-500/20 text-cyan-300 border-cyan-500/40 animate-pulse";
      case "IMPLEMENTING":
        return "bg-violet-950/60 text-violet-300 border-violet-800/60";
      case "VERIFYING":
        return "bg-sky-950/60 text-sky-300 border-sky-800/60";
      case "RESOLVED":
        return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
      case "REJECTED":
        return "bg-rose-950/60 text-rose-400 border-rose-800/60";
      case "DEFERRED":
        return "bg-slate-900 text-slate-400 border-slate-800";
      default:
        return "bg-slate-800 text-slate-300 border-slate-700";
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100 font-sans">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur px-6 py-3.5 flex items-center justify-between sticky top-0 z-20">
        <div className="flex items-center space-x-3">
          <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30">
            P
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
              PRAGMATA
              <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-mono">
                Phase 6 &bull; Bug Investigation &amp; Reproduction
              </span>
            </h1>
            <p className="text-[11px] text-slate-400">
              Deterministic Workflow Engine &bull; Switch Agent Collaboration
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Switch Status Pill */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800/80 border border-slate-700/60 text-[11px] text-slate-300 font-mono">
            {switchStatus?.connected ? (
              <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400" />
            ) : (
              <span className="h-2 w-2 rounded-full bg-amber-400" />
            )}
            <span>Switch: {switchStatus?.connected ? "Live" : "Standby (Local Adapter)"}</span>
          </div>

          {/* Backend Health Pill */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800/80 border border-slate-700/60 text-[11px] text-slate-300 font-mono">
            {health?.database === "connected" ? (
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
            ) : (
              <span className="h-2 w-2 rounded-full bg-amber-400" />
            )}
            <span>DB: {health?.database || "Connecting..."}</span>
          </div>

          <button
            onClick={refreshAll}
            disabled={loading}
            className="p-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors border border-slate-700"
            title="Refresh issues"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>

          <a
            href="/demo"
            className="flex items-center space-x-1.5 text-xs font-semibold px-3 py-1.5 rounded-md bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white shadow-md shadow-indigo-600/30 transition-all border border-purple-400/30"
          >
            <span>🎬</span>
            <span>Demo Mode (Switch & Slack)</span>
          </a>

          <button
            onClick={() => setShowNewModal(true)}
            className="flex items-center space-x-1.5 text-xs font-semibold px-3.5 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/30 transition-all"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span>Report Bug</span>
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
        {error && (
          <div className="p-3.5 rounded-lg bg-rose-950/60 border border-rose-800/80 text-rose-300 text-xs flex items-center justify-between">
            <span className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              {error}
            </span>
            <button onClick={() => setError(null)} className="text-rose-400 hover:text-white">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Filter Bar */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
            <span className="text-slate-400 font-medium mr-1 flex items-center gap-1">
              <Filter className="w-3 h-3 text-slate-500" /> Filter:
            </span>
            {[
              { label: "All", value: "" },
              { label: "Received", value: "RECEIVED" },
              { label: "Investigating", value: "INVESTIGATING" },
              { label: "Reproducing", value: "REPRODUCING" },
              { label: "Awaiting Triage", value: "AWAITING_DEVELOPER_TRIAGE" },
              { label: "Accepted", value: "ACCEPTED" },
              { label: "RCA", value: "ROOT_CAUSE_ANALYSIS" },
              { label: "Fix Discussion", value: "FIX_STRATEGY_DISCUSSION" },
              { label: "Resolved", value: "RESOLVED" },
            ].map((f) => (
              <button
                key={f.value}
                onClick={() => setStatusFilter(f.value)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                  statusFilter === f.value
                    ? "bg-indigo-600 text-white font-semibold"
                    : "bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="text-xs text-slate-400">
            Total Issues: <span className="font-mono font-bold text-slate-200">{issues.length}</span>
          </div>
        </div>

        {/* Split Grid: Issue List + Detail Pane */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Issue List (Left column) */}
          <div className="lg:col-span-5 space-y-3">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-400 uppercase tracking-wider px-1">
              <span>Submitted Issues</span>
              <span className="font-mono text-[11px] text-slate-500">Live Intake</span>
            </div>

            {loading && issues.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-xs">Loading issues...</div>
            ) : issues.length === 0 ? (
              <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-8 text-center space-y-2">
                <Bug className="w-8 h-8 mx-auto text-slate-600" />
                <p className="text-xs text-slate-400">No issues reported yet.</p>
                <button
                  onClick={() => setShowNewModal(true)}
                  className="text-xs text-indigo-400 hover:underline font-medium"
                >
                  Submit the first bug report &rarr;
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {issues.map((issue) => {
                  const isSelected = selectedIssueId === issue.id;
                  return (
                    <div
                      key={issue.id}
                      onClick={() => loadDetail(issue.id)}
                      className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 ${
                        isSelected
                          ? "bg-slate-900 border-indigo-500/80 shadow-lg shadow-indigo-950/40"
                          : "bg-slate-900/50 border-slate-800/80 hover:bg-slate-900 hover:border-slate-700"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs font-bold text-indigo-400">
                          {issue.id}
                        </span>
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-full font-mono border ${getStatusColor(
                            issue.status
                          )}`}
                        >
                          {issue.status}
                        </span>
                      </div>
                      <h3 className="text-xs font-semibold text-slate-200 line-clamp-1">
                        {issue.title}
                      </h3>
                      <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                        {issue.description}
                      </p>
                      <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800/50">
                        <span className="flex items-center gap-1 font-mono">
                          <Clock className="w-3 h-3" />
                          {new Date(issue.created_at).toLocaleDateString()}
                        </span>
                        {issue.reporter_environment && (
                          <span className="text-slate-400 font-mono">
                            {issue.reporter_environment.browser || "Environment attached"}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Issue Detail & Triage Console (Right column) */}
          <div className="lg:col-span-7 bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 min-h-[500px]">
            {detailLoading ? (
              <div className="flex items-center justify-center h-80 text-xs text-slate-400">
                Loading issue details...
              </div>
            ) : selectedIssueDetail ? (
              <div className="space-y-6">
                {/* Header */}
                <div className="border-b border-slate-800/80 pb-4">
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-indigo-400">
                        {selectedIssueDetail.id}
                      </span>
                      <span
                        className={`text-xs px-2.5 py-0.5 rounded-full font-mono border ${getStatusColor(
                          selectedIssueDetail.status
                        )}`}
                      >
                        {selectedIssueDetail.status}
                      </span>
                    </div>
                    <span className="text-xs text-slate-500 font-mono">
                      {new Date(selectedIssueDetail.created_at).toLocaleString()}
                    </span>
                  </div>
                  <h2 className="text-base font-bold text-slate-100">
                    {selectedIssueDetail.title}
                  </h2>
                </div>

                {/* Reporter Description */}
                <div className="space-y-3">
                  <div className="rounded-lg bg-slate-950/60 border border-slate-800/70 p-3.5 space-y-1.5">
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5 text-indigo-400" />
                      Reported Issue
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                      {selectedIssueDetail.description}
                    </p>
                  </div>

                  {selectedIssueDetail.expected_behavior && (
                    <div className="rounded-lg bg-slate-950/60 border border-slate-800/70 p-3.5 space-y-1">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                        Expected Behavior
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">
                        {selectedIssueDetail.expected_behavior}
                      </p>
                    </div>
                  )}

                  {selectedIssueDetail.steps_attempted && (
                    <div className="rounded-lg bg-slate-950/60 border border-slate-800/70 p-3.5 space-y-1">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                        Steps Attempted
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed">
                        {selectedIssueDetail.steps_attempted}
                      </p>
                    </div>
                  )}
                </div>

                {/* Switch Collaboration Rooms (Phase 3 Native Integration) */}
                <div className="rounded-xl border border-indigo-900/50 bg-indigo-950/15 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-semibold text-indigo-300">
                      <MessagesSquare className="w-4 h-4 text-indigo-400" />
                      Switch Agent Collaboration Rooms (Phase 3)
                    </div>
                    <span className="text-[10px] text-indigo-400 font-mono">
                      Persistent Context
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    Dedicated rooms associated with this issue for real-time agent handoffs and human collaboration.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1">
                    {selectedIssueDetail.conversations && selectedIssueDetail.conversations.length > 0 ? (
                      selectedIssueDetail.conversations.map((c) => (
                        <div
                          key={c.id}
                          className="rounded-lg bg-slate-950/80 border border-slate-800 p-2.5 space-y-1"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-mono font-bold text-indigo-400">
                              {c.channel_type}
                            </span>
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                          </div>
                          <div className="font-mono text-[11px] text-slate-300 truncate" title={c.room_id}>
                            {c.room_id}
                          </div>
                          <div className="text-[10px] text-slate-500">
                            Role: {c.channel_type === "INVESTIGATION" ? "Intake & Repro" : c.channel_type === "RESOLUTION" ? "Architect & Critic" : "Implementer & Verifier"}
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="col-span-3 text-xs text-slate-500 italic p-2 bg-slate-950/40 rounded border border-slate-800/60">
                        Auto-provisioning Switch rooms for this issue...
                      </div>
                    )}
                  </div>
                </div>

                {/* PHASE 6: Multi-Agent Bug Investigation & Reproduction Workflow */}
                <div className="rounded-xl border border-amber-500/40 bg-amber-950/15 p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-semibold text-amber-300">
                      <Bot className="w-4 h-4 text-amber-400" />
                      Multi-Agent Bug Investigation &amp; Reproduction (Phase 6)
                    </div>
                    <span className="text-[10px] text-amber-400 font-mono px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20">
                      Investigation Lead Coordinator
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Coordinates <strong>Intake Agent</strong>, <strong>Investigator</strong>, <strong>Reproducer</strong>, and <strong>Evidence Validator</strong>. Inspects repository files, executes minimal reproduction strictly inside the Docker sandbox, validates facts versus hypotheses, records real evidence to PostgreSQL, and posts updates to Switch.
                  </p>

                  <div className="flex flex-wrap items-center gap-3 pt-1">
                    <button
                      onClick={handleRunInvestigation}
                      disabled={isInvestigating || actionLoading}
                      className="px-4 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-bold shadow-lg shadow-amber-600/30 transition-all disabled:opacity-50 flex items-center gap-2"
                    >
                      <Zap className={`w-4 h-4 ${isInvestigating ? "animate-spin" : ""}`} />
                      <span>{isInvestigating ? "Investigating & Running Reproduction..." : "Run AI Bug Investigation & Reproduction"}</span>
                    </button>

                    {agentTasks.length > 0 && (
                      <span className="text-[11px] text-slate-400 font-mono">
                        {agentTasks.length} agent tasks recorded in PostgreSQL
                      </span>
                    )}
                  </div>

                  {isInvestigating && (
                    <div className="p-3.5 rounded-lg bg-slate-950 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2.5 animate-pulse">
                      <RefreshCw className="w-4 h-4 animate-spin text-amber-400" />
                      <span>Investigation Lead is delegating tasks to Intake Agent, Investigator, Reproducer, and Evidence Validator... Running reproduction in isolated Docker sandbox.</span>
                    </div>
                  )}

                  {/* Active Investigation Lead Report */}
                  {investigationReport && (
                    <div className="rounded-xl bg-slate-950 border border-slate-800 p-4 space-y-4 text-xs">
                      {/* Outcome Header Banner */}
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] text-slate-400 uppercase font-mono">Verdict:</span>
                          <span
                            className={`px-3 py-1 rounded-full font-mono font-bold text-xs border ${
                              investigationReport.outcome === "REPRODUCED"
                                ? "bg-amber-500/20 text-amber-300 border-amber-500/50"
                                : investigationReport.outcome === "NOT_REPRODUCED"
                                ? "bg-slate-800 text-slate-300 border-slate-700"
                                : investigationReport.outcome === "NEEDS_INFORMATION"
                                ? "bg-sky-500/20 text-sky-300 border-sky-500/50"
                                : investigationReport.outcome === "ENVIRONMENT_DEPENDENT"
                                ? "bg-purple-500/20 text-purple-300 border-purple-500/50"
                                : "bg-rose-500/20 text-rose-300 border-rose-500/50"
                            }`}
                          >
                            {investigationReport.outcome}
                          </span>
                        </div>
                        <div className="text-[11px] font-mono text-slate-400">
                          Next Step: <span className="text-indigo-400 font-semibold">{investigationReport.next_step}</span>
                        </div>
                      </div>

                      <div className="p-2.5 rounded bg-slate-900 border border-slate-800 text-slate-300 leading-relaxed">
                        <div className="text-[10px] uppercase font-mono text-slate-500 mb-1">Investigation Summary:</div>
                        {investigationReport.summary}
                      </div>

                      {/* Structured Intake Report */}
                      {investigationReport.structured_report && (
                        <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-bold text-indigo-300 flex items-center gap-1.5">
                              <FileText className="w-3.5 h-3.5 text-indigo-400" /> Intake Agent Analysis
                            </span>
                            {investigationReport.structured_report.tags.length > 0 && (
                              <div className="flex gap-1">
                                {investigationReport.structured_report.tags.map((t) => (
                                  <span key={t} className="text-[10px] px-1.5 py-0.2 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/50 font-mono">
                                    {t}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                            <div>
                              <span className="text-slate-500">Expected:</span> <span className="text-slate-300">{investigationReport.structured_report.expected_behaviour}</span>
                            </div>
                            <div>
                              <span className="text-slate-500">Actual:</span> <span className="text-slate-300">{investigationReport.structured_report.actual_behaviour}</span>
                            </div>
                          </div>
                          {investigationReport.structured_report.missing_context && (
                            <div className="p-2 rounded bg-amber-950/30 border border-amber-800/60 text-amber-300 space-y-1">
                              <div className="font-semibold flex items-center gap-1 text-[10px] uppercase">
                                <HelpCircle className="w-3 h-3 text-amber-400" /> Missing Information Requested:
                              </div>
                              <ul className="list-disc pl-4 space-y-0.5 text-[11px]">
                                {investigationReport.structured_report.clarification_questions.map((q, idx) => (
                                  <li key={idx}>{q}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Code Citations (Investigator) */}
                      {investigationReport.code_investigation && (
                        <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-2.5">
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-bold text-sky-300 flex items-center gap-1.5">
                              <Code2 className="w-3.5 h-3.5 text-sky-400" /> Investigator Findings &amp; Code Citations
                            </span>
                            <span className="text-[10px] text-slate-400 font-mono">
                              Confidence: {Math.round(investigationReport.code_investigation.confidence_score * 100)}%
                            </span>
                          </div>

                          <div className="text-[11px] text-slate-400">
                            Relevant Files: <span className="font-mono text-slate-200">{investigationReport.code_investigation.relevant_files.join(", ")}</span>
                          </div>

                          {investigationReport.code_investigation.citations && investigationReport.code_investigation.citations.length > 0 && (
                            <div className="space-y-1.5 pt-1">
                              <div className="text-[10px] uppercase font-mono text-slate-500">Evidence Citations:</div>
                              {investigationReport.code_investigation.citations.map((c, idx) => (
                                <div key={idx} className="p-2 rounded bg-slate-950 border border-slate-800 space-y-1 font-mono text-[11px]">
                                  <div className="flex items-center justify-between text-sky-400">
                                    <span>{c.file_path}{c.line_start ? `:${c.line_start}` : ""}{c.line_end ? `-${c.line_end}` : ""}</span>
                                    <span className="text-[10px] text-slate-500 font-sans">Evidence Citation</span>
                                  </div>
                                  {c.snippet && (
                                    <pre className="p-1.5 rounded bg-slate-900 text-slate-300 text-[10px] overflow-x-auto">
                                      {c.snippet}
                                    </pre>
                                  )}
                                  <div className="text-slate-400 font-sans text-[11px]">
                                    {c.relevance_note}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}

                          {investigationReport.code_investigation.suspected_root_cause_hypothesis && (
                            <div className="p-2 rounded bg-indigo-950/40 border border-indigo-800/60 text-indigo-300">
                              <span className="font-semibold text-[10px] uppercase block mb-0.5 text-indigo-400">
                                Suspected Root Cause Hypothesis [Separated from Verified Reproduction]:
                              </span>
                              <span className="text-[11px] text-slate-200">{investigationReport.code_investigation.suspected_root_cause_hypothesis}</span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Reproduction Plan & Execution Result */}
                      {investigationReport.reproduction_plan && (
                        <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-bold text-purple-300 flex items-center gap-1.5">
                              <Terminal className="w-3.5 h-3.5 text-purple-400" /> Reproducer Sandbox Plan
                            </span>
                            <span className="text-[10px] text-purple-400 font-mono">
                              Docker Read-Only Isolation
                            </span>
                          </div>
                          <div className="space-y-1 font-mono text-[11px]">
                            <div className="text-slate-400">
                              Command: <code className="text-purple-300 px-1 py-0.5 rounded bg-slate-950 border border-slate-800">{investigationReport.reproduction_plan.command_to_run}</code>
                            </div>
                            <div className="text-slate-400">
                              Expected Pattern: <span className="text-amber-300">{investigationReport.reproduction_plan.expected_failure_pattern}</span>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Evidence Validation Verdict */}
                      {investigationReport.evidence_validation && (
                        <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 space-y-1.5">
                          <div className="flex items-center justify-between">
                            <span className="text-[11px] font-bold text-emerald-300 flex items-center gap-1.5">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Evidence Validator Verdict
                            </span>
                            <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${investigationReport.evidence_validation.is_valid_reproduction ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-800 text-slate-400"}`}>
                              {investigationReport.evidence_validation.is_valid_reproduction ? "Reproduction Confirmed" : "Not Confirmed"}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-300 leading-relaxed">
                            {investigationReport.evidence_validation.evidence_summary}
                          </p>
                          <div className="text-[10px] text-slate-400 italic border-t border-slate-800/60 pt-1">
                            {investigationReport.evidence_validation.distinction_explanation}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Agent Task Audit Cards */}
                  {agentTasks.length > 0 && (
                    <div className="space-y-2 pt-2 border-t border-slate-800/80">
                      <div className="text-[10px] uppercase font-mono text-slate-400 flex items-center gap-1">
                        <Layers className="w-3 h-3 text-amber-400" /> Agent Tasks Execution Trail ({agentTasks.length})
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {agentTasks.map((t) => (
                          <div key={t.id} className="p-2 rounded bg-slate-950/80 border border-slate-800 text-[11px] space-y-1">
                            <div className="flex items-center justify-between">
                              <span className="font-mono font-bold text-amber-400">{t.agent_role}</span>
                              <span className={`text-[9px] px-1.5 py-0.2 rounded font-mono ${t.status === "COMPLETED" ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60" : "bg-slate-800 text-slate-400"}`}>
                                {t.status}
                              </span>
                            </div>
                            <div className="text-[10px] text-slate-500 font-mono">
                              Retries: {t.retry_count}/{t.max_retries} &bull; Timeout: {t.timeout_seconds}s
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* PHASE 5: Repository Connection & Base Commit Inspection */}
                <div className="rounded-xl border border-sky-900/50 bg-sky-950/15 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-semibold text-sky-300">
                      <FolderGit2 className="w-4 h-4 text-sky-400" />
                      Repository Connection & Workspace Inspection (Phase 5)
                    </div>
                    <span className="text-[10px] text-sky-400 font-mono">
                      Safe Workspace Isolation
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    Connects to the repository, clones into an isolated temporary workspace, records the exact base commit SHA, and inspects files, frameworks, and test runners.
                  </p>

                  <div className="flex flex-col sm:flex-row gap-2 pt-1">
                    <div className="flex-1 flex gap-2">
                      <input
                        type="text"
                        placeholder="Search code / symbols (e.g. discount, calculate, checkout)"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="flex-1 px-2.5 py-1.5 rounded bg-slate-950 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                      />
                      <button
                        onClick={handleInspect}
                        disabled={isInspecting}
                        className="px-3.5 py-1.5 rounded bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow transition-all disabled:opacity-50 flex items-center gap-1.5 shrink-0"
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${isInspecting ? "animate-spin" : ""}`} />
                        <span>{isInspecting ? "Inspecting..." : "Inspect Repository"}</span>
                      </button>
                    </div>
                  </div>

                  {inspection && (
                    <div className="space-y-3 pt-2 text-xs border-t border-slate-800">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <div className="p-2.5 rounded bg-slate-950/80 border border-slate-800 space-y-1">
                          <div className="text-[10px] uppercase font-mono text-slate-500 flex items-center gap-1">
                            <GitBranch className="w-3 h-3 text-sky-400" /> Base Commit SHA
                          </div>
                          <div className="font-mono text-xs text-sky-300 break-all">
                            {inspection.commit_sha}
                          </div>
                          <div className="text-[10px] text-slate-400">
                            Branch: <span className="font-mono text-slate-300">{inspection.branch}</span> &bull; {inspection.total_files} files
                          </div>
                        </div>

                        <div className="p-2.5 rounded bg-slate-950/80 border border-slate-800 space-y-1">
                          <div className="text-[10px] uppercase font-mono text-slate-500 flex items-center gap-1">
                            <Code2 className="w-3 h-3 text-sky-400" /> Tech & Test Runners
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {inspection.detected_languages.map((l) => (
                              <span key={l} className="text-[10px] px-1.5 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800/60 font-mono">
                                {l}
                              </span>
                            ))}
                            {inspection.detected_frameworks.map((f) => (
                              <span key={f} className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/60 font-mono">
                                {f}
                              </span>
                            ))}
                          </div>
                          {inspection.test_commands.length > 0 && (
                            <div className="text-[10px] text-slate-400 flex items-center gap-1 pt-1">
                              <span>Test Commands:</span>
                              {inspection.test_commands.map((cmd) => (
                                <button
                                  key={cmd}
                                  onClick={() => setSandboxCommand(cmd)}
                                  className="font-mono text-emerald-400 hover:underline"
                                  title="Click to copy to sandbox command"
                                >
                                  {cmd}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>

                      {inspection.search_results.length > 0 && (
                        <div className="p-2.5 rounded bg-slate-950/80 border border-slate-800 space-y-1.5">
                          <div className="text-[10px] uppercase font-mono text-slate-500 flex items-center gap-1">
                            <Search className="w-3 h-3 text-sky-400" /> Search Matches ({inspection.search_results.length})
                          </div>
                          <div className="space-y-1 max-h-36 overflow-y-auto font-mono text-[11px]">
                            {inspection.search_results.map((sm, idx) => (
                              <div key={idx} className="p-1 rounded bg-slate-900 border border-slate-800 flex justify-between gap-2">
                                <span className="text-sky-300 truncate">{sm.file_path}:{sm.line_number}</span>
                                <span className="text-slate-400 truncate">{sm.line_content}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* PHASE 5: Controlled Docker Sandbox Execution */}
                <div className="rounded-xl border border-purple-900/50 bg-purple-950/15 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-semibold text-purple-300">
                      <Terminal className="w-4 h-4 text-purple-400" />
                      Isolated Docker Sandbox Execution (Phase 5)
                    </div>
                    <span className="text-[10px] text-purple-400 font-mono">
                      Restricted Mounts & Offline
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    Executes controlled reproduction attempts inside a hardened container: resource-capped, non-root, zero host secrets, and disconnected from network.
                  </p>

                  <div className="flex flex-col sm:flex-row gap-2">
                    <div className="flex-1 flex gap-2">
                      <input
                        type="text"
                        value={sandboxCommand}
                        onChange={(e) => setSandboxCommand(e.target.value)}
                        placeholder="Command to run (e.g. pytest, python script.py)"
                        className="flex-1 px-2.5 py-1.5 rounded bg-slate-950 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:border-purple-500 font-mono"
                      />
                      <button
                        onClick={handleRunSandbox}
                        disabled={isRunningSandbox || !sandboxCommand.trim()}
                        className="px-3.5 py-1.5 rounded bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow transition-all disabled:opacity-50 flex items-center gap-1.5 shrink-0"
                      >
                        <Play className={`w-3.5 h-3.5 ${isRunningSandbox ? "animate-pulse" : ""}`} />
                        <span>{isRunningSandbox ? "Executing..." : "Run in Sandbox"}</span>
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 text-[10px] text-slate-500 font-mono">
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                      Network: Offline (--network none)
                    </span>
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                      CPUs: 1.0 &bull; RAM: 512m
                    </span>
                    <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800">
                      User: 1000:1000
                    </span>
                  </div>

                  {sandboxResult && (
                    <div className="rounded-lg bg-slate-950 border border-slate-800 p-3 space-y-2 text-xs font-mono">
                      <div className="flex items-center justify-between text-[11px] border-b border-slate-800/80 pb-1.5">
                        <span className="text-slate-400">
                          Exit Code: <span className={sandboxResult.exit_code === 0 ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>{sandboxResult.exit_code}</span>
                        </span>
                        <span className="text-slate-500">
                          {sandboxResult.duration_seconds}s {sandboxResult.timed_out ? "(TIMED OUT)" : ""}
                        </span>
                      </div>
                      {sandboxResult.stdout && (
                        <div className="space-y-1">
                          <div className="text-[10px] text-slate-500 uppercase">Stdout:</div>
                          <pre className="text-[11px] text-slate-300 max-h-36 overflow-y-auto whitespace-pre-wrap bg-slate-900/60 p-2 rounded">
                            {sandboxResult.stdout}
                          </pre>
                        </div>
                      )}
                      {sandboxResult.stderr && (
                        <div className="space-y-1">
                          <div className="text-[10px] text-rose-400 uppercase">Stderr:</div>
                          <pre className="text-[11px] text-rose-300 max-h-36 overflow-y-auto whitespace-pre-wrap bg-slate-900/60 p-2 rounded">
                            {sandboxResult.stderr}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* PHASE 5: Recorded Real Evidence */}
                {evidenceList.length > 0 && (
                  <div className="rounded-xl border border-emerald-900/40 bg-emerald-950/10 p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-xs font-semibold text-emerald-300">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        Recorded Evidence ({evidenceList.length} items in PostgreSQL)
                      </div>
                      <span className="text-[10px] text-emerald-400 font-mono">
                        Tool-Generated Provenance
                      </span>
                    </div>

                    <div className="space-y-2">
                      {evidenceList.map((ev) => (
                        <div key={ev.id} className="p-2.5 rounded bg-slate-950/80 border border-slate-800 space-y-1 text-xs">
                          <div className="flex items-center justify-between text-[10px] font-mono">
                            <span className="text-emerald-400 font-semibold">{ev.evidence_type}</span>
                            <span className="text-slate-500">{new Date(ev.created_at).toLocaleTimeString()}</span>
                          </div>
                          <pre className="text-[11px] text-slate-300 max-h-24 overflow-y-auto whitespace-pre-wrap bg-slate-900/70 p-2 rounded font-mono">
                            {ev.content}
                          </pre>
                          <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 font-mono">
                            <span>Tool: {ev.tool_name || "system"}</span>
                            {ev.exit_code !== undefined && ev.exit_code !== null && (
                              <span>Exit: {ev.exit_code}</span>
                            )}
                            <span className="text-slate-400">Provenance: {ev.provenance}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* HUMAN GATE: Developer Triage Section */}
                <div className="rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-semibold text-indigo-300">
                      <ShieldAlert className="w-4 h-4 text-indigo-400" />
                      Human Authority Gate: Developer Triage
                    </div>
                    <span className="text-[10px] text-indigo-400 font-mono">
                      Gate Enforced Server-Side
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed">
                    AI agents investigate and provide reproduction evidence. Only an authenticated developer can accept the bug before root-cause analysis or solution design begins.
                  </p>

                  {/* Triage Gate Status Banner */}
                  {selectedIssueDetail.status === "AWAITING_DEVELOPER_TRIAGE" ? (
                    <div className="p-2.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0 text-amber-400" />
                      <span><strong>Action Required:</strong> Investigation complete. Review the evidence above and choose a developer triage decision below.</span>
                    </div>
                  ) : selectedIssueDetail.status === "ACCEPTED" ? (
                    <div className="p-2.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
                      <span><strong>Issue Accepted:</strong> Developer approved this bug. Ready for Phase 7 Fix Strategy Discussion &amp; Solution Architect.</span>
                    </div>
                  ) : selectedIssueDetail.status === "REJECTED" ? (
                    <div className="p-2.5 rounded-lg bg-rose-500/20 border border-rose-500/40 text-rose-300 text-xs flex items-center gap-2">
                      <X className="w-4 h-4 shrink-0 text-rose-400" />
                      <span><strong>Issue Rejected:</strong> Closed by developer.</span>
                    </div>
                  ) : selectedIssueDetail.status === "NEEDS_INFORMATION" ? (
                    <div className="p-2.5 rounded-lg bg-sky-500/20 border border-sky-500/40 text-sky-300 text-xs flex items-center gap-2">
                      <HelpCircle className="w-4 h-4 shrink-0 text-sky-400" />
                      <span><strong>Needs Information:</strong> Intake Agent flagged missing context. Waiting for reporter clarification.</span>
                    </div>
                  ) : (
                    <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 text-xs flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 shrink-0 text-indigo-400" />
                      <span><strong>Resolution Gate Locked:</strong> Resolution agents cannot be activated before bug investigation and developer acceptance.</span>
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs pt-1">
                    <div>
                      <label className="text-[10px] text-slate-400 uppercase font-mono">Developer ID</label>
                      <input
                        type="text"
                        value={triageActor}
                        onChange={(e) => setTriageActor(e.target.value)}
                        className="w-full mt-1 px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-400 uppercase font-mono">Decision Notes</label>
                      <input
                        type="text"
                        placeholder="e.g. Valid bug, reproduction confirmed."
                        value={triageNotes}
                        onChange={(e) => setTriageNotes(e.target.value)}
                        className="w-full mt-1 px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2 pt-2">
                    <button
                      onClick={() => handleTriage("ACCEPTED")}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow transition-all disabled:opacity-50"
                    >
                      Accept & Begin Resolution
                    </button>
                    <button
                      onClick={() => handleTriage("REJECTED")}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded bg-rose-700 hover:bg-rose-600 text-white text-xs font-semibold shadow transition-all disabled:opacity-50"
                    >
                      Reject Issue
                    </button>
                    <button
                      onClick={() => handleTriage("REQUEST_INFORMATION")}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold shadow transition-all disabled:opacity-50"
                    >
                      Request Info
                    </button>
                    <button
                      onClick={() => handleTriage("DEFERRED")}
                      disabled={actionLoading}
                      className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-white text-xs font-semibold shadow transition-all disabled:opacity-50"
                    >
                      Defer
                    </button>
                  </div>
                </div>

                {/* PHASE 7: Multi-Agent Fix Strategy Debate, Ranking & Scope Guardian */}
                <div className="rounded-xl border border-indigo-500/40 bg-indigo-950/20 p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-semibold text-indigo-300">
                      <Layers className="w-4 h-4 text-indigo-400" />
                      Resolution Hierarchy &amp; Fix Strategy Debate (Phase 7)
                    </div>
                    <span className="text-[10px] text-indigo-400 font-mono px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/20">
                      Resolution Lead &amp; Scope Guardian
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Activated only after developer acceptance. Coordinates <strong>Root Cause Analyst</strong>, <strong>Solution Architect</strong> (2–3 distinct strategies), <strong>Critic</strong>, <strong>Scope Guardian</strong>, and <strong>Rubric Evaluator</strong>.
                  </p>

                  <div className="flex items-center gap-3">
                    <button
                      onClick={handleRunResolution}
                      disabled={isResolving || selectedIssueDetail.status === "RECEIVED" || selectedIssueDetail.status === "INVESTIGATING"}
                      className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-40 flex items-center gap-2"
                    >
                      <Zap className={`w-3.5 h-3.5 ${isResolving ? "animate-spin" : ""}`} />
                      <span>{isResolving ? "Debating Fix Strategies..." : "Trigger Multi-Agent Fix Debate"}</span>
                    </button>
                  </div>

                  {solutions.length > 0 && (
                    <div className="space-y-3 pt-2">
                      <div className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider font-mono">
                        Ranked Fix Proposals ({solutions.length})
                      </div>
                      <div className="grid grid-cols-1 gap-3">
                        {solutions.map((sol, index) => (
                          <div
                            key={sol.id}
                            className={`p-3.5 rounded-lg border transition-all ${
                              selectedSolutionId === sol.id
                                ? "bg-indigo-950/60 border-indigo-500 shadow-md shadow-indigo-500/20"
                                : "bg-slate-950/80 border-slate-800 hover:border-slate-700"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="space-y-1">
                                <div className="flex items-center gap-2">
                                  <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300">
                                    Rank #{sol.rank || index + 1}
                                  </span>
                                  <h4 className="text-xs font-bold text-slate-200">{sol.title}</h4>
                                  {sol.is_recommended && (
                                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 uppercase">
                                      Recommended
                                    </span>
                                  )}
                                </div>
                                <p className="text-[11px] text-slate-300 leading-relaxed">{sol.description}</p>
                              </div>
                              <input
                                type="radio"
                                name="selectedSolution"
                                checked={selectedSolutionId === sol.id}
                                onChange={() => setSelectedSolutionId(sol.id)}
                                className="mt-1 accent-indigo-500 cursor-pointer"
                              />
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 text-[10px] font-mono">
                              <div className="p-2 rounded bg-slate-900/90 border border-slate-800">
                                <span className="text-slate-400 font-semibold">Affected Files:</span>
                                <div className="text-indigo-300 mt-0.5">{sol.affected_files?.join(", ") || "None"}</div>
                              </div>
                              <div className="p-2 rounded bg-slate-900/90 border border-slate-800">
                                <span className="text-slate-400 font-semibold">Complexity Score:</span>
                                <div className="text-amber-300 mt-0.5">{sol.complexity_score} / 5</div>
                              </div>
                            </div>

                            {/* Scope Guardian & Critic Summary */}
                            {sol.scope_assessment && (
                              <div className="mt-2 p-2 rounded bg-slate-900/80 border border-slate-800 text-[10px] space-y-1">
                                <div className="flex items-center gap-1.5 text-emerald-400 font-semibold">
                                  <ShieldCheck className="w-3.5 h-3.5" />
                                  <span>Scope Guardian Verdict: {sol.scope_assessment.verdict || "APPROVED"}</span>
                                </div>
                                {sol.critique?.hidden_risks && sol.critique.hidden_risks.length > 0 && (
                                  <div className="text-slate-400">
                                    <span className="text-amber-400">Critic Note:</span> {sol.critique.hidden_risks.join("; ")}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>

                      {/* Developer Fix Approval Form */}
                      <div className="p-3.5 rounded-lg bg-slate-950 border border-indigo-900/60 space-y-3">
                        <div className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          Developer Fix Approval Gate (Phase 7)
                        </div>
                        <p className="text-[11px] text-slate-400">
                          Select one of the ranked strategies above or provide custom implementation guidance below.
                        </p>
                        <div>
                          <label className="text-[10px] text-slate-400 uppercase font-mono">Custom Developer Strategy (Optional)</label>
                          <input
                            type="text"
                            placeholder="e.g. Only modify cart.js, keep existing helper signature."
                            value={customStrategyText}
                            onChange={(e) => setCustomStrategyText(e.target.value)}
                            className="w-full mt-1 px-2.5 py-1.5 rounded bg-slate-900 border border-slate-700 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                          />
                        </div>
                        <button
                          onClick={handleApproveFix}
                          disabled={isApprovingFix || (!selectedSolutionId && !customStrategyText.trim())}
                          className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow transition-all disabled:opacity-40"
                        >
                          {isApprovingFix ? "Recording Approval..." : "Approve Fix Strategy for Implementation"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* PHASE 8: Approved Implementation & Sandbox Verification */}
                <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/20 p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-semibold text-emerald-300">
                      <FolderGit2 className="w-4 h-4 text-emerald-400" />
                      Approved Implementation &amp; Sandbox Verification (Phase 8)
                    </div>
                    <span className="text-[10px] text-emerald-400 font-mono px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20">
                      Isolated Branch &bull; Strict Verifier
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Source code is modified strictly on an isolated Git branch (<code>fix/pragmata-issue-*</code>) after developer approval. The Verifier re-runs the original reproduction procedure and project tests inside Docker before marking the issue <strong>RESOLVED</strong>.
                  </p>

                  <div className="flex flex-wrap gap-3">
                    <button
                      onClick={handleRunImplementation}
                      disabled={isImplementing || actionLoading}
                      className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow transition-all disabled:opacity-40 flex items-center gap-2"
                    >
                      <Code2 className={`w-3.5 h-3.5 ${isImplementing ? "animate-spin" : ""}`} />
                      <span>{isImplementing ? "Writing Implementation..." : "Execute Approved Implementation"}</span>
                    </button>

                    <button
                      onClick={handleRunVerification}
                      disabled={isVerifying || actionLoading}
                      className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold shadow transition-all disabled:opacity-40 flex items-center gap-2"
                    >
                      <ShieldCheck className={`w-3.5 h-3.5 ${isVerifying ? "animate-spin" : ""}`} />
                      <span>{isVerifying ? "Running Sandbox Verification..." : "Run Sandbox Verification"}</span>
                    </button>
                  </div>

                  {/* Implementation and Verification Status Card */}
                  {implementationInfo?.has_implementation && (
                    <div className="p-3.5 rounded-lg bg-slate-950/90 border border-slate-800 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-emerald-400 font-bold">Branch: {implementationInfo.branch_name}</span>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                          Status: {implementationInfo.status}
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-400">
                        Base Commit: <code className="text-slate-300">{implementationInfo.base_commit_sha?.slice(0, 8)}</code>
                        {implementationInfo.commit_shas?.length > 0 && (
                          <span> &bull; Head Commit: <code className="text-emerald-300">{implementationInfo.commit_shas[0]?.slice(0, 8)}</code></span>
                        )}
                      </div>
                      <div className="text-[11px] text-slate-400">
                        Modified Files: <span className="font-mono text-slate-200">{implementationInfo.changed_files?.join(", ") || "None"}</span>
                      </div>

                      {verificationResult && (
                        <div className="mt-3 p-3 rounded bg-slate-900 border border-slate-800 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-slate-200">Verification Outcome:</span>
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              verificationResult.all_passed ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300"
                            }`}>
                              {verificationResult.overall_status}
                            </span>
                          </div>
                          <div className="text-[11px] space-y-1 font-mono">
                            <div className="text-slate-300">
                              Reproduction Check: {verificationResult.reproduction_check?.passed ? "PASSED (0)" : "FAILED"}
                            </div>
                            {verificationResult.test_suite_check && (
                              <div className="text-slate-300">
                                Test Suite Check: {verificationResult.test_suite_check.passed ? "PASSED (0)" : "FAILED"}
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Deterministic Lifecycle Transitions (Simulation Helper) */}
                <div className="rounded-lg bg-slate-950/40 border border-slate-800 p-3 space-y-2">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                    <span>Workflow Stage Controller</span>
                    <span className="font-mono text-[10px] text-slate-500">Orchestrator Actions</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedIssueDetail.status === "RECEIVED" && (
                      <button
                        onClick={() => handleTransition("INVESTIGATING", "Investigation delegated")}
                        disabled={actionLoading}
                        className="text-[11px] px-2.5 py-1 rounded bg-blue-900/40 hover:bg-blue-800/60 text-blue-300 border border-blue-700/60"
                      >
                        Start Investigation &rarr;
                      </button>
                    )}
                    {selectedIssueDetail.status === "INVESTIGATING" && (
                      <button
                        onClick={() => handleTransition("REPRODUCING", "Reproducer sandbox started")}
                        disabled={actionLoading}
                        className="text-[11px] px-2.5 py-1 rounded bg-purple-900/40 hover:bg-purple-800/60 text-purple-300 border border-purple-700/60"
                      >
                        Run Reproduction in Sandbox &rarr;
                      </button>
                    )}
                    {selectedIssueDetail.status === "REPRODUCING" && (
                      <button
                        onClick={() => handleTransition("REPRODUCED", "Behavior reproduced with evidence")}
                        disabled={actionLoading}
                        className="text-[11px] px-2.5 py-1 rounded bg-amber-900/40 hover:bg-amber-800/60 text-amber-300 border border-amber-700/60"
                      >
                        Mark Reproduced &rarr;
                      </button>
                    )}
                    {selectedIssueDetail.status === "REPRODUCED" && (
                      <button
                        onClick={() => handleTransition("AWAITING_DEVELOPER_TRIAGE", "Present evidence to developer")}
                        disabled={actionLoading}
                        className="text-[11px] px-2.5 py-1 rounded bg-amber-600/30 hover:bg-amber-600/50 text-amber-200 border border-amber-500/50"
                      >
                        Advance to Developer Triage Gate &rarr;
                      </button>
                    )}
                    {selectedIssueDetail.status === "ACCEPTED" && (
                      <button
                        onClick={() => handleTransition("ROOT_CAUSE_ANALYSIS", "Starting RCA")}
                        disabled={actionLoading}
                        className="text-[11px] px-2.5 py-1 rounded bg-indigo-900/40 hover:bg-indigo-800/60 text-indigo-300 border border-indigo-700/60"
                      >
                        Start Root Cause Analysis &rarr;
                      </button>
                    )}
                    {selectedIssueDetail.status === "ROOT_CAUSE_ANALYSIS" && (
                      <button
                        onClick={() => handleTransition("FIX_STRATEGY_DISCUSSION", "Architect & Critic debating")}
                        disabled={actionLoading}
                        className="text-[11px] px-2.5 py-1 rounded bg-indigo-900/40 hover:bg-indigo-800/60 text-indigo-300 border border-indigo-700/60"
                      >
                        Propose Fix Strategies &rarr;
                      </button>
                    )}
                  </div>
                </div>

                {/* Audit Trail Timeline */}
                <div className="space-y-3">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                    <History className="w-3.5 h-3.5 text-slate-500" />
                    Immutable Audit Trail ({selectedIssueDetail.audit_events.length} events)
                  </div>
                  <div className="space-y-2 border-l-2 border-slate-800 pl-3">
                    {selectedIssueDetail.audit_events.map((ae) => (
                      <div key={ae.id} className="text-xs space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-300 font-mono text-[11px]">
                            {ae.event_type}
                          </span>
                          <span className="text-[10px] text-slate-500 font-mono">
                            {new Date(ae.created_at).toLocaleTimeString()}
                          </span>
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                            by {ae.actor}
                          </span>
                        </div>
                        {ae.from_state && ae.to_state && (
                          <div className="text-[11px] text-slate-400 flex items-center gap-1 font-mono">
                            <span className="text-slate-500">{ae.from_state}</span>
                            <ArrowRight className="w-2.5 h-2.5 text-slate-600" />
                            <span className="text-indigo-400 font-semibold">{ae.to_state}</span>
                          </div>
                        )}
                        {ae.payload?.notes && (
                          <div className="text-[11px] text-slate-400 italic">
                            &ldquo;{ae.payload.notes}&rdquo;
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-80 text-center space-y-2 text-slate-500">
                <FileText className="w-8 h-8 text-slate-700" />
                <p className="text-xs">Select an issue from the list to view evidence and triage.</p>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* New Issue Submission Modal */}
      {showNewModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <Bug className="w-4 h-4 text-indigo-400" />
                  Submit Bug Report
                </h3>
                <p className="text-[11px] text-slate-400">
                  Describe what went wrong in plain language. Technical details are optional.
                </p>
              </div>
              <button
                onClick={() => setShowNewModal(false)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateIssue} className="space-y-3.5 text-xs">
              <div>
                <label className="block text-[11px] font-semibold text-slate-300 mb-1">
                  Summary / Title <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Total price does not update when removing an item"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:border-indigo-500 text-xs"
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-300 mb-1">
                  What happened? <span className="text-rose-400">*</span>
                </label>
                <textarea
                  required
                  rows={4}
                  placeholder="Explain what occurred in your own words..."
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:border-indigo-500 text-xs"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-medium text-slate-400 mb-1">
                    Expected Behavior (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Total should decrease"
                    value={newExpected}
                    onChange={(e) => setNewExpected(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:border-indigo-500 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-400 mb-1">
                    Browser / OS (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Chrome on macOS"
                    value={newBrowser}
                    onChange={(e) => setNewBrowser(e.target.value)}
                    className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:border-indigo-500 text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">
                  Steps you took before it happened (Optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Added item, clicked delete button, saw no update"
                  value={newSteps}
                  onChange={(e) => setNewSteps(e.target.value)}
                  className="w-full px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-700 text-slate-200 focus:outline-none focus:border-indigo-500 text-xs"
                />
              </div>

              <div className="flex justify-end space-x-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowNewModal(false)}
                  className="px-3.5 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !newTitle.trim() || !newDescription.trim()}
                  className="px-4 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-500 text-white font-semibold shadow disabled:opacity-50"
                >
                  {actionLoading ? "Submitting..." : "Submit Report"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="border-t border-slate-800/80 px-6 py-4 text-center text-xs text-slate-500">
        PRAGMATA &bull; Collaborative Multi-Agent Bug Resolution Platform &bull; Human Authority Invariant
      </footer>
    </div>
  );
}
