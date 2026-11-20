// Shared raster layout and canvas drawing for the compact raster and the explorer window.
import type { CircuitData, SimulateResponse } from "../api";
import { CHART_BAND, CHART_GRID, CHART_TEXT, CURSOR, ROLE_ORDER, roleColor } from "../colors";
import { neuronName } from "../format";

export interface RowLayout {
  /** Matrix index of the neuron shown in each row. */
  rowNeuron: number[];
  rowOf: Map<number, number>;
  bands: Array<{ role: string; start: number; end: number }>;
  nRows: number;
}

/** Rows = neurons that spiked at least once, grouped by role, then type, then instance. */
export function layoutRows(data: CircuitData, sim: SimulateResponse): RowLayout {
  const active = new Set<number>(sim.raster_neurons);
  const sorted = Array.from(active).sort((a, b) => {
    const roleDiff = ROLE_ORDER.indexOf(data.roles[a]) - ROLE_ORDER.indexOf(data.roles[b]);
    if (roleDiff !== 0) {
      return roleDiff;
    }
    const typeDiff = data.types[a].localeCompare(data.types[b]);
    if (typeDiff !== 0) {
      return typeDiff;
    }
    const instanceDiff = data.instances[a].localeCompare(data.instances[b]);
    if (instanceDiff !== 0) {
      return instanceDiff;
    }
    return data.body_ids[a] - data.body_ids[b];
  });
  const rowOf = new Map<number, number>();
  const bands: RowLayout["bands"] = [];
  sorted.forEach((neuron, row) => {
    rowOf.set(neuron, row);
    const role = data.roles[neuron];
    const last = bands[bands.length - 1];
    if (last === undefined || last.role !== role) {
      bands.push({ role, start: row, end: row + 1 });
    } else {
      last.end = row + 1;
    }
  });
  return { rowNeuron: sorted, rowOf, bands, nRows: sorted.length };
}

export interface RasterView {
  width: number;
  height: number;
  /** Visible time window (ms). */
  t0: number;
  t1: number;
  /** First visible row (may be fractional) and row height in px. */
  rowStart: number;
  rowHeight: number;
  left: number;
  showRowLabels: boolean;
  currentTime: number | null;
}

export const AXIS_HEIGHT = 20;
export const RIGHT_PAD = 8;

/** First index i with values[i] >= target (values sorted ascending). */
export function lowerBound(values: number[], target: number): number {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (values[mid] < target) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }
  return low;
}

/** A "nice" tick spacing (1, 2 or 5 × 10^k) for roughly `span / target` ticks. */
export function niceStep(span: number, target: number): number {
  const raw = span / Math.max(target, 1);
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  const scaled = raw / power;
  let factor = 10;
  if (scaled <= 1) {
    factor = 1;
  } else if (scaled <= 2) {
    factor = 2;
  } else if (scaled <= 5) {
    factor = 5;
  }
  return factor * power;
}

export function plotWidthOf(view: RasterView): number {
  return Math.max(view.width - view.left - RIGHT_PAD, 10);
}

export function timeToX(view: RasterView, t: number): number {
  return view.left + ((t - view.t0) / (view.t1 - view.t0)) * plotWidthOf(view);
}

export function xToTime(view: RasterView, x: number): number {
  return view.t0 + ((x - view.left) / plotWidthOf(view)) * (view.t1 - view.t0);
}

export function yToRow(view: RasterView, y: number): number {
  return Math.floor(view.rowStart + y / view.rowHeight);
}

function rowLabel(data: CircuitData, neuron: number): string {
  return neuronName(data.instances[neuron], data.types[neuron], data.body_ids[neuron]);
}

