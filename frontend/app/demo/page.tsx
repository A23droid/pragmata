"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API = "http://localhost:8000";

type Phase =
  | "IDLE"
  | "INTAKE"
  | "INVESTIGATION"
  | "REPRODUCTION"
  | "TRIAGE"
  | "RCA"
  | "FIX_DEBATE"
  | "FIX_APPROVAL"
  | "IMPLEMENTATION"
  | "VERIFICATION"
  | "RESOLVED";

interface LogEntry {
  phase: string;
  agent: string;
  status: string;
  message: string;
  timestamp: string;
}

interface DemoStatus {
  running: boolean;
  room_id: string | null;
  issue: Record<string, any> | null;
  steps_completed: number;
  total_steps: number;
  slack_enabled?: boolean;
  log: LogEntry[];
}

interface SwitchMessage {
  id: string;
  sender: string;
  content: string;
  created_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  RECEIVED: "bg-slate-700 text-slate-200 border-slate-600",
  INVESTIGATING: "bg-blue-900/70 text-blue-300 border-blue-700",
  AWAITING_DEVELOPER_TRIAGE: "bg-amber-900/70 text-amber-300 border-amber-600 animate-pulse",
  ACCEPTED: "bg-emerald-900/70 text-emerald-300 border-emerald-700",
  ROOT_CAUSE_ANALYSIS: "bg-indigo-900/70 text-indigo-300 border-indigo-700",
  FIX_STRATEGY_DISCUSSION: "bg-violet-900/70 text-violet-300 border-violet-700",
  AWAITING_FIX_APPROVAL: "bg-cyan-900/70 text-cyan-300 border-cyan-600 animate-pulse",
  IMPLEMENTING: "bg-orange-900/70 text-orange-300 border-orange-700",
  VERIFYING: "bg-sky-900/70 text-sky-300 border-sky-700",
  RESOLVED: "bg-emerald-500/30 text-emerald-200 border-emerald-500 font-bold",
};

const PHASE_ORDER: Phase[] = [
  "INTAKE",
  "INVESTIGATION",
  "REPRODUCTION",
  "TRIAGE",
  "RCA",
  "FIX_DEBATE",
  "FIX_APPROVAL",
  "IMPLEMENTATION",
  "VERIFICATION",
  "RESOLVED",
];

const PHASE_LABEL: Record<string, string> = {
  INTAKE: "1. Intake & Hypothesis",
  INVESTIGATION: "2. Static AST Scan",
  REPRODUCTION: "3. Docker Sandbox Repro",
  TRIAGE: "4. Human Developer Triage",
  RCA: "5. Root Cause & Blast Radius",
  FIX_DEBATE: "6. Architect / Scope Debate",
  FIX_APPROVAL: "7. Developer Fix Approval",
  IMPLEMENTATION: "8. Patch & Branch",
  VERIFICATION: "9. Regression Test Suite",
  RESOLVED: "✅ Fixed & Verified",
};

