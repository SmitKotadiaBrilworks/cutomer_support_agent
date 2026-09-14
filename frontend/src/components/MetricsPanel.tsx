"use client";

import { TurnStats } from "@/lib/types";
import { PROVIDER_HEX } from "@/lib/agentTheme";

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Claude",
  google: "Gemini",
};

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-[var(--surface-muted)] border border-[var(--border)] px-3.5 py-3">
      <div className="text-xl font-semibold tabular-nums leading-tight text-[var(--foreground)]">{value}</div>
      <div className="text-[10.5px] uppercase tracking-wide text-[var(--text-faint)] mt-1">{label}</div>
    </div>
  );
}

export default function MetricsPanel({ stats }: { stats: TurnStats }) {
  const providerEntries = Object.entries(stats.providerCounts);
  const providerTotal = providerEntries.reduce((sum, [, n]) => sum + n, 0);

  return (
    <section className="card rounded-2xl p-5">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-faint)] mb-3">Session metrics</h2>
      <div className="grid grid-cols-2 gap-2.5">
        <StatTile label="Turns" value={String(stats.turns)} />
        <StatTile label="Escalations" value={String(stats.escalations)} />
        <StatTile label="Tool calls" value={String(stats.toolCalls)} />
        <StatTile label="Avg latency" value={stats.avgLatencyMs != null ? `${stats.avgLatencyMs}ms` : "—"} />
      </div>

      {providerTotal > 0 && (
        <div className="mt-4">
          <div className="text-[10.5px] uppercase tracking-wide text-[var(--text-faint)] mb-2">Provider mix</div>
          <div className="flex h-2 w-full overflow-hidden rounded-full bg-[var(--surface-muted)] border border-[var(--border)]">
            {providerEntries.map(([provider, n]) => (
              <div
                key={provider}
                style={{ width: `${(n / providerTotal) * 100}%`, backgroundColor: PROVIDER_HEX[provider] || "#9ca3af" }}
                title={`${PROVIDER_LABELS[provider] || provider}: ${n}`}
              />
            ))}
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
            {providerEntries.map(([provider, n]) => (
              <span key={provider} className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: PROVIDER_HEX[provider] || "#9ca3af" }} />
                {PROVIDER_LABELS[provider] || provider} ({n})
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
