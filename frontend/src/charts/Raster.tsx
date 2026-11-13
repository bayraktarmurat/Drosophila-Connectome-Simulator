import { useEffect, useMemo, useRef } from "react";
import type { CircuitData, SimulateResponse } from "../api";
import { ROLE_ORDER, roleColor } from "../colors";

interface RasterProps {
  data: CircuitData;
  sim: SimulateResponse;
  currentTime: number | null;
  onTimeClick: (timeMs: number) => void;
  height?: number;
}

interface RowLayout {
  rowOf: Map<number, number>;
  bands: Array<{ role: string; start: number; end: number }>;
  nRows: number;
}

/** Rows = neurons that spiked at least once, grouped by role, then by type. */
function layoutRows(data: CircuitData, sim: SimulateResponse): RowLayout {
  const active = new Set<number>(sim.raster_neurons);
  const sorted = Array.from(active).sort((a, b) => {
    const roleDiff = ROLE_ORDER.indexOf(data.roles[a]) - ROLE_ORDER.indexOf(data.roles[b]);
    if (roleDiff !== 0) {
      return roleDiff;
    }
    return data.types[a].localeCompare(data.types[b]);
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
  return { rowOf, bands, nRows: sorted.length };
}

const LEFT = 120;

export default function Raster(props: RasterProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const layout = useMemo(() => layoutRows(props.data, props.sim), [props.data, props.sim]);
  let height = 260;
  if (props.height !== undefined) {
    height = props.height;
  }

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    let width = 600;
    if (canvas.parentElement !== null) {
      width = canvas.parentElement.clientWidth;
    }
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const ctx = canvas.getContext("2d");
    if (ctx === null) {
      return;
    }
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, height);
    const plotWidth = width - LEFT - 8;
    const rows = Math.max(layout.nRows, 1);
    const rowHeight = (height - 20) / rows;
    const xOf = (t: number) => LEFT + (t / props.sim.duration_ms) * plotWidth;

    for (const band of layout.bands) {
      const top = band.start * rowHeight;
      const bandHeight = (band.end - band.start) * rowHeight;
      ctx.fillStyle = "rgba(148, 163, 184, 0.08)";
      ctx.fillRect(LEFT, top, plotWidth, bandHeight);
      ctx.fillStyle = roleColor(band.role);
      ctx.fillRect(LEFT - 6, top, 4, bandHeight);
      ctx.font = "11px system-ui";
      ctx.textAlign = "right";
      ctx.fillText(`${band.role} (${band.end - band.start})`, LEFT - 10, top + Math.min(bandHeight / 2 + 4, bandHeight));
    }

    const dot = Math.max(1, Math.min(rowHeight, 3));
    for (let i = 0; i < props.sim.raster_times_ms.length; i += 1) {
      const neuron = props.sim.raster_neurons[i];
      const row = layout.rowOf.get(neuron);
      if (row === undefined) {
        continue;
      }
      ctx.fillStyle = roleColor(props.data.roles[neuron]);
      ctx.fillRect(xOf(props.sim.raster_times_ms[i]), row * rowHeight, 1, dot);
    }

    ctx.fillStyle = "#475569";
    ctx.textAlign = "center";
    for (let t = 0; t <= props.sim.duration_ms; t += Math.max(50, Math.round(props.sim.duration_ms / 10 / 50) * 50)) {
      ctx.fillText(`${t}`, xOf(t), height - 4);
    }
    if (props.currentTime !== null) {
      ctx.strokeStyle = "#f97316";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(xOf(props.currentTime), 0);
      ctx.lineTo(xOf(props.currentTime), height - 18);
      ctx.stroke();
    }
  }, [layout, props.sim, props.data, props.currentTime, height]);

  const handleClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const plotWidth = rect.width - LEFT - 8;
    const fraction = (event.clientX - rect.left - LEFT) / plotWidth;
    if (fraction < 0 || fraction > 1) {
      return;
    }
    props.onTimeClick(fraction * props.sim.duration_ms);
  };

  return (
    <div className="raster">
      <canvas ref={canvasRef} onClick={handleClick} />
    </div>
  );
}
