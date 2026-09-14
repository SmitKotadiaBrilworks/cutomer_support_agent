export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AgentInfo {
  id: string;
  name: string;
  role: string;
  tools?: string[];
}

export interface HealthResponse {
  status: string;
  configured_providers: string[];
  store_backend?: "memory" | "postgres";
  postgres?: string;
  redis?: string;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
  escalated: boolean;
  ticket_id: string | null;
  provider_used: string | null;
  agent_path: string[];
  current_agent: string | null;
  tools_used: string[];
  intent: string | null;
  sentiment: string | null;
}

export class ApiError extends Error {}

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_URL}/health`);
  if (!res.ok) throw new ApiError(`health check failed: ${res.status}`);
  return res.json();
}

export async function getAgents(): Promise<{ agents: AgentInfo[] }> {
  const res = await fetch(`${API_URL}/agents`);
  if (!res.ok) throw new ApiError(`could not load agent roster: ${res.status}`);
  return res.json();
}

export async function sendChat(
  sessionId: string,
  message: string,
  customerId: string | null
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message, customer_id: customerId }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new ApiError(data.detail || `chat request failed: ${res.status}`);
  }
  return data;
}
