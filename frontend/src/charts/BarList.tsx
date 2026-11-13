import type { ScreenRow } from "../api";
import { formatNumber } from "../format";
import { orDefault } from "../state";

interface BarListProps {
  rows: ScreenRow[];
  selected: string | null;
  onSelect: (label: string) => void;
  limit?: number;
}

/** Ranked horizontal bars of percent change; click a bar to highlight it on the graph. */
export default function BarList(props: BarListProps) {
  let limit = 30;
  if (props.limit !== undefined) {
    limit = props.limit;
  }
  const rows = props.rows.slice(0, limit);
  let maxAbs = 1;
  for (const row of rows) {
    const value = Math.abs(orDefault(row.percent_change, 0));
    if (value > maxAbs) {
      maxAbs = value;
    }
  }
  return (
    <div className="bar-list">
      {rows.map((row) => {
        const change = orDefault(row.percent_change, 0);
        const width = `${(Math.abs(change) / maxAbs) * 50}%`;
        const style: React.CSSProperties = { width };
        let barClass = "bar bar-positive";
        if (change < 0) {
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
              {formatNumber(change, 0)}% · d={formatNumber(row.cohens_d, 1)}{" "}
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
