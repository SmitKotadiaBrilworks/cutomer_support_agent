export interface AgentTheme {
  dot: string;
  badge: string;
  ring: string;
  /** Tailwind classes for SVG node fill/stroke/text in AgentFlowDiagram */
  svgFill: string;
  svgStroke: string;
  svgText: string;
  svgTextMuted: string;
  /** Tailwind stroke class for animated edges in AgentFlowDiagram */
  stroke: string;
  /** Raw hex, for contexts where a Tailwind class can't be used (glow filter, charts) */
  hex: string;
}

// A deliberately restrained, editorial palette — muted rather than stock
// Tailwind primaries — so four simultaneous accent colors read as "designed
// system" instead of "every badge got a random bright color."
const THEMES: Record<string, AgentTheme> = {
  "Triage Agent": {
    dot: "bg-[#8c8a7f]",
    badge: "bg-[#f1f0ee] text-[#57564f]",
    ring: "ring-[#8c8a7f]",
    svgFill: "fill-[#f1f0ee]",
    svgStroke: "stroke-[#8c8a7f]",
    svgText: "fill-[#57564f]",
    svgTextMuted: "fill-[#8c8a7f]",
    stroke: "stroke-[#8c8a7f]",
    hex: "#8c8a7f",
  },
  "Order & Returns Agent": {
    dot: "bg-[#3f7fa0]",
    badge: "bg-[#eaf1f5] text-[#2b5770]",
    ring: "ring-[#3f7fa0]",
    svgFill: "fill-[#eaf1f5]",
    svgStroke: "stroke-[#3f7fa0]",
    svgText: "fill-[#2b5770]",
    svgTextMuted: "fill-[#3f7fa0]",
    stroke: "stroke-[#3f7fa0]",
    hex: "#3f7fa0",
  },
  "FAQ / Knowledge Agent": {
    dot: "bg-[#7d67b8]",
    badge: "bg-[#f1eef8] text-[#5b4b8a]",
    ring: "ring-[#7d67b8]",
    svgFill: "fill-[#f1eef8]",
    svgStroke: "stroke-[#7d67b8]",
    svgText: "fill-[#5b4b8a]",
    svgTextMuted: "fill-[#7d67b8]",
    stroke: "stroke-[#7d67b8]",
    hex: "#7d67b8",
  },
  "Escalation Agent": {
    dot: "bg-[#c17f2e]",
    badge: "bg-[#faf1e6] text-[#8a5a1f]",
    ring: "ring-[#c17f2e]",
    svgFill: "fill-[#faf1e6]",
    svgStroke: "stroke-[#c17f2e]",
    svgText: "fill-[#8a5a1f]",
    svgTextMuted: "fill-[#c17f2e]",
    stroke: "stroke-[#c17f2e]",
    hex: "#c17f2e",
  },
  Tools: {
    dot: "bg-[#5a9270]",
    badge: "bg-[#eef4ef] text-[#3f6b4f]",
    ring: "ring-[#5a9270]",
    svgFill: "fill-[#eef4ef]",
    svgStroke: "stroke-[#5a9270]",
    svgText: "fill-[#3f6b4f]",
    svgTextMuted: "fill-[#5a9270]",
    stroke: "stroke-[#5a9270]",
    hex: "#5a9270",
  },
};

const DEFAULT_THEME: AgentTheme = {
  dot: "bg-gray-400",
  badge: "bg-gray-100 text-gray-600",
  ring: "ring-gray-400",
  svgFill: "fill-gray-50",
  svgStroke: "stroke-gray-400",
  svgText: "fill-gray-600",
  svgTextMuted: "fill-gray-400",
  stroke: "stroke-gray-400",
  hex: "#9ca3af",
};

export function themeFor(agentName: string | null | undefined): AgentTheme {
  if (!agentName) return DEFAULT_THEME;
  return THEMES[agentName] ?? DEFAULT_THEME;
}

export const PROVIDER_HEX: Record<string, string> = {
  openai: "#5a9270",
  anthropic: "#c17f2e",
  google: "#3f7fa0",
};
