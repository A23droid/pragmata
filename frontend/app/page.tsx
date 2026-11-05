"use client";

import { useEffect, useState } from "react";
import {
  fetchHealth,
  fetchIssues,
  fetchIssueDetail,
  createIssue,
  triageIssue,
  transitionIssue,
  HealthStatus,
  Issue,
  IssueDetail,
} from "@/lib/api";
import {
  AlertCircle,
  ArrowRight,
  Bug,
  CheckCircle2,
  Clock,
  Database,
  FileText,
  Filter,
  History,
  Layers,
  PlusCircle,
  RefreshCw,
  Server,
  ShieldAlert,
  ShieldCheck,
  User,
  X,
} from "lucide-react";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
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

  const refreshAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, iss] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchIssues(statusFilter || undefined).catch(() => []),
      ]);
      setHealth(h);
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
      const detail = await fetchIssueDetail(id);
      setSelectedIssueDetail(detail);
      setSelectedIssueId(id);
    } catch (err: any) {
      setError(err.message || "Failed to load issue detail");
    } finally {
      setDetailLoading(false);
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
        return "bg-purple-950/60 text-purple-400 border-purple-800/60";
      case "REPRODUCED":
        return "bg-amber-950/60 text-amber-400 border-amber-800/60";
      case "AWAITING_DEVELOPER_TRIAGE":
        return "bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse";
      case "ACCEPTED":
        return "bg-emerald-950/60 text-emerald-400 border-emerald-800/60";
      case "ROOT_CAUSE_ANALYSIS":
      case "FIX_STRATEGY_DISCUSSION":
        return "bg-indigo-950/60 text-indigo-400 border-indigo-800/60";
      case "AWAITING_FIX_APPROVAL":
        return "bg-cyan-500/20 text-cyan-300 border-cyan-500/40";
      case "IMPLEMENTING":
        return "bg-cyan-950/60 text-cyan-400 border-cyan-800/60";
      case "VERIFYING":
        return "bg-yellow-950/60 text-yellow-400 border-yellow-800/60";
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
                Phase 2
              </span>
            </h1>
            <p className="text-[11px] text-slate-400">
              Deterministic Workflow Engine & Bug Resolution Platform
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Health Pill */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800/80 border border-slate-700/60 text-[11px] text-slate-300">
            {health?.database === "connected" ? (
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
            ) : (
              <span className="h-2 w-2 rounded-full bg-amber-400" />
            )}
            <span>Backend: {health?.status || "Connecting..."}</span>
          </div>

          <button
            onClick={refreshAll}
            disabled={loading}
            className="p-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors border border-slate-700"
            title="Refresh issues"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>

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
              "",
              "RECEIVED",
              "INVESTIGATING",
              "REPRODUCED",
              "AWAITING_DEVELOPER_TRIAGE",
              "ACCEPTED",
              "RESOLVED",
              "REJECTED",
              "DEFERRED",
            ].map((st) => (
              <button
                key={st || "ALL"}
                onClick={() => setStatusFilter(st)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors border ${
                  statusFilter === st
                    ? "bg-indigo-600/20 text-indigo-300 border-indigo-500/50"
                    : "bg-slate-900/60 text-slate-400 hover:text-slate-200 border-slate-800"
                }`}
              >
                {st || "ALL ISSUES"}
              </button>
            ))}
          </div>

          <div className="text-xs text-slate-500 font-mono">
            Total Issues: {issues.length}
          </div>
        </div>

        {/* Two-Column Layout: Issues List & Detail View */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Issue List (5 cols on lg) */}
          <div className="lg:col-span-5 space-y-2">
            {issues.length === 0 ? (
              <div className="p-8 rounded-xl border border-dashed border-slate-800 text-center space-y-3">
                <Bug className="w-8 h-8 text-slate-600 mx-auto" />
                <p className="text-xs text-slate-400">No issues matching criteria.</p>
                <button
                  onClick={() => setShowNewModal(true)}
                  className="text-xs text-indigo-400 hover:text-indigo-300 underline font-medium"
                >
                  Submit the first bug report
                </button>
              </div>
            ) : (
              issues.map((issue) => (
                <div
                  key={issue.id}
                  onClick={() => loadDetail(issue.id)}
                  className={`p-3.5 rounded-lg border transition-all cursor-pointer ${
                    selectedIssueId === issue.id
                      ? "bg-slate-900 border-indigo-500/80 shadow-md shadow-indigo-950/50"
                      : "bg-slate-900/40 hover:bg-slate-900/80 border-slate-800/80"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="font-mono text-[11px] font-semibold text-indigo-400">
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
                  <h3 className="text-xs font-semibold text-slate-200 line-clamp-1 mb-1">
                    {issue.title}
                  </h3>
                  <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                    {issue.description}
                  </p>
                  <div className="flex items-center justify-between text-[10px] text-slate-500 mt-2 font-mono">
                    <span>{new Date(issue.created_at).toLocaleTimeString()}</span>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Issue Detail (7 cols on lg) */}
          <div className="lg:col-span-7 rounded-xl border border-slate-800 bg-slate-900/40 p-5 min-h-[500px]">
            {detailLoading ? (
              <div className="flex items-center justify-center h-64 text-xs text-slate-500">
                <RefreshCw className="w-5 h-5 animate-spin mr-2" />
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
