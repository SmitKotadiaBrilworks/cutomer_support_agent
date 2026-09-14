"use client";

import { HealthResponse } from "@/lib/api";
import { TurnStats } from "@/lib/types";
import AgentFlowDiagram from "./AgentFlowDiagram";
import MetricsPanel from "./MetricsPanel";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-faint)] mb-3">
      {children}
    </h2>
  );
}

export default function AgentSidebar({
  activeAgentPath,
  activeTools,
  turnKey,
  stats,
  health,
  lastTicketId,
}: {
  activeAgentPath: string[];
  activeTools: string[];
  turnKey: string;
  stats: TurnStats;
  health: HealthResponse | null;
  lastTicketId: string | null;
}) {
  return (
    <aside className="thin-scroll w-full lg:w-96 shrink-0 flex flex-col gap-5 lg:h-full lg:overflow-y-auto lg:pr-1">
      <AgentFlowDiagram
        agentPath={activeAgentPath}
        toolsUsed={activeTools}
        turnKey={turnKey}
      />

      <MetricsPanel stats={stats} />

      {health?.store_backend && (
        <section className="card rounded-2xl p-5">
          <SectionTitle>Data layer</SectionTitle>
          {health.store_backend === "memory" ? (
            <p className="text-[13px] text-[var(--text-muted)]">
              In-memory mock data — demo mode, no external services.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              <li className="flex items-center gap-2 text-[13px] text-[var(--foreground)]">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${health.postgres === "ok" ? "bg-[#5a9270]" : "bg-red-500"}`}
                />
                <span>Postgres (orders, tickets, users, audit log)</span>
              </li>
              <li className="flex items-center gap-2 text-[13px] text-[var(--foreground)]">
                <span
                  className={`h-1.5 w-1.5 rounded-full ${health.redis === "ok" ? "bg-[#5a9270]" : "bg-red-500"}`}
                />
                <span>Redis (conversation memory)</span>
              </li>
              <li className="text-[11.5px] text-[var(--text-faint)] mt-0.5">
                pgvector semantic FAQ search enabled
              </li>
            </ul>
          )}
        </section>
      )}

      {lastTicketId && (
        <section className="rounded-2xl p-5 border border-[#eeddc0] bg-[#faf1e6]">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-[#8a5a1f] mb-1.5">
            Latest escalation
          </h2>
          <p className="text-[13px] text-[#8a5a1f]">
            Ticket <span className="font-mono">{lastTicketId}</span> filed for
            human follow-up.
          </p>
        </section>
      )}
    </aside>
  );
}
