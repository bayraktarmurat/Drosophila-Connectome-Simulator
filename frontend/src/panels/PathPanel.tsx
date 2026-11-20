import { useState } from "react";
import type { CircuitData, NeuronSet, PathLevel, PathOut, PathResponse, SignFilter } from "../api";
import { api } from "../api";
import NeuronSetPicker from "../components/NeuronSetPicker";
import { formatScientific, signLabel } from "../format";
import type { Highlight } from "../GraphView";
import { pathHighlight } from "../highlight";

interface PathPanelProps {
  circuit: string;
  data: CircuitData;
  onHighlight: (highlight: Highlight | null) => void;
  onSimulatePath: (path: PathOut, level: PathLevel) => void;
}

function defaultTargets(data: CircuitData): NeuronSet {
  const roles: string[] = [];
  if (data.roles.includes("output")) {
    roles.push("output");
  }
  return { types: [], instances: [], body_ids: [], roles };
}

export default function PathPanel(props: PathPanelProps) {
  const [sources, setSources] = useState<NeuronSet>({
    types: [],
    instances: [],
    body_ids: [],
    roles: ["input"],
  });
  const [targets, setTargets] = useState<NeuronSet>(() => defaultTargets(props.data));
  const [k, setK] = useState(10);
  const [maxHops, setMaxHops] = useState(4);
  const [signFilter, setSignFilter] = useState<SignFilter>("any");
  const [level, setLevel] = useState<PathLevel>("type");
  const [result, setResult] = useState<PathResponse | null>(null);
  const [selectedRow, setSelectedRow] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    setSelectedRow(null);
    props.onHighlight(null);
    try {
      const response = await api.paths({
        circuit: props.circuit,
        sources,
        targets,
        k,
        max_hops: maxHops,
        sign_filter: signFilter,
        level,
        normalization: null,
        min_synapses: 1,
      });
      setResult(response);
      if (response.paths.length > 0) {
        setSelectedRow(0);
        props.onHighlight(pathHighlight(props.data, response.paths[0], response.level));
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const selectRow = (row: number) => {
    if (result === null) {
      return;
    }
    setSelectedRow(row);
    props.onHighlight(pathHighlight(props.data, result.paths[row], result.level));
  };

  let table = null;
  if (result !== null) {
    let truncated = null;
    if (result.truncated) {
      truncated = (
        <p className="warning">Search stopped at the expansion limit; results may be incomplete.</p>
      );
    }
    let empty = null;
    if (result.paths.length === 0) {
      empty = <p className="hint">No path within {maxHops} hops.</p>;
    }
    table = (
      <div>
        {truncated}
        {empty}
        <table className="path-table">
          <thead>
            <tr>
              <th>#</th>
              <th>path</th>
              <th className="num">score</th>
              <th>sign</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {result.paths.map((path, row) => {
              let rowClass = "clickable";
              if (row === selectedRow) {
                rowClass = "clickable selected";
              }
              return (
                <tr key={row} className={rowClass} onClick={() => selectRow(row)}>
                  <td>{row + 1}</td>
                  <td>
                    {path.nodes.map((node, i) => {
                      let arrow = null;
                      if (i < path.synapses.length) {
                        arrow = (
                          <span
                            className="arrow"
                            title={`${(path.shares[i] * 100).toFixed(2)}% of target input`}
                          >
                            {" "}
                            →<sub>{path.synapses[i]}</sub>{" "}
                          </span>
                        );
                      }
                      return (
                        <span key={i}>
                          <span className="path-node">{node.label}</span>
                          {arrow}
                        </span>
                      );
                    })}
                  </td>
                  <td className="num mono">{formatScientific(path.score)}</td>
                  <td className={`sign sign-${path.sign}`}>{signLabel(path.sign)}</td>
                  <td>
                    <button
                      className="small"
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onSimulatePath(path, result.level);
                      }}
                    >
                      simulate
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="hint">
          Score = product of per-edge input shares (synapses ÷ target's total input in the whole dataset,
          normalization: {result.normalization}). Subscripts are synapse counts. Paths are anatomical; whether
          they carry activity is a question for the simulator.
        </p>
      </div>
    );
  }

  let runLabel = "Find paths";
  if (running) {
    runLabel = "Searching…";
  }
  let errorBox = null;
  if (error !== null) {
    errorBox = <p className="error">{error}</p>;
  }

  return (
    <div className="panel">
      <NeuronSetPicker label="Source" data={props.data} value={sources} onChange={setSources} />
      <NeuronSetPicker label="Target" data={props.data} value={targets} onChange={setTargets} />
      <div className="field-row">
        <label className="field">
          <span className="field-label">level</span>
          <select value={level} onChange={(e) => setLevel(e.target.value as PathLevel)}>
            <option value="type">cell type</option>
            <option value="neuron">neuron</option>
          </select>
        </label>
        <label className="field">
          <span className="field-label">k</span>
          <input type="number" min={1} max={200} value={k} onChange={(e) => setK(Number(e.target.value))} />
        </label>
        <label className="field">
          <span className="field-label">max hops</span>
          <input
            type="number"
            min={1}
            max={8}
            value={maxHops}
            onChange={(e) => setMaxHops(Number(e.target.value))}
          />
        </label>
        <label className="field">
          <span className="field-label">net sign</span>
          <select value={signFilter} onChange={(e) => setSignFilter(e.target.value as SignFilter)}>
            <option value="any">any</option>
            <option value="excitatory">excitatory</option>
            <option value="inhibitory">inhibitory</option>
          </select>
        </label>
      </div>
      <button className="primary" onClick={run} disabled={running}>
        {runLabel}
      </button>
      <button onClick={() => props.onHighlight(null)}>Clear highlight</button>
      {errorBox}
      {table}
    </div>
  );
}
