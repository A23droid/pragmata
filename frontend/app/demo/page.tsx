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
  log: LogEntry[];
}

interface SwitchMessage {
  id: string;
  sender: string;
  content: string;
  created_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  RECEIVED: "bg-slate-700 text-slate-200",
  INVESTIGATING: "bg-blue-900/70 text-blue-300",
  AWAITING_DEVELOPER_TRIAGE: "bg-amber-900/70 text-amber-300 animate-pulse",
  ACCEPTED: "bg-emerald-900/70 text-emerald-300",
  ROOT_CAUSE_ANALYSIS: "bg-indigo-900/70 text-indigo-300",
  FIX_STRATEGY_DISCUSSION: "bg-violet-900/70 text-violet-300",
  AWAITING_FIX_APPROVAL: "bg-cyan-900/70 text-cyan-300 animate-pulse",
  IMPLEMENTING: "bg-orange-900/70 text-orange-300",
  VERIFYING: "bg-sky-900/70 text-sky-300",
  RESOLVED: "bg-emerald-500/30 text-emerald-200 font-bold",
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
  INTAKE: "1. Intake",
  INVESTIGATION: "2. Investigate",
  REPRODUCTION: "3. Reproduce",
  TRIAGE: "4. Dev Triage",
  RCA: "5. Root Cause",
  FIX_DEBATE: "6. Fix Debate",
  FIX_APPROVAL: "7. Dev Approves",
  IMPLEMENTATION: "8. Implement",
  VERIFICATION: "9. Verify",
  RESOLVED: "✅ Resolved",
};

function markdownLite(text: string) {
  // Very light markdown: **bold**, `code`, ```block```
  const lines = text.split("\n");
  return lines.map((line, i) => {
    if (line.startsWith("```")) return null; // handled below
    return (
      <span key={i}>
        {line
          .replace(/\*\*(.+?)\*\*/g, (_, m) => `@@BOLD@@${m}@@BOLD@@`)
          .replace(/`(.+?)`/g, (_, m) => `@@CODE@@${m}@@CODE@@`)
          .split(/@@(BOLD|CODE)@@/)
          .map((chunk, j, arr) => {
            if (arr[j - 1] === "BOLD") return <strong key={j}>{chunk}</strong>;
            if (arr[j - 1] === "CODE")
              return (
                <code key={j} className="bg-slate-800 px-1 rounded text-sky-300 font-mono text-[11px]">
                  {chunk}
                </code>
              );
            if (chunk === "BOLD" || chunk === "CODE") return null;
            return chunk;
          })}
        {"\n"}
      </span>
    );
  });
}

