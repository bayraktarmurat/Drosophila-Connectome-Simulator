// Shared colour helpers (dark grey theme). Role colours are used by the graph, raster and charts.

export const ROLE_COLORS: Record<string, string> = {
  input: "#60a5fa",
  hub: "#f87171",
  output: "#4ade80",
  interneuron: "#9ca3af",
};

export const ROLE_ORDER = ["input", "interneuron", "hub", "output"];

export const EDGE_EXCITATORY = "rgba(203, 213, 225, 0.16)";
export const EDGE_INHIBITORY = "rgba(248, 113, 113, 0.2)";
export const EDGE_MODULATORY = "rgba(250, 204, 21, 0.24)";
export const EDGE_ELECTRICAL = "rgba(192, 132, 252, 0.95)";
export const HIGHLIGHT = "#fb923c";
export const GLOW = "#fde047";
export const DIMMED = "#3a3d44";
export const ABLATED = "#f4f4f5";

export const LABEL_COLOR = "#e5e7eb";
export const LABEL_BACKDROP = "#2b2e34";

/** Colours for canvas-drawn charts (raster, uPlot), which cannot read CSS variables. */
export const CHART_TEXT = "#c4c8cf";
export const CHART_GRID = "rgba(255, 255, 255, 0.08)";
export const CHART_BAND = "rgba(255, 255, 255, 0.035)";
export const CURSOR = "#fb923c";

export const SERIES_PALETTE = [
  "#60a5fa",
  "#f87171",
  "#4ade80",
  "#c084fc",
  "#fb923c",
  "#22d3ee",
  "#f472b6",
  "#a3e635",
  "#a78bfa",
  "#fbbf24",
];

export function roleColor(role: string): string {
  const color = ROLE_COLORS[role];
  if (color === undefined) {
    return "#9ca3af";
  }
  return color;
}

/** Stable colour per cell-type name (hash -> hue). */
export function typeColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) | 0;
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 70%, 62%)`;
}

export function seriesColor(index: number): string {
  return SERIES_PALETTE[index % SERIES_PALETTE.length];
}

export function edgeColor(sign: number): string {
  if (sign > 0) {
    return EDGE_EXCITATORY;
  }
  if (sign < 0) {
    return EDGE_INHIBITORY;
  }
  return EDGE_MODULATORY;
}
