import { useEffect, useMemo, useRef, useState } from "react";
import type { CircuitData, LesionResponse, Metric, MetricRow, NeuronSet, ScreenStatus } from "../api";
import { api, resolveSet } from "../api";
import BarList from "../charts/BarList";
import LineChart from "../charts/LineChart";
import type { Series } from "../charts/LineChart";
import { seriesColor } from "../colors";
import NeuronSetPicker from "../components/NeuronSetPicker";
import StimulusForm from "../components/StimulusForm";
import { formatNumber } from "../format";
import type { Highlight } from "../GraphView";
import type { RunSettings } from "../state";
import { orDefault } from "../state";

interface LesionPanelProps {
  circuit: string;
  data: CircuitData;
  settings: RunSettings;
  onSettings: (value: RunSettings) => void;
  useExtraEdges: boolean;
  ablated: Set<number>;
  onAblated: (value: Set<number>) => void;
  clickToAblate: boolean;
  onClickToAblate: (value: boolean) => void;
  onHighlight: (highlight: Highlight | null) => void;
}

const METRIC_LABELS: Record<Metric, string> = {
  spike_count: "spike count",
  rate_hz: "rate (Hz)",
  first_spike_ms: "first-spike latency (ms)",
};

function meanSd(mean: number | null | undefined, sd: number | null | undefined, digits: number): string {
  return `${formatNumber(mean, digits)} ± ${formatNumber(sd, digits)}`;
}

function ciText(ci: (number | null)[] | undefined, digits: number): string {
  if (ci === undefined) {
    return "";
  }
  return `[${formatNumber(ci[0], digits)}, ${formatNumber(ci[1], digits)}]`;
}

