import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CircuitData, CircuitSummary, NeuronSet, PathLevel, PathOut, SimulateResponse } from "./api";
import { api } from "./api";
import GraphView from "./GraphView";
import type { ColorBy, Highlight } from "./GraphView";
import LesionPanel from "./panels/LesionPanel";
import NeuronPanel from "./panels/NeuronPanel";
import PathPanel from "./panels/PathPanel";
import QueryPanel from "./panels/QueryPanel";
import SimulationPanel from "./panels/SimulationPanel";
import type { RunSettings } from "./state";
import { defaultRunSettings } from "./state";
import "./App.css";

type Tab = "neuron" | "simulate" | "paths" | "lesion" | "query";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "neuron", label: "Neuron" },
  { id: "simulate", label: "Simulate" },
  { id: "paths", label: "Paths" },
  { id: "lesion", label: "Lesion" },
  { id: "query", label: "Query" },
];

const ASIDE_MIN = 340;
const ASIDE_DEFAULT = 560;
const ASIDE_STORAGE_KEY = "connectome.asideWidth";

/** Side-panel width remembered in this browser (falls back to the default). */
function initialAsideWidth(): number {
  try {
    const stored = Number(window.localStorage.getItem(ASIDE_STORAGE_KEY));
    if (Number.isFinite(stored) && stored >= ASIDE_MIN) {
      return stored;
    }
  } catch {
    // storage unavailable: use the default
  }
  return ASIDE_DEFAULT;
}

function clampAsideWidth(width: number): number {
  const maximum = Math.max(ASIDE_MIN, window.innerWidth - 240);
  return Math.min(Math.max(width, ASIDE_MIN), maximum);
}

const GLOW_WINDOW_MS = 6;

/** First index i with values[i] >= target (values sorted ascending). */
function lowerBound(values: number[], target: number): number {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const mid = (low + high) >> 1;
    if (values[mid] < target) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }
  return low;
}

function activityAt(sim: SimulateResponse, time: number): Map<number, number> {
  const activity = new Map<number, number>();
  const start = lowerBound(sim.raster_times_ms, time - GLOW_WINDOW_MS);
  const end = lowerBound(sim.raster_times_ms, time + 1e-9);
  for (let i = start; i < end; i += 1) {
    const level = 1 - (time - sim.raster_times_ms[i]) / GLOW_WINDOW_MS;
    const neuron = sim.raster_neurons[i];
    const previous = activity.get(neuron);
    if (previous === undefined || previous < level) {
      activity.set(neuron, level);
    }
  }
  return activity;
}

