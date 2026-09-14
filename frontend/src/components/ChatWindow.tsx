"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { ChatMessage, EXAMPLE_PROMPTS } from "@/lib/types";
import { themeFor } from "@/lib/agentTheme";

// Tight, chat-bubble-appropriate spacing — the browser's default markdown
// spacing (large paragraph/list margins) reads fine in a document, not in a
// 14px chat bubble.
const MARKDOWN_COMPONENTS: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 last:mb-0 pl-4 list-disc space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 last:mb-0 pl-4 list-decimal space-y-0.5">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em>{children}</em>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-black/[0.06] px-1 py-0.5 text-[12.5px] font-mono">{children}</code>
  ),
  h1: ({ children }) => <p className="font-semibold mb-1">{children}</p>,
  h2: ({ children }) => <p className="font-semibold mb-1">{children}</p>,
  h3: ({ children }) => <p className="font-semibold mb-1">{children}</p>,
};

const AGENT_INITIALS: Record<string, string> = {
  "Triage Agent": "TR",
  "Order & Returns Agent": "OR",
  "FAQ / Knowledge Agent": "FQ",
  "Escalation Agent": "ES",
};

function Avatar({ role, lastAgent }: { role: ChatMessage["role"]; lastAgent?: string }) {
  if (role === "user") {
    return (
      <div
        className="h-8 w-8 shrink-0 rounded-full text-white text-[10px] font-semibold flex items-center justify-center"
        style={{ background: "linear-gradient(135deg, var(--brand), var(--brand-strong))" }}
      >
        You
      </div>
    );
  }
  if (role === "system") {
    return (
      <div className="h-8 w-8 shrink-0 rounded-full bg-[#faf1e6] text-[#8a5a1f] text-sm font-semibold flex items-center justify-center">
        !
      </div>
    );
  }
  const theme = themeFor(lastAgent);
  return (
    <div className={`h-8 w-8 shrink-0 rounded-full ${theme.badge} text-[9px] font-bold flex items-center justify-center`}>
      {lastAgent ? AGENT_INITIALS[lastAgent] ?? "AI" : "AI"}
    </div>
  );
}

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard API unavailable (e.g. insecure context) — fail silently, nothing to recover
    }
  }

  return (
    <button
      onClick={handleCopy}
      title={copied ? "Copied" : "Copy message"}
      className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity text-[var(--text-faint)] hover:text-[var(--foreground)]"
    >
      {copied ? (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 6 9 17l-5-5" />
        </svg>
      ) : (
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  );
}

function MessageMeta({ message }: { message: ChatMessage }) {
  return (
    <div className={`flex items-center gap-2 mt-1 px-1 text-[10.5px] text-[var(--text-faint)] ${message.role === "user" ? "flex-row-reverse" : ""}`}>
      <span>{formatTime(message.timestamp)}</span>
      <CopyButton text={message.content} />
    </div>
  );
}

function TraceRow({ meta }: { meta: NonNullable<ChatMessage["meta"]> }) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--text-faint)]">
      {meta.agent_path.map((agent, i) => (
        <span key={i} className="flex items-center gap-1">
          <span className={`rounded-full px-2 py-0.5 font-medium ${themeFor(agent).badge}`}>{agent}</span>
          {i < meta.agent_path.length - 1 && <span>→</span>}
        </span>
      ))}
      {meta.tools_used.length > 0 && <span className="font-mono">· used {meta.tools_used.join(", ")}</span>}
      {meta.provider_used && <span>· via {meta.provider_used}</span>}
      {meta.intent && (
        <span>
          · intent={meta.intent}
          {meta.sentiment ? `/${meta.sentiment}` : ""}
        </span>
      )}
      {typeof meta.latencyMs === "number" && <span>· {meta.latencyMs}ms</span>}
    </div>
  );
}

function summarizeError(raw: string): string {
  const lower = raw.toLowerCase();
  if (lower.includes("resource_exhausted") || lower.includes("rate limit") || lower.includes("429")) {
    return "The current model provider hit a rate limit. With more than one provider configured, the fallback chain would have automatically tried the next one.";
  }
  if (lower.includes("missing credentials") || lower.includes("api_key") || lower.includes("no llm provider")) {
    return "No model provider is reachable right now — likely a missing or invalid API key in backend/.env.";
  }
  if (lower.includes("unreachable") || lower.includes("connection")) {
    return "Couldn't reach a backing service (database, cache, or model provider).";
  }
  return "Something went wrong handling that message.";
}