function MetricsTable(props: { rows: MetricRow[]; metric: Metric }) {
  const rows = props.rows.filter((r) => r.metric === props.metric);
  return (
    <table className="metrics-table">
      <thead>
        <tr>
          <th>group</th>
          <th className="num">baseline</th>
          <th className="num">lesion</th>
          <th className="num">Δ%</th>
          <th className="num">Cohen's d [95% CI]</th>
          <th className="num secondary">p</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          let responded = null;
          if (props.metric === "first_spike_ms") {
            responded = (
              <div className="muted small">
                responded {formatNumber(row.responded_baseline * 100, 0)}% → {formatNumber(row.responded_lesion * 100, 0)}%
              </div>
            );
          }
          let dCell = <span className="muted">n/a (fewer than 2 paired trials)</span>;
          if (row.comparison_valid) {
            dCell = (
              <span>
                <strong>{formatNumber(row.cohens_d, 2)}</strong>{" "}
                <span className="muted">{ciText(row.cohens_d_ci, 2)}</span>
              </span>
            );
          }
          let ablatedNote = null;
          if (row.n_ablated_in_group > 0) {
            ablatedNote = <span className="muted small"> ({row.n_ablated_in_group} ablated)</span>;
          }
          return (
            <tr key={row.group}>
              <td>
                {row.group}
                {ablatedNote}
                {responded}
              </td>
              <td className="num">{meanSd(row.baseline_mean, row.baseline_std, 1)}</td>
              <td className="num">{meanSd(row.lesion_mean, row.lesion_std, 1)}</td>
              <td className="num">{formatNumber(row.percent_change, 1)}</td>
              <td className="num">{dCell}</td>
              <td className="num secondary">{formatNumber(row.p_value_wilcoxon, 3)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function LesionPanel(props: LesionPanelProps) {
  const [result, setResult] = useState<LesionResponse | null>(null);
  const [metric, setMetric] = useState<Metric>("spike_count");
  const [plotGroup, setPlotGroup] = useState<string>("all outputs");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typeDraft, setTypeDraft] = useState<NeuronSet>({ types: [], body_ids: [], roles: [] });

  const [measure, setMeasure] = useState<NeuronSet>({ types: [], body_ids: [], roles: ["output"] });
  const [screenMetric, setScreenMetric] = useState<Metric>("spike_count");
  const [screenTrials, setScreenTrials] = useState(5);
  const [screenDuration, setScreenDuration] = useState(300);
  const [job, setJob] = useState<ScreenStatus | null>(null);
  const [selectedBar, setSelectedBar] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
      }
    };
  }, []);

  const ablatedBodyIds = Array.from(props.ablated).map((i) => props.data.body_ids[i]);

  const addToAblation = (set: NeuronSet) => {
    const indices = resolveSet(props.data, set);
    const next = new Set(props.ablated);
    for (const i of indices) {
      next.add(i);
    }
    props.onAblated(next);
    setTypeDraft({ types: [], body_ids: [], roles: [] });
  };

  const runLesion = async () => {
    setRunning(true);
    setError(null);
    try {
      const response = await api.lesion({
        circuit: props.circuit,
        stimulus: props.settings.stimulus,
        duration_ms: props.settings.duration_ms,
        n_trials: props.settings.n_trials,
        base_seed: props.settings.base_seed,
        use_extra_edges: props.useExtraEdges,
        lesion: { types: [], roles: [], body_ids: ablatedBodyIds },
        output_groups: [],
        bin_ms: 10,
      });
      setResult(response);
      if (!(plotGroup in response.psth_baseline.groups)) {
        setPlotGroup(Object.keys(response.psth_baseline.groups)[0]);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const startScreen = async () => {
    setError(null);
    setSelectedBar(null);
    try {
      const status = await api.startScreen({
        circuit: props.circuit,
        stimulus: props.settings.stimulus,
        duration_ms: screenDuration,
        n_trials: screenTrials,
        base_seed: props.settings.base_seed,
        use_extra_edges: props.useExtraEdges,
        level: "type",
        candidates: null,
        measure,
        metric: screenMetric,
        rank_by: "percent_change",
        max_columns: 200,
      });
      setJob(status);
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
      }
      pollRef.current = window.setInterval(async () => {
        const next = await api.screenStatus(status.job_id);
        setJob(next);
        if (next.status !== "queued" && next.status !== "running") {
          if (pollRef.current !== null) {
            window.clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }
      }, 1000);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const cancelScreen = async () => {
    if (job !== null) {
      setJob(await api.cancelScreen(job.job_id));
    }
  };

  const selectBar = (label: string) => {
    setSelectedBar(label);
    const nodes = new Set<number>();
    props.data.types.forEach((t, i) => {
      if (t === label) {
        nodes.add(i);
      }
    });
    props.onHighlight({ nodes, edges: [] });
  };

  const series: Series[] = useMemo(() => {
    if (result === null) {
      return [];
    }
    const base = result.psth_baseline.groups[plotGroup];
    const lesion = result.psth_lesion.groups[plotGroup];
    if (base === undefined || lesion === undefined) {
      return [];
    }
    return [
      { label: `${plotGroup} baseline`, values: base, color: seriesColor(0) },
      { label: `${plotGroup} lesion`, values: lesion, color: seriesColor(1), dashed: true },
    ];
  }, [result, plotGroup]);

  let lesionResults = null;
  if (result !== null) {
    let baselineNote = "computed";
    if (result.baseline_cached) {
      baselineNote = "reused from cache";
    }
    // Circuit-wide model warnings live in the header; show only lesion-specific ones here.
    const specific = result.warnings.filter((w) => !props.data.warnings.includes(w));
    let warnings = null;
    if (specific.length > 0) {
      warnings = (
        <ul className="warning-list">
          {specific.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      );
    }
    lesionResults = (
      <div>
        <p className="muted">
          {result.n_ablated} neurons ablated · paired trials share seeds · baseline {baselineNote}
        </p>
        {warnings}
        <div className="field-row">
          <label className="field">
            <span className="field-label">metric</span>
            <select value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
              {Object.entries(METRIC_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <MetricsTable rows={result.metrics} metric={metric} />
        <p className="hint">{result.p_value_note}</p>
        <div className="field-row">
          <label className="field">
            <span className="field-label">rate curve</span>
            <select value={plotGroup} onChange={(e) => setPlotGroup(e.target.value)}>
              {Object.keys(result.psth_baseline.groups).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <LineChart x={result.psth_baseline.bin_starts_ms} series={series} />
      </div>
    );
  }

  let screenResults = null;
  if (job !== null) {
    const progress = `${job.done} / ${job.total}`;
    let rows = null;
    if (job.results !== null && job.results.length > 0) {
      rows = <BarList rows={orDefault(job.results, [])} selected={selectedBar} onSelect={selectBar} />;
    }
    let cancel = null;
    if (job.status === "running" || job.status === "queued") {
      cancel = <button onClick={cancelScreen}>Cancel</button>;
    }
    let jobError = null;
    if (job.error !== null) {
      jobError = <p className="error">{job.error}</p>;
    }
    let skipped = null;
    if (job.skipped.length > 0) {
      skipped = <p className="muted small">Skipped (overlap with measured group): {job.skipped.join(", ")}</p>;
    }
    let fraction = 0;
    if (job.total > 0) {
      fraction = job.done / job.total;
    }
    screenResults = (
      <div>
        <div className="progress">
          <div className="progress-bar" style={{ width: `${fraction * 100}%` }} />
        </div>
        <p className="muted">
          {job.status} · {progress} candidates · {job.elapsed_s}s {cancel}
        </p>
        {jobError}
        {skipped}
        {rows}
        <p className="hint">
          Bars: % change of the measured group's {METRIC_LABELS[screenMetric]} when each cell type is removed
          (all its neurons). d = Cohen's d with 95% bootstrap CI. Click a bar to highlight that type.
        </p>
      </div>
    );
  }

  let runLabel = "Run baseline vs lesion";
  if (running) {
    runLabel = "Running…";
  }
  let errorBox = null;
  if (error !== null) {
    errorBox = <p className="error">{error}</p>;
  }
  const ablatedTypes = new Map<string, number>();
  for (const i of props.ablated) {
    const t = props.data.types[i];
    ablatedTypes.set(t, orDefault(ablatedTypes.get(t), 0) + 1);
  }

  return (
    <div className="panel">
      <h4>Ablation set</h4>
      <label className="check">
        <input
          type="checkbox"
          checked={props.clickToAblate}
          onChange={(e) => props.onClickToAblate(e.target.checked)}
        />
        click graph nodes to ablate / restore
      </label>
      <div className="chips">
        {Array.from(ablatedTypes.entries()).map(([t, n]) => (
          <span key={t} className="chip chip-ablated">
            {t} ×{n}
          </span>
        ))}
      </div>
      <NeuronSetPicker
        label="Add to ablation (type, bodyId or role)"
        data={props.data}
        value={typeDraft}
        onChange={addToAblation}
      />
      <button onClick={() => props.onAblated(new Set())}>Clear ablation</button>
      <details>
        <summary>Stimulus (shared with the Simulation tab)</summary>
        <StimulusForm data={props.data} value={props.settings} onChange={props.onSettings} />
      </details>
      <button className="primary" onClick={runLesion} disabled={running || props.ablated.size === 0}>
        {runLabel}
      </button>
      {errorBox}
      {lesionResults}

      <h4 className="section">Lesion screen (one cell type at a time)</h4>
      <NeuronSetPicker label="Measured group" data={props.data} value={measure} onChange={setMeasure} />
      <div className="field-row">
        <label className="field">
          <span className="field-label">metric</span>
          <select value={screenMetric} onChange={(e) => setScreenMetric(e.target.value as Metric)}>
            {Object.entries(METRIC_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">trials</span>
          <input type="number" min={2} max={50} value={screenTrials} onChange={(e) => setScreenTrials(Number(e.target.value))} />
        </label>
        <label className="field">
          <span className="field-label">duration (ms)</span>
          <input type="number" min={50} step={50} value={screenDuration} onChange={(e) => setScreenDuration(Number(e.target.value))} />
        </label>
      </div>
      <button className="primary" onClick={startScreen}>
        Start screen
      </button>
      {screenResults}
    </div>
  );
}