export default function App() {
  const [circuits, setCircuits] = useState<CircuitSummary[]>([]);
  const [circuitName, setCircuitName] = useState<string | null>(null);
  const [data, setData] = useState<CircuitData | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("simulate");
  const [selected, setSelected] = useState<number | null>(null);
  const [highlight, setHighlight] = useState<Highlight | null>(null);
  const [ablated, setAblated] = useState<Set<number>>(new Set());
  const [clickToAblate, setClickToAblate] = useState(false);
  const [useExtraEdges, setUseExtraEdges] = useState(false);
  const [colorBy, setColorBy] = useState<ColorBy>("role");
  const [minEdgeWeight, setMinEdgeWeight] = useState(30);
  const [showWarnings, setShowWarnings] = useState(false);
  const [settings, setSettings] = useState<RunSettings | null>(null);
  const [sim, setSim] = useState<SimulateResponse | null>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(0.05);
  const [extraPsthTypes, setExtraPsthTypes] = useState<string[]>([]);
  const [asideWidth, setAsideWidth] = useState<number>(initialAsideWidth);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  // Drag the divider between graph and side panel to resize the panel.
  useEffect(() => {
    const move = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (drag === null) {
        return;
      }
      setAsideWidth(clampAsideWidth(drag.startWidth + drag.startX - event.clientX));
    };
    const up = () => {
      if (dragRef.current === null) {
        return;
      }
      dragRef.current = null;
      document.body.classList.remove("resizing");
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(ASIDE_STORAGE_KEY, String(asideWidth));
    } catch {
      // storage unavailable: width is not remembered
    }
  }, [asideWidth]);

  const startResize = (event: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = { startX: event.clientX, startWidth: asideWidth };
    document.body.classList.add("resizing");
    event.preventDefault();
  };

  useEffect(() => {
    api
      .circuits()
      .then((list) => {
        setCircuits(list);
        const first = list.find((c) => c.available);
        if (first !== undefined) {
          setCircuitName(first.name);
        } else {
          setLoadError("No circuit has cached data. Run scripts/fetch_circuit.py first.");
        }
      })
      .catch((err: Error) => setLoadError(`Backend not reachable: ${err.message}`));
  }, []);

  useEffect(() => {
    if (circuitName === null) {
      return;
    }
    api
      .circuit(circuitName)
      .then((value) => {
        setData(value);
        setSettings(defaultRunSettings(value));
      })
      .catch((err: Error) => setLoadError(err.message));
  }, [circuitName]);

  // Playback: advance biological time at `speed` × real time.
  useEffect(() => {
    if (!playing || sim === null) {
      return;
    }
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const elapsed = now - last;
      last = now;
      let stop = false;
      setTime((current) => {
        const next = current + elapsed * speed;
        if (next >= sim.duration_ms) {
          stop = true;
          return sim.duration_ms;
        }
        return next;
      });
      if (stop) {
        setPlaying(false);
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, sim, speed]);

  const activity = useMemo(() => {
    if (sim === null || tab !== "simulate" || (time === 0 && !playing)) {
      return null;
    }
    return activityAt(sim, time);
  }, [sim, time, playing, tab]);

  /** Switch circuits: reset everything tied to the old circuit, then load the new one. */
  const changeCircuit = (name: string) => {
    setData(null);
    setSim(null);
    setSelected(null);
    setHighlight(null);
    setAblated(new Set());
    setPlaying(false);
    setCircuitName(name);
  };

  const toggleAblate = useCallback(
    (index: number) => {
      const next = new Set(ablated);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      setAblated(next);
    },
    [ablated],
  );

  const handleNodeClick = useCallback(
    (index: number) => {
      if (clickToAblate) {
        toggleAblate(index);
        return;
      }
      setSelected(index);
      setTab("neuron");
    },
    [clickToAblate, toggleAblate],
  );

  const simulatePath = (path: PathOut, level: PathLevel) => {
    if (settings === null) {
      return;
    }
    const first = path.nodes[0];
    let targets: NeuronSet = { types: [first.type], instances: [], body_ids: [], roles: [] };
    if (level === "neuron" && first.body_id !== null) {
      targets = { types: [], instances: [], body_ids: [first.body_id], roles: [] };
    }
    setSettings({ ...settings, stimulus: { ...settings.stimulus, targets } });
    const types: string[] = [];
    for (const node of path.nodes) {
      if (!types.includes(node.type)) {
        types.push(node.type);
      }
    }
    setExtraPsthTypes(types);
    setTab("simulate");
  };

  if (loadError !== null) {
    return <div className="fatal">{loadError}</div>;
  }
  if (data === null || settings === null || circuitName === null) {
    return <div className="fatal">Loading circuit…</div>;
  }

  const ntMissing = data.warnings.some((w) => w.includes("NO NEUROTRANSMITTER"));
  let ntBanner = null;
  if (ntMissing) {
    ntBanner = (
      <div className="banner-danger">
        No neurotransmitter predictions in this dataset: synaptic signs come from the config's fallback table
        only. Inhibition in this model is unreliable.
      </div>
    );
  }
  let warningList = null;
  if (showWarnings) {
    warningList = (
      <div className="warning-popover">
        <ul>
          {data.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
        <p className="muted small">See docs/ASSUMPTIONS.md for all modelling assumptions.</p>
      </div>
    );
  }

  let panel = null;
  if (tab === "neuron") {
    panel = (
      <NeuronPanel
        circuit={circuitName}
        data={data}
        selected={selected}
        ablated={ablated}
        onSelect={setSelected}
        onToggleAblate={toggleAblate}
        onHighlight={setHighlight}
      />
    );
  } else if (tab === "simulate") {
    panel = (
      <SimulationPanel
        circuit={circuitName}
        data={data}
        settings={settings}
        onSettings={setSettings}
        useExtraEdges={useExtraEdges}
        ablated={ablated}
        sim={sim}
        onSim={setSim}
        time={time}
        onTime={setTime}
        playing={playing}
        onPlaying={setPlaying}
        speed={speed}
        onSpeed={setSpeed}
        extraPsthTypes={extraPsthTypes}
        onSelectNeuron={(index) => {
          setSelected(index);
          setTab("neuron");
        }}
      />
    );
  } else if (tab === "paths") {
    panel = (
      <PathPanel circuit={circuitName} data={data} onHighlight={setHighlight} onSimulatePath={simulatePath} />
    );
  } else if (tab === "query") {
    panel = (
      <QueryPanel
        circuit={circuitName}
        data={data}
        onHighlight={setHighlight}
        onSelect={(index) => {
          setSelected(index);
          setTab("neuron");
        }}
      />
    );
  } else {
    panel = (
      <LesionPanel
        circuit={circuitName}
        data={data}
        settings={settings}
        onSettings={setSettings}
        useExtraEdges={useExtraEdges}
        ablated={ablated}
        onAblated={setAblated}
        clickToAblate={clickToAblate}
        onClickToAblate={setClickToAblate}
        onHighlight={setHighlight}
      />
    );
  }

  let extraEdgeNote = null;
  if (useExtraEdges) {
    extraEdgeNote = (
      <span
        className="assumption-tag"
        title="GF→TTMn and GF→PSI gap junctions from the literature; not in the EM data"
      >
        assumption active
      </span>
    );
  }

  let clearHighlightButton = null;
  if (highlight !== null) {
    clearHighlightButton = (
      <button className="graph-overlay-button" onClick={() => setHighlight(null)}>
        ✕ clear highlight ({highlight.nodes.size} neurons)
      </button>
    );
  }

  return (
    <div className="app">
      <header>
        <h1>Connectome Circuit Explorer</h1>
        <select value={circuitName} onChange={(e) => changeCircuit(e.target.value)}>
          {circuits.map((c) => (
            <option key={c.name} value={c.name} disabled={!c.available}>
              {c.name}
            </option>
          ))}
        </select>
        <span className="muted">
          {data.body_ids.length.toLocaleString()} neurons · {data.edge_pre.length.toLocaleString()} edges ·{" "}
          {String(data.manifest["dataset"])}
        </span>
        <label
          className="check"
          title="Literature-based electrical synapses. NOT connectome data (see ASSUMPTIONS.md)."
        >
          <input
            type="checkbox"
            checked={useExtraEdges}
            onChange={(e) => setUseExtraEdges(e.target.checked)}
          />
          electrical synapses ({data.extra_edge_pre.length})
        </label>
        {extraEdgeNote}
        <label className="field-inline">
          colour
          <select value={colorBy} onChange={(e) => setColorBy(e.target.value as ColorBy)}>
            <option value="role">role</option>
            <option value="type">cell type</option>
          </select>
        </label>
        <label
          className="field-inline"
          title="Edges with fewer synapses are hidden in the graph (they are still simulated)"
        >
          edges ≥ {minEdgeWeight} syn
          <input
            type="range"
            min={10}
            max={200}
            step={5}
            value={minEdgeWeight}
            onChange={(e) => setMinEdgeWeight(Number(e.target.value))}
          />
        </label>
        <button className="warning-button" onClick={() => setShowWarnings(!showWarnings)}>
          ⚠ {data.warnings.length} model warnings
        </button>
        {warningList}
      </header>
      {ntBanner}
      <main>
        <section className="graph-area">
          <GraphView
            data={data}
            colorBy={colorBy}
            minEdgeWeight={minEdgeWeight}
            showExtraEdges={useExtraEdges}
            selected={selected}
            highlight={highlight}
            ablated={ablated}
            activity={activity}
            onNodeClick={handleNodeClick}
            onStageClick={() => setSelected(null)}
          />
          {clearHighlightButton}
        </section>
        <div
          className="aside-resizer"
          onPointerDown={startResize}
          onDoubleClick={() => setAsideWidth(ASIDE_DEFAULT)}
          title="Drag to resize the panel (double-click to reset)"
        />
        <aside style={{ width: asideWidth }}>
          <nav className="tabs">
            {TABS.map((t) => {
              let className = "tab";
              if (t.id === tab) {
                className = "tab tab-active";
              }
              return (
                <button key={t.id} className={className} onClick={() => setTab(t.id)}>
                  {t.label}
                </button>
              );
            })}
          </nav>
          <div className="panel-scroll">{panel}</div>
        </aside>
      </main>
    </div>
  );
}