export default function DemoPage() {
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [messages, setMessages] = useState<SwitchMessage[]>([]);
  const [started, setStarted] = useState(false);
  const [loading, setLoading] = useState(false);
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

      // Also fetch Switch room messages
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
      // Reset first
      await fetch(`${API}/api/v1/demo/reset`, { method: "POST" });
      // Start
      await fetch(`${API}/api/v1/demo/run`, { method: "POST" });
      setStarted(true);
      // Poll every 600ms
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(fetchStatus, 600);
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
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur px-6 py-3 flex items-center justify-between sticky top-0 z-20">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30 text-sm">
            P
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-white">
              PRAGMATA{" "}
              <span className="text-xs font-normal text-indigo-400 font-mono">
                · Hardcoded Demo Flow
              </span>
            </h1>
            <p className="text-[11px] text-slate-400">
              Cart Discount Bug · End-to-End AI Investigation & Fix
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="/"
            className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 px-3 py-1 rounded-md transition-colors"
          >
            ← Dashboard
          </a>
          {started && (
            <button
              onClick={resetDemo}
              className="text-xs text-rose-400 hover:text-rose-200 border border-rose-900 px-3 py-1 rounded-md transition-colors"
            >
              Reset
            </button>
          )}
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* LEFT: Demo Controls + Timeline */}
        <div className="space-y-5">
          {/* Bug Report Card */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Bug Report
              </div>
              <span
                className={`text-[10px] px-2.5 py-0.5 rounded-full font-mono border ${
                  STATUS_COLORS[issueStatus] ?? "bg-slate-800 text-slate-300 border-slate-700"
                }`}
              >
                {issueStatus}
              </span>
            </div>
            <div>
              <div className="font-mono text-xs text-indigo-400 mb-1">demo-001</div>
              <h2 className="text-sm font-bold text-white">
                SAVE20 discount coupon not applying on $100 cart
              </h2>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed">
              When a customer adds a $100 item and applies the SAVE20 coupon, the total stays at
              $100 instead of $80. The 20% discount is completely ignored for carts totalling
              exactly $100.
            </p>
            <div className="text-[11px] text-slate-500 font-mono bg-slate-950 rounded-lg border border-slate-800 p-2.5 space-y-0.5">
              <div>
                <span className="text-slate-400">File:</span>{" "}
                demo/sample-node-cart/src/cart.js:30
              </div>
              <div>
                <span className="text-rose-400">Bug:</span>{" "}
                <code className="text-rose-300">if (subtotal &gt; 100 …)</code>
              </div>
              <div>
                <span className="text-emerald-400">Fix:</span>{" "}
                <code className="text-emerald-300">if (subtotal &gt;= 100 …)</code>
              </div>
            </div>
          </div>

          {/* Start button */}
          {!started && (
            <button
              onClick={startDemo}
              disabled={loading}
              className="w-full py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <span className="inline-block animate-spin">⚙️</span> Starting…
                </>
              ) : (
                <>🚀 Run Demo Flow</>
              )}
            </button>
          )}

          {/* Progress bar */}
          {started && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>
                  Progress — {status?.steps_completed ?? 0} / {status?.total_steps ?? 10} steps
                </span>
                <span className="font-mono text-indigo-400">{progress}%</span>
              </div>
              <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Phase Timeline */}
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-1">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
              Workflow Phases
            </div>
            <div className="space-y-1">
              {PHASE_ORDER.map((phase) => {
                const donePhases = status?.log?.map((e) => e.phase) ?? [];
                const isDone = donePhases.includes(phase);
                const isCurrent = phase === currentPhase;
                return (
                  <div
                    key={phase}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-all ${
                      isCurrent
                        ? "bg-indigo-900/50 border border-indigo-500/50 text-indigo-200 font-semibold"
                        : isDone
                        ? "bg-slate-800/40 text-emerald-400"
                        : "text-slate-600"
                    }`}
                  >
                    <span className="text-sm">
                      {isDone ? "✅" : isCurrent ? "⚡" : "○"}
                    </span>
                    <span className="font-mono">{PHASE_LABEL[phase]}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* RIGHT: Switch Console Room Feed */}
        <div className="flex flex-col rounded-2xl border border-indigo-900/60 bg-slate-900/50 overflow-hidden">
          {/* Room Header */}
          <div className="px-5 py-3 border-b border-slate-800 bg-slate-900 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="h-6 w-6 rounded-md bg-indigo-700 flex items-center justify-center text-xs font-bold">
                S
              </div>
              <div>
                <div className="text-xs font-semibold text-white">Switch Console</div>
                <div className="text-[10px] text-slate-400 font-mono">
                  #pragmata-bug-demo-001
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-400">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  status?.running ? "bg-emerald-400 animate-pulse" : "bg-slate-600"
                }`}
              />
              {status?.running ? "Live" : messages.length > 0 ? "Complete" : "Waiting"}
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[400px] max-h-[600px]">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-slate-600 text-xs space-y-2 py-16">
                <div className="text-3xl">💬</div>
                <div>Agent messages will appear here when the demo runs</div>
              </div>
            )}
            {messages.map((msg) => {
              const isHuman = msg.sender.includes("Developer");
              const isOrchestrator = msg.sender.includes("Orchestrator");
              return (
                <div key={msg.id} className="space-y-1">
                  <div
                    className={`flex items-center gap-2 text-[10px] font-mono ${
                      isHuman
                        ? "text-cyan-400"
                        : isOrchestrator
                        ? "text-indigo-400"
                        : "text-amber-400"
                    }`}
                  >
                    <span>{msg.sender}</span>
                    <span className="text-slate-600">
                      {new Date(msg.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div
                    className={`rounded-xl px-3.5 py-2.5 text-xs leading-relaxed whitespace-pre-wrap max-w-full border ${
                      isHuman
                        ? "bg-cyan-950/40 border-cyan-900/50 text-cyan-100"
                        : isOrchestrator
                        ? "bg-indigo-950/50 border-indigo-900/50 text-indigo-100"
                        : "bg-slate-800/60 border-slate-700/50 text-slate-200"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Footer Agent Count */}
          <div className="px-4 py-2.5 border-t border-slate-800 bg-slate-900/80 flex items-center justify-between text-[10px] font-mono text-slate-500">
            <span>8 agents active · demo-room-pragmata-001</span>
            <span>{messages.length} messages</span>
          </div>
        </div>
      </main>
    </div>
  );
}
