import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CircuitData, SimulateResponse } from "../api";
import { GLOW } from "../colors";
import { neuronName, signLabel } from "../format";
import {
  AXIS_HEIGHT,
  drawRaster,
  layoutRows,
  lowerBound,
  prepareCanvas,
  xToTime,
  yToRow,
} from "./rasterDraw";
import type { RasterView } from "./rasterDraw";

interface RasterExplorerProps {
  data: CircuitData;
  sim: SimulateResponse;
  currentTime: number;
  onTimeClick: (timeMs: number) => void;
  onSelectNeuron: (index: number) => void;
}

interface Viewport {
  t0: number;
  t1: number;
  rowStart: number;
}

interface HoverInfo {
  x: number;
  y: number;
  neuron: number;
  time: number;
  nearestSpike: number | null;
}

const LEFT = 200;
const MIN_SPAN_MS = 2;
const DRAG_THRESHOLD_PX = 4;

/** Spike time of `neuron` closest to `time` within `toleranceMs`, or null. */
function nearestSpike(
  sim: SimulateResponse,
  neuron: number,
  time: number,
  toleranceMs: number,
): number | null {
  const start = lowerBound(sim.raster_times_ms, time - toleranceMs);
  const end = lowerBound(sim.raster_times_ms, time + toleranceMs);
  let best: number | null = null;
  let bestDistance = Infinity;
  for (let i = start; i < end; i += 1) {
    if (sim.raster_neurons[i] !== neuron) {
      continue;
    }
    const distance = Math.abs(sim.raster_times_ms[i] - time);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = sim.raster_times_ms[i];
    }
  }
  return best;
}

/**
 * Large, navigable raster: wheel scrolls neurons, ctrl/⌘ + wheel (or pinch) zooms time,
 * shift + wheel pans time, drag pans both. One labelled row per neuron when rows are tall enough.
 */
