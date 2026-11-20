import { useState } from "react";
import type { CircuitData, NeuronSet, PathResponse } from "../api";
import { api, emptySet, isEmptySet, resolveSet } from "../api";
import NeuronSetPicker from "../components/NeuronSetPicker";
import { neuronName, signLabel } from "../format";
import type { Highlight } from "../GraphView";
import { pathHighlight } from "../highlight";

interface QueryPanelProps {
  circuit: string;
  data: CircuitData;
  onHighlight: (value: Highlight | null) => void;
  onSelect: (index: number) => void;
}

interface DirectEdge {
  pre: number;
  post: number;
  synapses: number;
}

interface QueryResult {
  aToB: DirectEdge[];
  bToA: DirectEdge[];
  nA: number;
  nB: number;
}

/** Direct edges from any neuron in `from` to any neuron in `to`, strongest first. */
function directEdges(data: CircuitData, from: Set<number>, to: Set<number>): DirectEdge[] {
  const out: DirectEdge[] = [];
  for (let e = 0; e < data.edge_pre.length; e += 1) {
    const pre = data.edge_pre[e];
    const post = data.edge_post[e];
    if (from.has(pre) && to.has(post)) {
      out.push({ pre, post, synapses: data.edge_weight[e] });
    }
  }
  out.sort((a, b) => b.synapses - a.synapses);
  return out;
}

function totalSynapses(edges: DirectEdge[]): number {
  let total = 0;
  for (const edge of edges) {
    total += edge.synapses;
  }
  return total;
}

function edgesHighlight(edges: DirectEdge[]): Highlight {
  const nodes = new Set<number>();
  const pairs: Array<[number, number]> = [];
  for (const edge of edges) {
    nodes.add(edge.pre);
    nodes.add(edge.post);
    pairs.push([edge.pre, edge.post]);
  }
  return { nodes, edges: pairs };
}

