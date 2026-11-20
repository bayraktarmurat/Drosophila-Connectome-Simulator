import { useEffect, useLayoutEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { CHART_GRID, CHART_TEXT, CURSOR } from "../colors";
import { orDefault } from "../state";

export interface Series {
  label: string;
  values: (number | null)[];
  color: string;
  dashed?: boolean;
}

interface LineChartProps {
  x: number[];
  series: Series[];
  height?: number;
  xLabel?: string;
  yLabel?: string;
  cursorX?: number | null;
}

/** Thin uPlot wrapper; recreated when the data changes, cursor line drawn via a hook. */
export default function LineChart(props: LineChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const plotRef = useRef<uPlot | null>(null);
  const cursorRef = useRef<number | null>(null);
  let height = 180;
  if (props.height !== undefined) {
    height = props.height;
  }
  useLayoutEffect(() => {
    cursorRef.current = orDefault(props.cursorX, null);
  });

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) {
      return;
    }
    const seriesOptions: uPlot.Series[] = [{ label: orDefault(props.xLabel, "time (ms)") }];
    for (const s of props.series) {
      const option: uPlot.Series = { label: s.label, stroke: s.color, width: 1.5 };
      if (s.dashed === true) {
        option.dash = [6, 4];
      }
      seriesOptions.push(option);
    }
    const drawCursor = (plot: uPlot) => {
      const value = cursorRef.current;
      if (value === null) {
        return;
      }
      const left = plot.valToPos(value, "x", true);
      const ctx = plot.ctx;
      ctx.save();
      ctx.strokeStyle = CURSOR;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(left, plot.bbox.top);
      ctx.lineTo(left, plot.bbox.top + plot.bbox.height);
      ctx.stroke();
      ctx.restore();
    };
    const options: uPlot.Options = {
      width: Math.max(container.clientWidth, 200),
      height,
      series: seriesOptions,
      scales: { x: { time: false } },
      axes: [
        {
          label: orDefault(props.xLabel, "time (ms)"),
          stroke: CHART_TEXT,
          grid: { stroke: CHART_GRID },
          ticks: { stroke: CHART_GRID },
        },
        {
          label: orDefault(props.yLabel, "rate (Hz)"),
          stroke: CHART_TEXT,
          grid: { stroke: CHART_GRID },
          ticks: { stroke: CHART_GRID },
        },
      ],
      hooks: { draw: [drawCursor] },
      legend: { live: false },
    };
    const columns: uPlot.AlignedData = [props.x, ...props.series.map((s) => s.values)];
    const plot = new uPlot(options, columns, container);
    plotRef.current = plot;
    const observer = new ResizeObserver(() => {
      plot.setSize({ width: Math.max(container.clientWidth, 200), height });
    });
    observer.observe(container);
    return () => {
      observer.disconnect();
      plot.destroy();
      plotRef.current = null;
    };
  }, [props.x, props.series, height, props.xLabel, props.yLabel]);

  useEffect(() => {
    if (plotRef.current !== null) {
      plotRef.current.redraw(false, false);
    }
  }, [props.cursorX]);

  return <div className="line-chart" ref={containerRef} />;
}