export default function RasterExplorer(props: RasterExplorerProps) {
  const { data, sim } = props;
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const layout = useMemo(() => layoutRows(data, sim), [data, sim]);
  const [size, setSize] = useState({ width: 800, height: 500 });
  const [rowHeight, setRowHeight] = useState(12);
  const [viewport, setViewport] = useState<Viewport>({ t0: 0, t1: sim.duration_ms, rowStart: 0 });
  const [hover, setHover] = useState<HoverInfo | null>(null);
  const [jumpText, setJumpText] = useState("");
  const [jumpedRow, setJumpedRow] = useState<number | null>(null);
  const dragRef = useRef<{ x: number; y: number; start: Viewport; moved: boolean } | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (wrapper === null) {
      return;
    }
    const observer = new ResizeObserver(() => {
      setSize({ width: Math.max(wrapper.clientWidth, 300), height: Math.max(wrapper.clientHeight, 200) });
    });
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, []);

  const visibleRows = (size.height - AXIS_HEIGHT) / rowHeight;
  const maxRowStart = Math.max(0, layout.nRows - visibleRows);

  /** Keep the window inside the run and the row offset inside the table. */
  const clampViewport = useCallback(
    (next: Viewport): Viewport => {
      let span = Math.max(next.t1 - next.t0, MIN_SPAN_MS);
      span = Math.min(span, sim.duration_ms);
      let t0 = next.t0;
      if (t0 < 0) {
        t0 = 0;
      }
      if (t0 + span > sim.duration_ms) {
        t0 = sim.duration_ms - span;
      }
      const rowStart = Math.min(Math.max(next.rowStart, 0), maxRowStart);
      return { t0, t1: t0 + span, rowStart };
    },
    [sim.duration_ms, maxRowStart],
  );

  const view: RasterView = useMemo(
    () => ({
      width: size.width,
      height: size.height,
      t0: viewport.t0,
      t1: viewport.t1,
      rowStart: Math.min(viewport.rowStart, maxRowStart),
      rowHeight,
      left: LEFT,
      showRowLabels: true,
      currentTime: props.currentTime,
    }),
    [size, viewport, rowHeight, props.currentTime, maxRowStart],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    const ctx = prepareCanvas(canvas, view.width, view.height);
    if (ctx === null) {
      return;
    }
    drawRaster(ctx, data, sim, layout, view);
    if (jumpedRow !== null) {
      const top = (jumpedRow - view.rowStart) * view.rowHeight;
      ctx.strokeStyle = GLOW;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(1, top, view.width - 2, view.rowHeight);
    }
  }, [view, layout, data, sim, jumpedRow]);

  // Wheel needs a non-passive listener so the page does not scroll or zoom.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      setViewport((current) => {
        const span = current.t1 - current.t0;
        if (event.ctrlKey || event.metaKey) {
          const factor = Math.exp(event.deltaY * 0.01);
          const plotWidth = Math.max(rect.width - LEFT - 8, 10);
          const fraction = Math.min(Math.max((x - LEFT) / plotWidth, 0), 1);
          const anchor = current.t0 + fraction * span;
          const nextSpan = span * factor;
          return clampViewport({
            t0: anchor - fraction * nextSpan,
            t1: anchor + (1 - fraction) * nextSpan,
            rowStart: current.rowStart,
          });
        }
        let horizontal = event.deltaX;
        let vertical = event.deltaY;
        if (event.shiftKey && horizontal === 0) {
          horizontal = vertical;
          vertical = 0;
        }
        const plotWidth = Math.max(rect.width - LEFT - 8, 10);
        const shift = (horizontal / plotWidth) * span;
        return clampViewport({
          t0: current.t0 + shift,
          t1: current.t1 + shift,
          rowStart: current.rowStart + vertical / rowHeight,
        });
      });
    };
    canvas.addEventListener("wheel", handleWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", handleWheel);
  }, [clampViewport, rowHeight]);

  const zoomTime = (factor: number) => {
    setViewport((current) => {
      const center = (current.t0 + current.t1) / 2;
      const span = (current.t1 - current.t0) * factor;
      return clampViewport({ t0: center - span / 2, t1: center + span / 2, rowStart: current.rowStart });
    });
  };

  const reset = () => {
    setViewport({ t0: 0, t1: sim.duration_ms, rowStart: 0 });
    setJumpedRow(null);
  };

  const fitRows = () => {
    const fitted = Math.max((size.height - AXIS_HEIGHT) / Math.max(layout.nRows, 1), 0.5);
    setRowHeight(Math.min(fitted, 24));
    setViewport((current) => ({ ...current, rowStart: 0 }));
  };

  const pointerInfo = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const { x, y } = pointerInfo(event);
    dragRef.current = { x, y, start: viewport, moved: false };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const { x, y } = pointerInfo(event);
    const drag = dragRef.current;
    if (drag !== null) {
      const dx = x - drag.x;
      const dy = y - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) {
        drag.moved = true;
        setDragging(true);
      }
      if (drag.moved) {
        const span = drag.start.t1 - drag.start.t0;
        const plotWidth = Math.max(size.width - LEFT - 8, 10);
        const shift = (-dx / plotWidth) * span;
        setViewport(
          clampViewport({
            t0: drag.start.t0 + shift,
            t1: drag.start.t1 + shift,
            rowStart: drag.start.rowStart - dy / rowHeight,
          }),
        );
        setHover(null);
        return;
      }
    }
    const row = yToRow(view, y);
    if (y > size.height - AXIS_HEIGHT || row < 0 || row >= layout.nRows) {
      setHover(null);
      return;
    }
    const neuron = layout.rowNeuron[row];
    const time = xToTime(view, x);
    const pxPerMs = (size.width - LEFT - 8) / (view.t1 - view.t0);
    const tolerance = Math.max(6 / pxPerMs, sim.dt_ms);
    setHover({ x, y, neuron, time, nearestSpike: nearestSpike(sim, neuron, time, tolerance) });
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const drag = dragRef.current;
    dragRef.current = null;
    setDragging(false);
    if (drag === null || drag.moved) {
      return;
    }
    const { x } = pointerInfo(event);
    if (x < LEFT) {
      return;
    }
    const time = xToTime(view, x);
    if (time >= 0 && time <= sim.duration_ms) {
      props.onTimeClick(time);
    }
  };

  const handleDoubleClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const row = yToRow(view, event.clientY - rect.top);
    if (row >= 0 && row < layout.nRows) {
      props.onSelectNeuron(layout.rowNeuron[row]);
    }
  };

  const rowNames = useMemo(
    () => layout.rowNeuron.map((n) => neuronName(data.instances[n], data.types[n], data.body_ids[n])),
    [layout, data],
  );

  const jump = () => {
    const query = jumpText.trim().toLowerCase();
    if (query.length === 0) {
      return;
    }
    let found = rowNames.findIndex((name) => name.toLowerCase() === query);
    if (found < 0) {
      found = rowNames.findIndex((name) => name.toLowerCase().includes(query));
    }
    if (found < 0) {
      setJumpedRow(null);
      return;
    }
    let height = rowHeight;
    if (height < 9) {
      height = 12;
      setRowHeight(height);
    }
    const rowsOnScreen = (size.height - AXIS_HEIGHT) / height;
    setJumpedRow(found);
    setViewport((current) => ({
      ...current,
      rowStart: Math.min(Math.max(found - rowsOnScreen / 2, 0), Math.max(0, layout.nRows - rowsOnScreen)),
    }));
  };

  let tooltip = null;
  if (hover !== null) {
    const n = hover.neuron;
    let spikeText = `t = ${hover.time.toFixed(1)} ms`;
    if (hover.nearestSpike !== null) {
      spikeText = `spike at ${hover.nearestSpike.toFixed(1)} ms`;
    }
    let left = hover.x + 14;
    if (left > size.width - 260) {
      left = hover.x - 260;
    }
    tooltip = (
      <div className="raster-tooltip" style={{ left, top: hover.y + 12 }}>
        <strong>{rowNames[layout.rowOf.get(n) as number]}</strong> · {data.types[n]} · {data.roles[n]}
        <br />
        {data.nts[n]} ({signLabel(data.signs[n])}) · {spikeText}
      </div>
    );
  }

  let canvasClass = "";
  if (dragging) {
    canvasClass = "dragging";
  }
  const listId = "raster-explorer-rows";

  return (
    <>
      <div className="modal-tools">
        <button onClick={() => zoomTime(0.5)}>zoom in</button>
        <button onClick={() => zoomTime(2)}>zoom out</button>
        <button onClick={reset}>reset</button>
        <label className="field-inline">
          row height
          <input
            type="range"
            min={1}
            max={24}
            step={1}
            value={Math.round(rowHeight)}
            onChange={(e) => setRowHeight(Number(e.target.value))}
          />
        </label>
        <button onClick={fitRows}>fit all rows</button>
        <input
          list={listId}
          placeholder="jump to neuron (e.g. GNG132_L)"
          value={jumpText}
          onChange={(e) => setJumpText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              jump();
            }
          }}
        />
        <datalist id={listId}>
          {rowNames.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
        <button onClick={jump}>jump</button>
        <span className="muted small">
          {layout.nRows} active neurons · {viewport.t0.toFixed(1)}–{viewport.t1.toFixed(1)} ms
        </span>
      </div>
      <p className="hint">
        Scroll: move through neurons · ⌘/Ctrl + scroll or pinch: zoom time · Shift + scroll: move in time ·
        Drag: pan · Click: set playback time · Double-click a row: open that neuron.
      </p>
      <div className="explorer-canvas-wrap" ref={wrapperRef}>
        <canvas
          ref={canvasRef}
          className={canvasClass}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={() => setHover(null)}
          onDoubleClick={handleDoubleClick}
        />
        {tooltip}
      </div>
    </>
  );
}
