import type { ScreenRow } from "../api";
import { formatNumber } from "../format";
import { orDefault } from "../state";

export type BarMode = "percent_change" | "mean_difference" | "cohens_d";

interface BarListProps {
  rows: ScreenRow[];
  selected: string | null;
  onSelect: (label: string) => void;
  mode: BarMode;
  limit?: number;
}

/** True when the measured group was silent at baseline and the lesion made it fire (Δ% undefined). */
function wokeFromZero(row: ScreenRow): boolean {
  const percent = row.percent_change;
  const difference = orDefault(row.mean_difference, 0);
  return (percent === null || percent === undefined) && difference !== 0;
}

/** The value a bar is drawn from in the chosen mode. */
function barValue(row: ScreenRow, mode: BarMode): number {
  if (mode === "mean_difference") {
    return orDefault(row.mean_difference, 0);
  }
  if (mode === "cohens_d") {
    const d = orDefault(row.cohens_d, 0);
    if (!Number.isFinite(d)) {
      return 0;
    }
    return d;
  }
  return orDefault(row.percent_change, 0);
}

function valueText(row: ScreenRow, mode: BarMode): string {
  const difference = formatNumber(row.mean_difference, 1);
  if (mode === "mean_difference") {
    return `Δ ${difference} spikes`;
  }
  if (wokeFromZero(row)) {
    return `from 0 · Δ ${difference} spikes`;
  }
  return `${formatNumber(row.percent_change, 0)}% · Δ ${difference}`;
}

/** Ranked horizontal bars; click a bar to highlight that type on the graph. */
export default function BarList(props: BarListProps) {
  let limit = 30;
  if (props.limit !== undefined) {
    limit = props.limit;
  }
  const rows = props.rows.slice(0, limit);
  let maxAbs = 1;
  for (const row of rows) {
    const value = Math.abs(barValue(row, props.mode));
    if (value > maxAbs) {
      maxAbs = value;
    }
  }
  return (
    <div className="bar-list">
      {rows.map((row) => {
        let value = barValue(row, props.mode);
        let fraction = Math.abs(value) / maxAbs;
        if (props.mode === "percent_change" && wokeFromZero(row)) {
          // Waking a silent group is the largest relative change: draw a full bar.
          value = orDefault(row.mean_difference, 0);
          fraction = 1;
        }
        const style: React.CSSProperties = { width: `${fraction * 50}%` };
        let barClass = "bar bar-positive";
        if (value < 0) {
          barClass = "bar bar-negative";
          style.right = "50%";
        } else {
          style.left = "50%";
        }
        let rowClass = "bar-row";
        if (props.selected === row.label) {
          rowClass = "bar-row bar-row-selected";
        }
        const ci = orDefault(row.cohens_d_ci, [null, null]);
        return (
          <div key={row.label} className={rowClass} onClick={() => props.onSelect(row.label)}>
            <div className="bar-label" title={row.label}>
              {row.label} <span className="muted">×{row.n_ablated}</span>
            </div>
            <div className="bar-track">
              <div className="bar-axis" />
              <div className={barClass} style={style} />
            </div>
            <div className="bar-value">
              {valueText(row, props.mode)} · d={formatNumber(row.cohens_d, 1)}{" "}
              <span className="muted">
                [{formatNumber(ci[0], 1)}, {formatNumber(ci[1], 1)}]
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