function ErrorBubble({ content }: { content: string }) {
  return (
    <div className="rounded-2xl px-4 py-3 text-sm bg-[#faf1e6] text-[#8a5a1f] border border-[#eeddc0]">
      <p>{summarizeError(content)}</p>
      <details className="mt-2">
        <summary className="text-[11px] cursor-pointer opacity-80 hover:underline">Technical details</summary>
        <pre className="mt-1.5 whitespace-pre-wrap break-words text-[10px] font-mono opacity-75 max-h-40 overflow-y-auto thin-scroll">
          {content}
        </pre>
      </details>
    </div>
  );
}

export default function ChatWindow({
  messages,
  sending,
  onSend,
}: {
  messages: ChatMessage[];
  sending: boolean;
  onSend: (text: string) => void;
  customerId: string;
}) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  function submit() {
    const text = input.trim();
    if (!text || sending) return;
    onSend(text);
    setInput("");
  }

  return (
    <div className="card flex flex-1 min-w-0 min-h-0 flex-col rounded-2xl overflow-hidden lg:h-full">
      <div className="thin-scroll flex-1 overflow-y-auto p-6 flex flex-col gap-5 min-h-[500px] lg:min-h-0">
        {messages.map((m) => {
          const lastAgent = m.meta?.agent_path[m.meta.agent_path.length - 1];
          return (
            <div key={m.id} className={`msg-enter group flex gap-3 ${m.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
              <Avatar role={m.role} lastAgent={lastAgent} />
              <div className={`flex flex-col max-w-[75%] ${m.role === "user" ? "items-end" : "items-start"}`}>
                {m.role === "system" ? (
                  <ErrorBubble content={m.content} />
                ) : m.role === "user" ? (
                  <div
                    className="rounded-2xl px-4 py-3 text-[14px] leading-relaxed whitespace-pre-wrap text-white rounded-br-md"
                    style={{ background: "linear-gradient(135deg, var(--brand), var(--brand-strong))" }}
                  >
                    {m.content}
                  </div>
                ) : (
                  <div className="rounded-2xl px-4 py-3 text-[14px] leading-relaxed bg-[var(--surface-muted)] text-[var(--foreground)] rounded-bl-md border border-[var(--border)]">
                    <ReactMarkdown components={MARKDOWN_COMPONENTS}>{m.content}</ReactMarkdown>
                  </div>
                )}
                <MessageMeta message={m} />
                {m.meta && m.meta.agent_path.length > 0 && <TraceRow meta={m.meta} />}
              </div>
            </div>
          );
        })}
        {sending && (
          <div className="msg-enter flex gap-3">
            <div className="h-8 w-8 shrink-0 rounded-full bg-[var(--surface-muted)] border border-[var(--border)]" />
            <div className="rounded-2xl rounded-bl-md bg-[var(--surface-muted)] border border-[var(--border)] px-4 py-3.5 flex items-center gap-1">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-[var(--text-faint)]" style={{ animationDelay: "0s" }} />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-[var(--text-faint)]" style={{ animationDelay: "0.15s" }} />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-[var(--text-faint)]" style={{ animationDelay: "0.3s" }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-[var(--border)] p-4 bg-[var(--surface-muted)]">
        <div className="flex flex-wrap gap-1.5 mb-3">
          {EXAMPLE_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => onSend(p)}
              disabled={sending}
              className="rounded-full border border-[var(--border)] bg-white text-[var(--text-muted)] text-[11.5px] px-3 py-1.5 hover:border-[var(--border-strong)] hover:text-[var(--foreground)] disabled:opacity-50 transition-colors"
            >
              {p}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Ask about an order, return, or policy…"
            className="flex-1 rounded-xl border border-[var(--border-strong)] bg-white px-4 py-3 text-[14px] outline-none focus:ring-2 focus:ring-[var(--brand)]/30 focus:border-[var(--brand)] transition-shadow"
          />
          <button
            onClick={submit}
            disabled={sending || !input.trim()}
            className="rounded-xl px-5 py-3 text-[14px] font-medium text-white disabled:opacity-40 transition-opacity"
            style={{ background: "linear-gradient(135deg, var(--brand), var(--brand-strong))" }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