export default function DemoPage() {
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [messages, setMessages] = useState<SwitchMessage[]>([]);
  const [started, setStarted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [speed, setSpeed] = useState<"realistic" | "fast">("realistic");
  const [slackUrl, setSlackUrl] = useState("");
  const [showSlackConfig, setShowSlackConfig] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/v1/demo/status`);
      const data: DemoStatus = await r.json();
      setStatus(data);

      const mr = await fetch(`${API}/gateway/rooms/demo-room-pragmata-001/messages`);
      if (mr.ok) {
        const msgs = await mr.json();
        setMessages(msgs);
        scrollToBottom();
      }

      if (!data.running && data.steps_completed === data.total_steps && data.total_steps > 0) {
        if (pollRef.current) clearInterval(pollRef.current);
      }
    } catch {}
  }, []);

  const startDemo = async () => {
    setLoading(true);
    try {
      await fetch(`${API}/api/v1/demo/reset`, { method: "POST" });
      await fetch(`${API}/api/v1/demo/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          speed,
          slack_webhook_url: slackUrl.trim() || undefined,
        }),
      });
      setStarted(true);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(fetchStatus, 700);
    } finally {
      setLoading(false);
    }
  };

  const resetDemo = async () => {
    if (pollRef.current) clearInterval(pollRef.current);
    await fetch(`${API}/api/v1/demo/reset`, { method: "POST" });
    setStarted(false);
    setStatus(null);
    setMessages([]);
  };

  useEffect(() => {
    fetchStatus();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchStatus]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const currentPhase = status?.log?.at(-1)?.phase ?? "IDLE";
  const issueStatus = status?.issue?.status ?? "RECEIVED";
  const progress =
    status && status.total_steps > 0
      ? Math.round((status.steps_completed / status.total_steps) * 100)
      : 0;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans flex flex-col">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur px-6 py-3 flex items-center justify-between sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30 text-sm">
            P
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-white flex items-center gap-2">
              PRAGMATA
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-mono">
                Live Video Demo Control
              </span>
            </h1>
            <p className="text-[11px] text-slate-400">
              Dual Screen Ready: Watch in <strong>Switch Console</strong> or <strong>Slack</strong>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowSlackConfig(!showSlackConfig)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
              slackUrl.trim()
                ? "bg-emerald-950/80 border-emerald-600 text-emerald-300"
                : "bg-slate-900 border-slate-700 text-slate-300 hover:border-slate-500"
            }`}
          >
            <span>💬</span>
            <span>{slackUrl.trim() ? "Slack Connected" : "Connect Slack"}</span>
          </button>

          <a
            href="/"
            className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 px-3 py-1.5 rounded-lg transition-colors"
          >
            ← Main Dashboard
          </a>

          {started && (
            <button
              onClick={resetDemo}
              className="text-xs text-rose-400 hover:text-rose-200 border border-rose-900 px-3 py-1.5 rounded-lg transition-colors"
            >
              Reset
            </button>
          )}
        </div>
      </header>

      {/* Optional Slack Webhook Dropdown */}
      {showSlackConfig && (
        <div className="border-b border-slate-800 bg-slate-900/90 px-6 py-3.5 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="space-y-1">
            <span className="font-semibold text-slate-200">Broadcast to Real Slack Channel:</span>
            <p className="text-[11px] text-slate-400">
              Paste an Incoming Webhook URL to stream all agent messages straight into your Slack workspace during recording.
            </p>
          </div>
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <input
              type="text"
              placeholder="https://hooks.slack.com/services/T.../B.../..."
              value={slackUrl}
              onChange={(e) => setSlackUrl(e.target.value)}
              className="px-3 py-1.5 rounded-md bg-slate-950 border border-slate-700 text-slate-200 text-xs w-80 font-mono focus:outline-none focus:border-indigo-500"
            />
            <button
              onClick={() => setShowSlackConfig(false)}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md font-semibold"
            >
              Save
            </button>
          </div>
        </div>
      )}

      {/* Main Content: Left Control, Right Switch App Stream */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT COLUMN: Controls & State Machine (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          {/* Issue Summary Card */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold tracking-wider uppercase text-slate-400 font-mono">
                Target Issue
              </span>
              <span
                className={`text-[11px] px-2.5 py-0.5 rounded-full font-mono border ${
                  STATUS_COLORS[issueStatus] ?? "bg-slate-800 text-slate-300 border-slate-700"
                }`}
              >
                {issueStatus}
              </span>
            </div>

            <div>
              <div className="font-mono text-xs text-indigo-400 font-bold mb-0.5">demo-001</div>
              <h2 className="text-sm font-bold text-white">
                SAVE20 discount coupon not applying on $100 cart
              </h2>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              When a customer adds a $100 item and applies the SAVE20 coupon, the total stays at
              $100 instead of $80. The 20% discount is completely ignored for carts totalling
              exactly $100.
            </p>

            <div className="text-[11px] text-slate-400 font-mono bg-slate-950/80 rounded-xl border border-slate-800 p-3 space-y-1">
              <div>
                <span className="text-slate-500">Repository:</span>{" "}
                <span className="text-slate-200">demo/sample-node-cart (Node.js)</span>
              </div>
              <div>
                <span className="text-rose-400 font-bold">Buggy Code:</span>{" "}
                <code className="text-rose-300">if (subtotal &gt; 100 && discountRate &gt; 0)</code>
              </div>
              <div>
                <span className="text-emerald-400 font-bold">Approved Fix:</span>{" "}
                <code className="text-emerald-300">if (subtotal &gt;= 100 && discountRate &gt; 0)</code>
              </div>
            </div>
          </div>

          {/* Execution Controls */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-300">Playback Pacing:</span>
              <div className="flex gap-1.5 bg-slate-950 p-1 rounded-lg border border-slate-800">
                <button
                  onClick={() => setSpeed("realistic")}
                  className={`px-2.5 py-1 rounded text-[11px] font-medium transition-all ${
                    speed === "realistic"
                      ? "bg-indigo-600 text-white font-bold"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Realistic (~32s for Video)
                </button>
                <button
                  onClick={() => setSpeed("fast")}
                  className={`px-2.5 py-1 rounded text-[11px] font-medium transition-all ${
                    speed === "fast"
                      ? "bg-indigo-600 text-white font-bold"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Fast (~8s)
                </button>
              </div>
            </div>

            {!started && (
              <button
                onClick={startDemo}
                disabled={loading}
                className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>Starting Demo Workflow...</>
                ) : (
                  <>🚀 Launch Multi-Agent Workflow</>
                )}
              </button>
            )}

            {started && (
              <div className="space-y-1.5 pt-1">
                <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
                  <span>
                    Step {status?.steps_completed ?? 0} of {status?.total_steps ?? 10}
                  </span>
                  <span className="text-indigo-400 font-bold">{progress}%</span>
                </div>
                <div className="h-2 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
                  <div
                    className="h-full bg-gradient-to-r from-indigo-500 to-emerald-400 rounded-full transition-all duration-700"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Workflow State Tracker */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-4 space-y-2">
            <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 font-mono">
              9-Phase Workflow Pipeline
            </div>
            <div className="space-y-1">
              {PHASE_ORDER.map((phase) => {
                const donePhases = status?.log?.map((e) => e.phase) ?? [];
                const isDone = donePhases.includes(phase);
                const isCurrent = phase === currentPhase;
                return (
                  <div
                    key={phase}
                    className={`flex items-center justify-between px-3 py-1.5 rounded-lg text-xs transition-all ${
                      isCurrent
                        ? "bg-indigo-900/60 border border-indigo-500/60 text-indigo-200 font-bold"
                        : isDone
                        ? "bg-slate-900/80 text-emerald-400 border border-emerald-950/40"
                        : "text-slate-600 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-2 font-mono">
                      <span>{isDone ? "✅" : isCurrent ? "⚡" : "○"}</span>
                      <span>{PHASE_LABEL[phase]}</span>
                    </div>
                    {isCurrent && (
                      <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300">
                        Active
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Live Collaboration Stream (7 cols) */}
        <div className="lg:col-span-7 flex flex-col rounded-2xl border border-indigo-900/50 bg-slate-900/60 overflow-hidden shadow-2xl">
          {/* Header */}
          <div className="px-5 py-3.5 border-b border-slate-800 bg-slate-900/90 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="h-7 w-7 rounded-lg bg-indigo-600 flex items-center justify-center text-xs font-bold shadow-md shadow-indigo-600/30">
                S
              </div>
              <div>
                <div className="text-xs font-bold text-white flex items-center gap-2">
                  Switch Console Room
                  <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                    #pragmata-demo-001
                  </span>
                </div>
                <div className="text-[10px] text-slate-400 font-mono">
                  Live synced with Switch Desktop App (port 8000)
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 text-[11px] font-mono">
              <span
                className={`h-2 w-2 rounded-full ${
                  status?.running ? "bg-emerald-400 animate-pulse" : "bg-slate-500"
                }`}
              />
              <span className="text-slate-400">
                {status?.running ? "Streaming Agents" : messages.length > 0 ? "Workflow Complete" : "Standby"}
              </span>
            </div>
          </div>

          {/* Messages Feed */}
          <div className="flex-1 overflow-y-auto p-5 space-y-3.5 min-h-[520px] max-h-[680px]">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-slate-500 text-xs space-y-3 py-24">
                <div className="text-4xl">🤖</div>
                <div className="font-semibold text-slate-400">Awaiting Demo Execution</div>
                <p className="text-[11px] text-slate-500 text-center max-w-sm">
                  Click <strong>&quot;Launch Multi-Agent Workflow&quot;</strong> to begin. Messages will stream live into this room and your local Switch Console application.
                </p>
              </div>
            )}

            {messages.map((msg) => {
              const isHuman = msg.sender.includes("Developer");
              const isOrchestrator = msg.sender.includes("Orchestrator");
              const isLead = msg.sender.includes("Lead") || msg.sender.includes("Architect");
              return (
                <div key={msg.id} className="space-y-1.5 animate-fadeIn">
                  <div className="flex items-center justify-between text-[11px] font-mono">
                    <span
                      className={`font-bold flex items-center gap-1.5 ${
                        isHuman
                          ? "text-cyan-400"
                          : isOrchestrator
                          ? "text-indigo-400"
                          : isLead
                          ? "text-amber-400"
                          : "text-emerald-400"
                      }`}
                    >
                      {msg.sender}
                    </span>
                    <span className="text-slate-600 text-[10px]">
                      {new Date(msg.created_at).toLocaleTimeString()}
                    </span>
                  </div>

                  <div
                    className={`rounded-xl px-4 py-3 text-xs leading-relaxed whitespace-pre-wrap border ${
                      isHuman
                        ? "bg-cyan-950/30 border-cyan-800/60 text-cyan-100 shadow-sm"
                        : isOrchestrator
                        ? "bg-indigo-950/40 border-indigo-800/60 text-indigo-100"
                        : "bg-slate-950/80 border-slate-800 text-slate-200"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Footer Status */}
          <div className="px-5 py-2.5 border-t border-slate-800 bg-slate-900/90 flex items-center justify-between text-[11px] font-mono text-slate-500">
            <span>8 Active Specialized Agents · Canonical PostgreSQL State</span>
            <span>{messages.length} Events Logged</span>
          </div>
        </div>
      </main>
    </div>
  );
}
