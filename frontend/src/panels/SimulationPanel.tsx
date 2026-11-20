import { useMemo, useState } from "react";
import type { CircuitData, SimulateResponse } from "../api";
import { api } from "../api";
import LineChart from "../charts/LineChart";
import type { Series } from "../charts/LineChart";
import Raster from "../charts/Raster";
import RasterExplorer from "../charts/RasterExplorer";
import { seriesColor } from "../colors";
import Modal from "../components/Modal";
import StimulusForm from "../components/StimulusForm";
import { formatNumber } from "../format";
import type { RunSettings } from "../state";

interface SimulationPanelProps {
  circuit: string;
  data: CircuitData;
  settings: RunSettings;
  onSettings: (value: RunSettings) => void;
  useExtraEdges: boolean;
  ablated: Set<number>;
  sim: SimulateResponse | null;
  onSim: (value: SimulateResponse | null) => void;
  time: number;
  onTime: (value: number) => void;
  playing: boolean;
  onPlaying: (value: boolean) => void;
  speed: number;
  onSpeed: (value: number) => void;
  extraPsthTypes: string[];
  onSelectNeuron: (index: number) => void;
}

function defaultGroups(sim: SimulateResponse, data: CircuitData, extra: string[]): string[] {
  const available = Object.keys(sim.psth.groups);
  const wanted: string[] = [];
  for (const name of extra) {
    if (available.includes(name)) {
      wanted.push(name);
    }
  }
  if (wanted.length > 0) {
    return wanted;
  }
  if (available.includes("role:input")) {
    wanted.push("role:input");
  }
  for (const summary of data.type_summary) {
    if ((summary.role === "hub" || summary.role === "output") && available.includes(summary.type)) {
      wanted.push(summary.type);
    }
  }
  return wanted.slice(0, 6);
}

