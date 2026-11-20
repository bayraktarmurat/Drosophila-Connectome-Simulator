import { useEffect, useMemo, useRef, useState } from "react";
import type { CircuitData, SimulateResponse } from "../api";
import { AXIS_HEIGHT, drawRaster, layoutRows, prepareCanvas, xToTime } from "./rasterDraw";
import type { RasterView } from "./rasterDraw";

interface RasterProps {
  data: CircuitData;
  sim: SimulateResponse;
  currentTime: number | null;
  onTimeClick: (timeMs: number) => void;
  height?: number;
}

const LEFT = 120;

/** Compact raster: the whole run and every active neuron squeezed into the panel. */
export default function Raster(props: RasterProps) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const drawRef = useRef<HTMLCanvasElement | null>(null);
  const layout = useMemo(() => layoutRows(props.data, props.sim), [props.data, props.sim]);
  const [width, setWidth] = useState(600);
  let height = 260;
  if (props.height !== undefined) {
    height = props.height;
  }

  // Follow the panel width (the side panel can be resized).
  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (wrapper === null) {
      return;
    }
    const observer = new ResizeObserver(() => {
      setWidth(Math.max(wrapper.clientWidth, 200));
    });
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, []);

  const view: RasterView = useMemo(
    () => ({
      width,
      height,
      t0: 0,
      t1: props.sim.duration_ms,
      rowStart: 0,
      rowHeight: (height - AXIS_HEIGHT) / Math.max(layout.nRows, 1),
      left: LEFT,
      showRowLabels: false,
      currentTime: props.currentTime,
    }),
    [width, height, props.sim, layout, props.currentTime],
  );

  useEffect(() => {
    const canvas = drawRef.current;
    if (canvas === null) {
      return;
    }
    const ctx = prepareCanvas(canvas, view.width, view.height);
    if (ctx === null) {
      return;
    }
    drawRaster(ctx, props.data, props.sim, layout, view);
  }, [view, layout, props.data, props.sim]);

  const handleClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    if (x < LEFT) {
      return;
    }
    const time = xToTime(view, x);
    if (time < 0 || time > props.sim.duration_ms) {
      return;
    }
    props.onTimeClick(time);
  };

  return (
    <div className="raster" ref={wrapperRef}>
      <canvas ref={drawRef} onClick={handleClick} />
    </div>
  );
}