function EdgeTable(props: {
  title: string;
  edges: DirectEdge[];
  data: CircuitData;
  onSelect: (index: number) => void;
  onHighlight: (value: Highlight) => void;
}) {
  const data = props.data;
  const name = (index: number) => neuronName(data.instances[index], data.types[index], data.body_ids[index]);
  if (props.edges.length === 0) {
    return (
      <div>
        <h4>{props.title}</h4>
        <p className="hint">No direct connection.</p>
      </div>
    );
  }
  return (
    <div>
      <h4>
        {props.title}: {props.edges.length} connection(s), {totalSynapses(props.edges)} synapses{" "}
        <button className="small" onClick={() => props.onHighlight(edgesHighlight(props.edges))}>
          show on graph
        </button>
      </h4>
      <table>
        <thead>
          <tr>
            <th>from (pre)</th>
            <th>to (post)</th>
            <th className="num">synapses</th>
            <th>sign</th>
          </tr>
        </thead>
        <tbody>
          {props.edges.map((edge) => {
            const sign = data.signs[edge.pre];
            return (
              <tr key={`${edge.pre}>${edge.post}`}>
                <td className="clickable-cell" onClick={() => props.onSelect(edge.pre)}>
                  {name(edge.pre)}
                </td>
                <td className="clickable-cell" onClick={() => props.onSelect(edge.post)}>
                  {name(edge.post)}
                </td>
                <td className="num">{edge.synapses}</td>
                <td className={`sign sign-${sign}`}>
                  {signLabel(sign)} <span className="muted">({data.nts[edge.pre]})</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** "Is there a connection between A and B?": direct edges both ways, then indirect paths. */
export default function QueryPanel(props: QueryPanelProps) {
  const [setA, setSetA] = useState<NeuronSet>(emptySet());
  const [setB, setSetB] = useState<NeuronSet>(emptySet());
  const [result, setResult] = useState<QueryResult | null>(null);
  const [paths, setPaths] = useState<PathResponse | null>(null);
  const [pathsRunning, setPathsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [maxHops, setMaxHops] = useState(3);

  let minWeight = "10";
  const manifestWeight = props.data.manifest["edge_min_weight"];
  if (manifestWeight !== undefined && manifestWeight !== null) {
    minWeight = String(manifestWeight);
  }

  const check = () => {
    const a = new Set(resolveSet(props.data, setA));
    const b = new Set(resolveSet(props.data, setB));
    setPaths(null);
    setError(null);
    const aToB = directEdges(props.data, a, b);
    const bToA = directEdges(props.data, b, a);
    setResult({ aToB, bToA, nA: a.size, nB: b.size });
    const all = [...aToB, ...bToA];
    if (all.length > 0) {
      props.onHighlight(edgesHighlight(all));
    } else {
      props.onHighlight(null);
    }
  };

  const findPaths = async () => {
    setPathsRunning(true);
    setError(null);
    try {
      const response = await api.paths({
        circuit: props.circuit,
        sources: setA,
        targets: setB,
        k: 5,
        max_hops: maxHops,
        sign_filter: "any",
        level: "neuron",
        normalization: null,
        min_synapses: 1,
      });
      setPaths(response);
      if (response.paths.length > 0) {
        props.onHighlight(pathHighlight(props.data, response.paths[0], "neuron"));
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPathsRunning(false);
    }
  };

  const canRun = !isEmptySet(setA) && !isEmptySet(setB);

  let resultBox = null;
  if (result !== null) {
    resultBox = (
      <div>
        <p className="muted">
          A = {result.nA} neuron(s), B = {result.nB} neuron(s)
        </p>
        <EdgeTable
          title="A → B"
          edges={result.aToB}
          data={props.data}
          onSelect={props.onSelect}
          onHighlight={props.onHighlight}
        />
        <EdgeTable
          title="B → A"
          edges={result.bToA}
          data={props.data}
          onSelect={props.onSelect}
          onHighlight={props.onHighlight}
        />
        <div className="field-row query-paths">
          <label className="field">
            <span className="field-label">max hops</span>
            <input
              type="number"
              min={2}
              max={6}
              value={maxHops}
              onChange={(e) => setMaxHops(Math.max(1, Math.round(Number(e.target.value))))}
            />
          </label>
          <button onClick={findPaths} disabled={pathsRunning}>
            Find indirect paths A → B
          </button>
        </div>
      </div>
    );
  }

  let pathBox = null;
  if (paths !== null) {
    const data = props.data;
    let empty = null;
    if (paths.paths.length === 0) {
      empty = <p className="hint">No path from A to B within {maxHops} hops.</p>;
    }
    pathBox = (
      <div>
        <h4>Strongest paths A → B (click to highlight)</h4>
        {empty}
        <table>
          <tbody>
            {paths.paths.map((path, row) => (
              <tr
                key={row}
                className="clickable"
                onClick={() => props.onHighlight(pathHighlight(data, path, "neuron"))}
              >
                <td>{row + 1}</td>
                <td>
                  {path.nodes.map((node, i) => {
                    let arrow = null;
                    if (i < path.synapses.length) {
                      arrow = (
                        <span className="arrow">
                          {" "}
                          →<sub>{path.synapses[i]}</sub>{" "}
                        </span>
                      );
                    }
                    return (
                      <span key={i}>
                        <span className="path-node">
                          {neuronName(data.instances[node.index], node.type, data.body_ids[node.index])}
                        </span>
                        {arrow}
                      </span>
                    );
                  })}
                </td>
                <td className={`sign sign-${path.sign}`}>{signLabel(path.sign)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="hint">Subscripts = synapse counts. Net sign = product of the pre-neuron signs.</p>
      </div>
    );
  }

  let errorBox = null;
  if (error !== null) {
    errorBox = <p className="error">{error}</p>;
  }

  return (
    <div className="panel">
      <p className="hint">
        Is there a connection between two neurons (or groups)? Use a bodyId (29086), an instance (DNge023_L)
        or a type (GNG132).
      </p>
      <NeuronSetPicker label="A" data={props.data} value={setA} onChange={setSetA} allowRoles={false} />
      <NeuronSetPicker label="B" data={props.data} value={setB} onChange={setSetB} allowRoles={false} />
      <button className="primary" onClick={check} disabled={!canRun}>
        Check connection
      </button>
      <p className="hint">
        Only connections with ≥ {minWeight} synapses inside this sub-circuit are in the data. &ldquo;No direct
        connection&rdquo; means none at that threshold here, not none in the whole fly.
      </p>
      {errorBox}
      {resultBox}
      {pathBox}
    </div>
  );
}