export default function SimulationPanel(props: SimulationPanelProps) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applyLesion, setApplyLesion] = useState(false);
  const [explorerOpen, setExplorerOpen] = useState(false);
  // The user's group choice is remembered per simulation result; a new result starts from defaults.
  const [groupChoice, setGroupChoice] = useState<{ sim: SimulateResponse | null; groups: string[] }>({
    sim: null,
    groups: [],
  });

  const sim = props.sim;
  const groups = useMemo(() => {
    if (sim === null) {
      return [];
    }
    if (groupChoice.sim === sim) {
      return groupChoice.groups;
    }
    return defaultGroups(sim, props.data, props.extraPsthTypes);
  }, [sim, groupChoice, props.data, props.extraPsthTypes]);
  const setGroups = (next: string[]) => {
    setGroupChoice({ sim, groups: next });
  };

  const run = async () => {
    setRunning(true);
    setError(null);
    props.onPlaying(false);
    let lesion = null;
    if (applyLesion && props.ablated.size > 0) {
      lesion = {
        types: [],
        instances: [],
        roles: [],
        body_ids: Array.from(props.ablated).map((i) => props.data.body_ids[i]),
      };
    }
    try {
      const result = await api.simulate({
        circuit: props.circuit,
        stimulus: props.settings.stimulus,
        duration_ms: props.settings.duration_ms,
        n_trials: props.settings.n_trials,
        base_seed: props.settings.base_seed,
        use_extra_edges: props.useExtraEdges,
        lesion,
        record_body_ids: [],
        bin_ms: 10,
        raster_trial: 0,
        max_raster_spikes: 400000,
        psth_types: props.extraPsthTypes,
        max_psth_types: 40,
      });
      props.onSim(result);
      props.onTime(0);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const series: Series[] = useMemo(() => {
    const out: Series[] = [];
    if (sim === null) {
      return out;
    }
    groups.forEach((name, i) => {
      const values = sim.psth.groups[name];
      if (values !== undefined) {
        out.push({ label: name, values, color: seriesColor(i) });
      }
    });
    return out;
  }, [sim, groups]);

  const toggleGroup = (name: string) => {
    if (groups.includes(name)) {
      setGroups(groups.filter((g) => g !== name));
    } else {
      setGroups([...groups, name]);
    }
  };

  let lesionToggle = null;
  if (props.ablated.size > 0) {
    lesionToggle = (
      <label className="check">
        <input type="checkbox" checked={applyLesion} onChange={(e) => setApplyLesion(e.target.checked)} />
        apply current ablation ({props.ablated.size} neurons)
      </label>
    );
  }

  let runLabel = "Run simulation";
  if (running) {
    runLabel = "Running…";
  }

  let results = null;
  if (sim !== null) {
    let truncatedNote = null;
    if (sim.raster_truncated) {
      truncatedNote = <p className="warning">Raster truncated for display.</p>;
    }
    let playLabel = "▶ Play";
    if (props.playing) {
      playLabel = "❚❚ Pause";
    }
    const topTypes = sim.type_rates.slice(0, 12);
    let explorer = null;
    if (explorerOpen) {
      explorer = (
        <Modal
          title={`Raster explorer · trial ${sim.raster_trial} · ${sim.duration_ms} ms`}
          onClose={() => setExplorerOpen(false)}
          wide
        >
          <RasterExplorer
            data={props.data}
            sim={sim}
            currentTime={props.time}
            onTimeClick={(t) => {
              props.onPlaying(false);
              props.onTime(t);
            }}
            onSelectNeuron={(index) => {
              setExplorerOpen(false);
              props.onSelectNeuron(index);
            }}
          />
        </Modal>
      );
    }
    results = (
      <div className="sim-results">
        <p className="muted">
          {sim.n_trials} trials × {sim.duration_ms} ms in {sim.elapsed_s}s ·{" "}
          {sim.total_spikes.toLocaleString()} spikes (raster and graph animation show trial {sim.raster_trial}
          )
        </p>
        {truncatedNote}
        {explorer}
        <div className="playback">
          <button onClick={() => props.onPlaying(!props.playing)}>{playLabel}</button>
          <input
            type="range"
            min={0}
            max={sim.duration_ms}
            step={sim.dt_ms}
            value={props.time}
            onChange={(e) => {
              props.onPlaying(false);
              props.onTime(Number(e.target.value));
            }}
          />
          <span className="mono">{formatNumber(props.time, 1)} ms</span>
          <select
            value={props.speed}
            onChange={(e) => props.onSpeed(Number(e.target.value))}
            title="playback speed"
          >
            <option value={0.02}>0.02×</option>
            <option value={0.05}>0.05×</option>
            <option value={0.1}>0.1×</option>
            <option value={0.25}>0.25×</option>
          </select>
        </div>
        <div className="raster-head">
          <h4>Raster (grouped by role, then type)</h4>
          <button className="small" onClick={() => setExplorerOpen(true)}>
            ⤢ enlarge and explore
          </button>
        </div>
        <Raster data={props.data} sim={sim} currentTime={props.time} onTimeClick={(t) => props.onTime(t)} />
        <h4>Population rate per group (mean over neurons and trials)</h4>
        <LineChart x={sim.psth.bin_starts_ms} series={series} cursorX={props.time} />
        <div className="group-toggles">
          {Object.keys(sim.psth.groups).map((name) => (
            <label key={name} className="check small">
              <input type="checkbox" checked={groups.includes(name)} onChange={() => toggleGroup(name)} />
              {name}
            </label>
          ))}
        </div>
        <h4>Most active cell types</h4>
        <table>
          <thead>
            <tr>
              <th>type</th>
              <th>role</th>
              <th className="num">n</th>
              <th className="num">rate (Hz)</th>
              <th className="num">± trials</th>
              <th className="num">active</th>
            </tr>
          </thead>
          <tbody>
            {topTypes.map((t) => (
              <tr key={t.type}>
                <td>{t.type}</td>
                <td>{t.role}</td>
                <td className="num">{t.n_neurons}</td>
                <td className="num">{formatNumber(t.mean_rate_hz, 1)}</td>
                <td className="num">{formatNumber(t.std_over_trials_hz, 1)}</td>
                <td className="num">{formatNumber(t.fraction_active * 100, 0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  let errorBox = null;
  if (error !== null) {
    errorBox = <p className="error">{error}</p>;
  }

  return (
    <div className="panel">
      <StimulusForm data={props.data} value={props.settings} onChange={props.onSettings} />
      {lesionToggle}
      <button className="primary" onClick={run} disabled={running}>
        {runLabel}
      </button>
      {errorBox}
      {results}
    </div>
  );
}