/** Draw the raster for `view` into a canvas context already scaled to CSS pixels. */
export function drawRaster(
  ctx: CanvasRenderingContext2D,
  data: CircuitData,
  sim: SimulateResponse,
  layout: RowLayout,
  view: RasterView,
): void {
  const plotHeight = view.height - AXIS_HEIGHT;
  const plotWidth = plotWidthOf(view);
  ctx.clearRect(0, 0, view.width, view.height);
  ctx.font = "11px system-ui";

  const rowTop = (row: number) => (row - view.rowStart) * view.rowHeight;
  const firstRow = Math.max(0, Math.floor(view.rowStart));
  const lastRow = Math.min(layout.nRows, Math.ceil(view.rowStart + plotHeight / view.rowHeight));
  const labelRows = view.showRowLabels && view.rowHeight >= 9;

  ctx.save();
  ctx.beginPath();
  ctx.rect(0, 0, view.width, plotHeight);
  ctx.clip();

  for (const band of layout.bands) {
    if (band.end <= firstRow || band.start >= lastRow) {
      continue;
    }
    const top = rowTop(band.start);
    const bandHeight = (band.end - band.start) * view.rowHeight;
    ctx.fillStyle = CHART_BAND;
    ctx.fillRect(view.left, top, plotWidth, bandHeight);
    ctx.fillStyle = roleColor(band.role);
    ctx.fillRect(view.left - 6, top, 4, bandHeight);
    if (!labelRows) {
      const visibleTop = Math.max(top, 0);
      const visibleBottom = Math.min(top + bandHeight, plotHeight);
      ctx.textAlign = "right";
      ctx.fillText(
        `${band.role} (${band.end - band.start})`,
        view.left - 10,
        Math.min((visibleTop + visibleBottom) / 2 + 4, visibleBottom),
      );
    }
  }

  if (labelRows) {
    ctx.textAlign = "right";
    for (let row = firstRow; row < lastRow; row += 1) {
      const neuron = layout.rowNeuron[row];
      ctx.fillStyle = roleColor(data.roles[neuron]);
      ctx.fillText(rowLabel(data, neuron), view.left - 10, rowTop(row) + view.rowHeight / 2 + 4);
      if (view.rowHeight >= 14) {
        ctx.fillStyle = CHART_GRID;
        ctx.fillRect(view.left, rowTop(row + 1), plotWidth, 1);
      }
    }
  }

  ctx.beginPath();
  ctx.rect(view.left, 0, plotWidth, plotHeight);
  ctx.clip();
  const pxPerMs = plotWidth / (view.t1 - view.t0);
  const markWidth = Math.min(Math.max(1, pxPerMs * 0.3), 4);
  const markHeight = Math.max(1, Math.min(view.rowHeight * 0.8, view.rowHeight - 1, 14));
  const startIndex = lowerBound(sim.raster_times_ms, view.t0 - 1);
  const endIndex = lowerBound(sim.raster_times_ms, view.t1 + 1);
  for (let i = startIndex; i < endIndex; i += 1) {
    const neuron = sim.raster_neurons[i];
    const row = layout.rowOf.get(neuron);
    if (row === undefined || row < firstRow || row >= lastRow) {
      continue;
    }
    ctx.fillStyle = roleColor(data.roles[neuron]);
    const top = rowTop(row) + (view.rowHeight - markHeight) / 2;
    ctx.fillRect(timeToX(view, sim.raster_times_ms[i]) - markWidth / 2, top, markWidth, markHeight);
  }
  ctx.restore();

  ctx.fillStyle = CHART_TEXT;
  ctx.textAlign = "center";
  const step = niceStep(view.t1 - view.t0, Math.max(plotWidth / 90, 2));
  const firstTick = Math.ceil(view.t0 / step) * step;
  let digits = 0;
  if (step < 1) {
    digits = Math.min(2, Math.ceil(-Math.log10(step)));
  }
  for (let t = firstTick; t <= view.t1 + 1e-9; t += step) {
    const x = timeToX(view, t);
    ctx.fillStyle = CHART_GRID;
    ctx.fillRect(x, plotHeight, 1, 4);
    ctx.fillStyle = CHART_TEXT;
    const label = t.toFixed(digits);
    const halfWidth = ctx.measureText(label).width / 2;
    if (x + halfWidth > view.width) {
      ctx.textAlign = "right";
      ctx.fillText(label, view.width - 1, view.height - 4);
      ctx.textAlign = "center";
    } else {
      ctx.fillText(label, x, view.height - 4);
    }
  }

  if (view.currentTime !== null && view.currentTime >= view.t0 && view.currentTime <= view.t1) {
    const x = timeToX(view, view.currentTime);
    ctx.strokeStyle = CURSOR;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, plotHeight);
    ctx.stroke();
  }
}

/** Size a canvas for its CSS box and return a context scaled to CSS pixels. */
export function prepareCanvas(
  canvas: HTMLCanvasElement,
  width: number,
  height: number,
): CanvasRenderingContext2D | null {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  if (ctx === null) {
    return null;
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return ctx;
}
