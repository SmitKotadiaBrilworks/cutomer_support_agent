import { ChatResponse } from "./api";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: number;
  meta?: Pick<
    ChatResponse,
    "agent_path" | "tools_used" | "provider_used" | "intent" | "sentiment" | "escalated" | "ticket_id"
  > & { latencyMs?: number };
}

export interface TurnStats {
  turns: number;
  escalations: number;
  toolCalls: number;
  avgLatencyMs: number | null;
  providerCounts: Record<string, number>;
  agentCounts: Record<string, number>;
}

export function computeStats(messages: ChatMessage[]): TurnStats {
  const assistantTurns = messages.filter((m) => m.role === "assistant" && m.meta);
  const providerCounts: Record<string, number> = {};
  const agentCounts: Record<string, number> = {};
  let toolCalls = 0;
  let escalations = 0;
  let latencySum = 0;
  let latencyN = 0;

  for (const m of assistantTurns) {
    const meta = m.meta!;
    if (meta.provider_used) providerCounts[meta.provider_used] = (providerCounts[meta.provider_used] || 0) + 1;
    for (const agent of meta.agent_path) agentCounts[agent] = (agentCounts[agent] || 0) + 1;
    toolCalls += meta.tools_used.length;
    if (meta.escalated) escalations += 1;
    if (typeof meta.latencyMs === "number") {
      latencySum += meta.latencyMs;
      latencyN += 1;
    }
  }

  return {
    turns: assistantTurns.length,
    escalations,
    toolCalls,
    avgLatencyMs: latencyN > 0 ? Math.round(latencySum / latencyN) : null,
    providerCounts,
    agentCounts,
  };
}

export const CUSTOMERS = [
  { id: "", label: "Guest (no account)" },
  { id: "CUST-1", label: "CUST-1 — has ORD-1001, ORD-1002" },
  { id: "CUST-2", label: "CUST-2 — has ORD-1003, ORD-1005" },
  { id: "CUST-3", label: "CUST-3 — has ORD-1004" },
];

export const EXAMPLE_PROMPTS = [
  "What's the status of my order ORD-1001?",
  "I want to return ORD-1002, delivered 10 days ago.",
  "Do you ship internationally?",
  "This is the third late delivery in a row, I'm furious.",
  "Can I speak to a human please?",
];
