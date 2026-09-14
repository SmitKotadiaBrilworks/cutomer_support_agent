"use client";

import { themeFor } from "@/lib/agentTheme";

type NodeId = "triage" | "orderReturns" | "faq" | "tools" | "escalation";

const NODE_LABEL: Record<NodeId, string> = {
  triage: "Triage Agent",
  orderReturns: "Order & Returns Agent",
  faq: "FAQ / Knowledge Agent",
  tools: "Tools",
  escalation: "Escalation Agent",
};

const NODE_SUB: Record<NodeId, string> = {
  triage: "classify + route",
  orderReturns: "order status · returns",
  faq: "policy · shipping · FAQ",
  tools: "get_order_status · search_faq …",
  escalation: "draft + file ticket",
};

const NODE_RECT: Record<NodeId, { x: number; y: number; w: number; h: number }> = {
  triage: { x: 165, y: 10, w: 130, h: 46 },
  orderReturns: { x: 15, y: 112, w: 165, h: 52 },
  faq: { x: 280, y: 112, w: 165, h: 52 },
  tools: { x: 165, y: 208, w: 130, h: 40 },
  escalation: { x: 165, y: 268, w: 130, h: 44 },
};

function center(id: NodeId) {
  const r = NODE_RECT[id];
  return { x: r.x + r.w / 2, y: r.y + r.h / 2 };
}

interface Edge {
  id: string;
  from: NodeId;
  to: NodeId;
  d: string;
  dashed?: boolean;
}

const EDGES: Edge[] = [
  { id: "e1", from: "triage", to: "orderReturns", d: "M 200 56 C 170 80, 110 90, 97 112" },
  { id: "e2", from: "triage", to: "faq", d: "M 260 56 C 300 80, 360 90, 362 112" },
  { id: "e3", from: "triage", to: "escalation", dashed: true, d: "M 295 40 C 400 70, 400 230, 232 278" },
  { id: "e4", from: "orderReturns", to: "tools", d: "M 110 164 C 130 185, 155 195, 190 210" },
  { id: "e5", from: "faq", to: "tools", d: "M 350 164 C 330 185, 305 195, 270 210" },
  { id: "e6", from: "orderReturns", to: "escalation", dashed: true, d: "M 105 164 C 90 220, 130 255, 172 280" },
  { id: "e7", from: "faq", to: "escalation", dashed: true, d: "M 355 164 C 370 220, 330 255, 288 280" },
];

export default function AgentFlowDiagram({
  agentPath,
  toolsUsed,
  turnKey,
}: {
  agentPath: string[];
  toolsUsed: string[];
  turnKey: string;
}) {
  const has = (label: string) => agentPath.includes(label);
  const hasOrderReturns = has(NODE_LABEL.orderReturns);
  const hasFaq = has(NODE_LABEL.faq);
  const hasEscalation = has(NODE_LABEL.escalation);
  const toolsActive = toolsUsed.length > 0;
  const directEscalation = hasEscalation && agentPath[1] === NODE_LABEL.escalation;

  const activeNodes = new Set<NodeId>();
  if (agentPath.length > 0) activeNodes.add("triage");
  if (hasOrderReturns) activeNodes.add("orderReturns");
  if (hasFaq) activeNodes.add("faq");
  if (toolsActive) activeNodes.add("tools");
  if (hasEscalation) activeNodes.add("escalation");

  const activeEdgeIds = new Set<string>();
  if (hasOrderReturns) activeEdgeIds.add("e1");
  if (hasFaq) activeEdgeIds.add("e2");
  if (directEscalation) activeEdgeIds.add("e3");
  if (hasOrderReturns && toolsActive) activeEdgeIds.add("e4");
  if (hasFaq && toolsActive) activeEdgeIds.add("e5");
  if (hasOrderReturns && hasEscalation && !directEscalation) activeEdgeIds.add("e6");
  if (hasFaq && hasEscalation && !directEscalation) activeEdgeIds.add("e7");

  return (
    <div className="card rounded-2xl p-4">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-faint)] mb-2 px-1">
        Live agent graph
      </h2>
      <svg viewBox="0 0 460 320" className="w-full h-auto" role="img" aria-label="Agent workflow diagram">
        <g className="stroke-[rgba(28,28,26,0.38)]" fill="none" strokeWidth={1.75}>
          {EDGES.map((e) => (
            <path key={e.id} d={e.d} strokeDasharray={e.dashed ? "4 4" : undefined} />
          ))}
        </g>

        <g key={turnKey} fill="none" strokeLinecap="round">
          {EDGES.filter((e) => activeEdgeIds.has(e.id)).map((e) => (
            <path
              key={e.id}
              d={e.d}
              strokeDasharray="7 5"
              strokeWidth={2.5}
              className={`${themeFor(NODE_LABEL[e.to]).stroke} agent-edge-flow`}
            />
          ))}
        </g>

        {(Object.keys(NODE_RECT) as NodeId[]).map((id) => {
          const r = NODE_RECT[id];
          const active = activeNodes.has(id);
          const theme = themeFor(NODE_LABEL[id]);
          const c = center(id);
          return (
            <g key={`${id}-${turnKey}`} className={active ? "agent-node-active" : undefined}>
              <rect
                x={r.x}
                y={r.y}
                width={r.w}
                height={r.h}
                rx={10}
                className={active ? `${theme.svgFill} ${theme.svgStroke}` : "fill-white stroke-[rgba(28,28,26,0.38)]"}
                strokeWidth={active ? 1.75 : 1.25}
              />
              <text
                x={c.x}
                y={id === "tools" ? c.y - 3 : c.y - 6}
                textAnchor="middle"
                className={`text-[10.5px] font-semibold ${active ? theme.svgText : "fill-[var(--foreground)]"}`}
              >
                {NODE_LABEL[id]}
              </text>
              <text
                x={c.x}
                y={id === "tools" ? c.y + 11 : c.y + 10}
                textAnchor="middle"
                className={`text-[8.5px] ${active ? theme.svgTextMuted : "fill-[var(--text-muted)]"}`}
              >
                {NODE_SUB[id]}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="px-1 text-[10.5px] text-[var(--text-muted)] mt-1.5 leading-relaxed">
        Dashed edges = conditional routing (complaint/escalation intent, or sentiment still negative after a
        specialist replies).
      </p>
    </div>
  );
}
