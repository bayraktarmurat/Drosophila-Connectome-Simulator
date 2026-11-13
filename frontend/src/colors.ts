// Shared colour helpers. Role colours are used by the graph, raster and legends.

export const ROLE_COLORS: Record<string, string> = {
  input: "#2563eb",
  hub: "#dc2626",
  output: "#16a34a",
  interneuron: "#94a3b8",
};

export const ROLE_ORDER = ["input", "interneuron", "hub", "output"];

export const EDGE_EXCITATORY = "rgba(71, 85, 105, 0.18)";
export const EDGE_INHIBITORY = "rgba(220, 38, 38, 0.22)";
export const EDGE_MODULATORY = "rgba(202, 138, 4, 0.22)";
export const EDGE_ELECTRICAL = "rgba(147, 51, 234, 0.9)";
export const HIGHLIGHT = "#f97316";
export const GLOW = "#facc15";
export const DIMMED = "#e2e8f0";
export const ABLATED = "#111827";

export const SERIES_PALETTE = [
  "#2563eb",
  "#dc2626",
  "#16a34a",
  "#9333ea",
  "#ea580c",
  "#0891b2",
  "#be185d",
  "#4d7c0f",
  "#7c3aed",
  "#b45309",
];

export function roleColor(role: string): string {
  const color = ROLE_COLORS[role];
  if (color === undefined) {
    return "#64748b";
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
  return `hsl(${hue}, 65%, 50%)`;
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
