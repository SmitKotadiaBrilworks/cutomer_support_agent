"use client";

import { useEffect, useMemo, useState } from "react";
import ChatWindow from "@/components/ChatWindow";
import AgentSidebar from "@/components/AgentSidebar";
import { ApiError, getHealth, HealthResponse, sendChat } from "@/lib/api";
import { ChatMessage, computeStats, CUSTOMERS } from "@/lib/types";

function newSessionId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function welcomeMessage(content: string): ChatMessage {
  return { id: "welcome", role: "assistant", content, timestamp: Date.now() };
}

const CAPABILITY_BADGES = [
  "LangGraph orchestration",
  "4 cooperating agents",
  "structured outputs",
  "multi-provider",
];

export default function Home() {
  const [sessionId, setSessionId] = useState(() => newSessionId());
  const [customerId, setCustomerId] = useState("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    welcomeMessage(
      "Hi! I'm UrbanCart's support assistant — behind the scenes, a Triage Agent routes you to one of three specialist agents (Order & Returns, FAQ, or Escalation). Try an example below, or ask your own question.",
    ),
  ]);
  const [sending, setSending] = useState(false);
  const [lastTicketId, setLastTicketId] = useState<string | null>(null);
  const [activeAgentPath, setActiveAgentPath] = useState<string[]>([]);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const [turnKey, setTurnKey] = useState("initial");

  const stats = useMemo(() => computeStats(messages), [messages]);

  useEffect(() => {
    const refreshHealth = () =>
      getHealth()
        .then(setHealth)
        .catch(() => setHealth(null));
    refreshHealth();
    const interval = setInterval(refreshHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  function resetConversation() {
    setSessionId(newSessionId());
    setMessages([
      welcomeMessage(
        "New conversation started. Memory from the previous session won't carry over.",
      ),
    ]);
    setActiveAgentPath([]);
    setActiveTools([]);
    setLastTicketId(null);
    setTurnKey(`reset-${Date.now()}`);
  }

  async function handleSend(text: string) {
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);
    const startedAt = performance.now();
    try {
      const res = await sendChat(sessionId, text, customerId || null);
      const latencyMs = Math.round(performance.now() - startedAt);
      setActiveAgentPath(res.agent_path);
      setActiveTools(res.tools_used);
      setTurnKey(`${Date.now()}`);
      if (res.ticket_id) setLastTicketId(res.ticket_id);

      const assistantMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: "assistant",
        content: res.reply,
        timestamp: Date.now(),
        meta: {
          agent_path: res.agent_path,
          tools_used: res.tools_used,
          provider_used: res.provider_used,
          intent: res.intent,
          sentiment: res.sentiment,
          escalated: res.escalated,
          ticket_id: res.ticket_id,
          latencyMs,
        },
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (e) {
      const detail =
        e instanceof ApiError
          ? e.message
          : "Network error talking to the backend.";
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "system",
          content: detail,
          timestamp: Date.now(),
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="bg-mesh min-h-screen lg:h-screen lg:overflow-hidden flex flex-col">
      <header className="shrink-0 border-b border-[var(--border)] bg-white/97 backdrop-blur-md sticky top-0 z-10">
        <div className="mx-auto px-32 py-4 flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <div
              className="h-10 w-10 rounded-xl flex items-center justify-center text-white font-semibold text-sm"
              style={{
                background:
                  "linear-gradient(135deg, var(--brand), var(--brand-strong))",
                boxShadow: "0 4px 14px -4px rgba(61,58,138,0.45)",
              }}
            >
              UC
            </div>
            <div>
              <h1 className="text-[15px] font-semibold leading-tight tracking-tight">
                UrbanCart Support
              </h1>
              <p className="text-[12px] text-[var(--text-muted)] leading-tight">
                Multi-agent AI support system
              </p>
            </div>
          </div>

          {/* <div className="hidden md:flex items-center gap-1.5">
            {CAPABILITY_BADGES.map((b) => (
              <span
                key={b}
                className="text-[11px] font-medium rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-1.5 text-[var(--text-muted)]"
              >
                {b}
              </span>
            ))}
          </div> */}

          <div className="flex items-center gap-2 w-full sm:w-auto">
            <select
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              className="min-w-0 flex-1 sm:flex-initial text-[13px] rounded-lg border border-[var(--border-strong)] bg-white px-2.5 py-2 text-[var(--foreground)] shadow-sm"
            >
              {CUSTOMERS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
            <button
              onClick={resetConversation}
              className="shrink-0 whitespace-nowrap text-[13px] font-medium rounded-lg border border-[var(--border-strong)] bg-white px-3.5 py-2 text-[var(--foreground)] shadow-sm hover:bg-[var(--surface-muted)] transition-colors"
            >
              New conversation
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto px-32 py-7 flex flex-col lg:flex-row gap-5 w-full flex-1 min-h-0 lg:overflow-hidden">
        <ChatWindow
          messages={messages}
          sending={sending}
          onSend={handleSend}
          customerId={customerId}
        />
        <AgentSidebar
          activeAgentPath={activeAgentPath}
          activeTools={activeTools}
          turnKey={turnKey}
          stats={stats}
          health={health}
          lastTicketId={lastTicketId}
        />
      </main>
    </div>
  );
}
