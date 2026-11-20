"""Application service: caches circuits, networks, path graphs, baselines and screen jobs.

The API layer is a thin wrapper around this class, so everything here is testable
without HTTP.
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from connectome_app.analysis import psth, type_rate_table
from connectome_app.config import list_configs, load_config
from connectome_app.data import Circuit, load_circuit
from connectome_app.layout import load_or_flow_layout
from connectome_app.lesion import (
    BaselineCache,
    RunSettings,
    ScreenCandidate,
    lesion_screen,
    run_lesion,
)
from connectome_app.lif import LIFNetwork
from connectome_app.paths import PathGraph, build_neuron_graph, build_type_graph, k_shortest_paths
from connectome_app.schemas import (
    CircuitData,
    CircuitSummary,
    LesionRequest,
    LesionResponse,
    NeuronDetail,
    NeuronSet,
    Partner,
    PathNode,
    PathOut,
    PathRequest,
    PathResponse,
    Psth,
    RunSpec,
    ScreenRequest,
    ScreenStatus,
    SimulateRequest,
    SimulateResponse,
    TypeRate,
    TypeSummary,
)
from connectome_app.stats import P_VALUE_NOTE
from connectome_app.stimulus import Stimulus

VOLTAGE_SAMPLE_MS = 1.0


def clean(value: object) -> object:
    """Make a value JSON-safe: NaN/inf -> None, numpy scalars -> Python, tuples -> lists."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return [clean(v) for v in value.tolist()]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if math.isfinite(number):
            return number
        return None
    return value


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


@dataclass
class ScreenJob:
    job_id: str
    total: int = 0
    done: int = 0
    status: str = "queued"
    started: float = field(default_factory=time.time)
    finished: float | None = None
    results: list[dict] | None = None
    skipped: list[str] = field(default_factory=list)
    error: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)


class Service:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._circuits: dict[str, Circuit] = {}
        self._networks: dict[tuple[str, bool], LIFNetwork] = {}
        self._graphs: dict[tuple[str, str, str], PathGraph] = {}
        self._baselines = BaselineCache()
        self._jobs: dict[str, ScreenJob] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="screen")

    # ---------- caches ----------

    def register_circuit(self, circuit: Circuit) -> None:
        """Add an already-loaded circuit (used by tests and notebooks)."""
        with self._lock:
            self._circuits[circuit.config.name] = circuit

    def circuit(self, name: str) -> Circuit:
        with self._lock:
            if name not in self._circuits:
                self._circuits[name] = load_circuit(name)
            return self._circuits[name]

    def network(self, name: str, use_extra_edges: bool) -> LIFNetwork:
        circuit = self.circuit(name)
        key = (name, use_extra_edges)
        with self._lock:
            if key not in self._networks:
                self._networks[key] = LIFNetwork.from_circuit(circuit, use_extra_edges=use_extra_edges)
            return self._networks[key]

    def graph(self, name: str, level: str, normalization: str) -> PathGraph:
        circuit = self.circuit(name)
        key = (name, level, normalization)
        with self._lock:
            if key not in self._graphs:
                if level == "type":
                    self._graphs[key] = build_type_graph(circuit, normalization)
                else:
                    self._graphs[key] = build_neuron_graph(circuit, normalization)
            return self._graphs[key]

    # ---------- helpers ----------

    @staticmethod
    def resolve(circuit: Circuit, neuron_set: NeuronSet) -> np.ndarray:
        parts = [circuit.select(neuron_set.types, neuron_set.body_ids)]
        if neuron_set.instances:
            parts.append(circuit.indices_of_instances(neuron_set.instances))
        for role in neuron_set.roles:
            parts.append(circuit.indices_of_role(role))
        return np.unique(np.concatenate(parts)).astype(np.int64)

    def settings(self, circuit: Circuit, spec: RunSpec) -> RunSettings:
        stim_spec = spec.stimulus
        targets = self.resolve(circuit, stim_spec.targets)
        stimulus = Stimulus(
            targets=targets,
            profile=stim_spec.profile,
            rate_hz=stim_spec.rate_hz,
            baseline_hz=stim_spec.baseline_hz,
            start_ms=stim_spec.start_ms,
            end_ms=stim_spec.end_ms,
            mode=stim_spec.mode,
            synaptic_weight_mv=stim_spec.synaptic_weight_mv,
        )
        base_seed = spec.base_seed
        if base_seed is None:
            base_seed = circuit.config.simulation.base_seed
        return RunSettings(spec.duration_ms, spec.n_trials, base_seed, stimulus)

    def _baseline(self, name: str, spec: RunSpec, settings: RunSettings) -> tuple:
        network = self.network(name, spec.use_extra_edges)
        before = len(self._baselines)
        baseline = self._baselines.get((name, spec.use_extra_edges), network, settings)
        was_cached = len(self._baselines) == before
        return network, baseline, was_cached

    # ---------- circuit info ----------

    def list_circuits(self) -> list[CircuitSummary]:
        out: list[CircuitSummary] = []
        for name in list_configs():
            config = load_config(name)
            available = (config.data_dir() / "neurons.parquet").exists()
            summary = CircuitSummary(name=name, description=config.description.strip(), available=available)
            if available:
                circuit = self.circuit(name)
                summary.n_neurons = circuit.n_neurons
                summary.n_edges = int(circuit.weights.nnz)
            out.append(summary)
        return out

    def circuit_data(self, name: str) -> CircuitData:
        circuit = self.circuit(name)
        neurons = circuit.neurons
        coo = circuit.weights.tocoo()
        type_frame = neurons.groupby("type").agg(role=("role", "first"), n=("body_id", "size")).reset_index()
        type_summary = [
            TypeSummary(type=str(r.type), role=str(r.role), n_neurons=int(r.n))
            for r in type_frame.itertuples()
        ]
        extra = circuit.extra_edges
        layout = load_or_flow_layout(circuit)
        return CircuitData(
            name=circuit.config.name,
            description=circuit.config.description.strip(),
            manifest=clean(circuit.manifest),
            warnings=circuit.warnings,
            body_ids=[int(b) for b in neurons["body_id"]],
            types=[_text(t) for t in neurons["type"]],
            instances=[_text(t) for t in neurons.get("instance", pd.Series([""] * len(neurons)))],
            roles=[str(r) for r in neurons["role"]],
            soma_sides=[_text(s) for s in neurons.get("soma_side", pd.Series([""] * len(neurons)))],
            nts=[_text(n) for n in neurons.get("consensus_nt", pd.Series([""] * len(neurons)))],
            signs=[int(s) for s in circuit.signs],
            sign_sources=[str(s) for s in neurons["sign_source"]],
            x=[float(v) for v in layout["x"]],
            y=[float(v) for v in layout["y"]],
            edge_pre=coo.col.astype(int).tolist(),
            edge_post=coo.row.astype(int).tolist(),
            edge_weight=coo.data.astype(int).tolist(),
            extra_edge_pre=[int(v) for v in extra["pre_index"]],
            extra_edge_post=[int(v) for v in extra["post_index"]],
            extra_edge_weight=[float(v) for v in extra["synapse_equivalent"]],
            type_summary=type_summary,
            simulation_defaults=circuit.config.simulation.model_dump(),
        )

    def neuron_detail(self, name: str, body_id: int, top: int = 10) -> NeuronDetail:
        """Identity, sign provenance and the strongest partners (`top` <= 0 returns all)."""
        circuit = self.circuit(name)
        index = circuit.index_of(body_id)
        row = circuit.neurons.iloc[index]
        incoming = circuit.weights.getrow(index).tocoo()
        outgoing = circuit.weights_csc.getcol(index).tocoo()
        return NeuronDetail(
            body_id=int(body_id),
            index=int(index),
            type=_text(row["type"]),
            instance=_text(row.get("instance")),
            role=str(row["role"]),
            soma_side=_text(row.get("soma_side")),
            consensus_nt=_text(row.get("consensus_nt")),
            sign=int(row["sign"]),
            sign_source=str(row["sign_source"]),
            total_post=_optional_int(row.get("total_post")),
            total_pre=_optional_int(row.get("total_pre")),
            in_degree=int(incoming.nnz),
            out_degree=int(outgoing.nnz),
            in_synapses=int(incoming.data.sum()),
            out_synapses=int(outgoing.data.sum()),
            top_inputs=self._partners(circuit, incoming.col, incoming.data, top),
            top_outputs=self._partners(circuit, outgoing.row, outgoing.data, top),
        )

    @staticmethod
    def _partners(circuit: Circuit, indices: np.ndarray, weights: np.ndarray, top: int) -> list[Partner]:
        order = np.argsort(-weights, kind="stable")
        if top > 0:
            order = order[:top]
        partners: list[Partner] = []
        for k in order:
            i = int(indices[k])
            partners.append(
                Partner(
                    body_id=int(circuit.neurons.at[i, "body_id"]),
                    index=i,
                    type=_text(circuit.neurons.at[i, "type"]),
                    instance=_instance_text(circuit, i),
                    synapses=int(weights[k]),
                    sign=int(circuit.signs[i]),
                )
            )
        return partners

    # ---------- simulation ----------

    def simulate(self, request: SimulateRequest) -> SimulateResponse:
        circuit = self.circuit(request.circuit)
        network = self.network(request.circuit, request.use_extra_edges)
        settings = self.settings(circuit, request)
        alive = None
        if request.lesion is not None:
            alive = np.ones(circuit.n_neurons, dtype=bool)
            alive[self.resolve(circuit, request.lesion)] = False
        record = np.array([circuit.index_of(b) for b in request.record_body_ids], dtype=np.int64)

        started = time.perf_counter()
        result = network.run(
            settings.duration_ms,
            settings.seeds(),
            stimulus=settings.stimulus,
            alive=alive,
            record_indices=record,
        )
        elapsed = time.perf_counter() - started

        raster_trial = min(request.raster_trial, request.n_trials - 1)
        in_trial = result.spike_columns == raster_trial
        times = result.spike_times_ms[in_trial]
        neurons = result.spike_neurons[in_trial]
        truncated = len(times) > request.max_raster_spikes
        if truncated:
            times = times[: request.max_raster_spikes]
            neurons = neurons[: request.max_raster_spikes]

        table = type_rate_table(result, circuit.neurons)
        type_rates = [
            TypeRate(
                type=str(r.type),
                role=str(r.role),
                n_neurons=int(r.n_neurons),
                mean_rate_hz=float(r.mean_rate_hz),
                std_over_trials_hz=float(r.std_over_trials_hz),
                fraction_active=float(r.fraction_active),
            )
            for r in table.itertuples()
        ]
        groups = self._psth_groups(circuit, table, request.psth_types, request.max_psth_types)
        bins, curves = psth(result, groups, request.bin_ms)

        voltage: dict[str, list[float]] = {}
        voltage_times: list[float] = []
        if result.voltage is not None:
            stride = max(1, int(round(VOLTAGE_SAMPLE_MS / result.dt_ms)))
            voltage_times = (np.arange(0, result.n_steps, stride) * result.dt_ms).tolist()
            for slot, body_id in enumerate(request.record_body_ids):
                trace = result.voltage[::stride, slot, raster_trial]
                voltage[str(body_id)] = [float(v) for v in trace]

        return SimulateResponse(
            duration_ms=result.duration_ms,
            dt_ms=result.dt_ms,
            n_trials=request.n_trials,
            seeds=[int(s) for s in settings.seeds()],
            raster_trial=raster_trial,
            raster_times_ms=times.tolist(),
            raster_neurons=neurons.astype(int).tolist(),
            raster_truncated=bool(truncated),
            total_spikes=int(len(result.spike_steps)),
            type_rates=type_rates,
            psth=Psth(bin_ms=request.bin_ms, bin_starts_ms=bins.tolist(), groups=clean(curves)),
            voltage_times_ms=voltage_times,
            voltage=voltage,
            elapsed_s=round(elapsed, 3),
            warnings=list(circuit.warnings),
        )

    @staticmethod
    def _psth_groups(
        circuit: Circuit, table: pd.DataFrame, requested: list[str], max_types: int
    ) -> dict[str, np.ndarray]:
        groups: dict[str, np.ndarray] = {}
        for role in ("input", "hub", "output", "interneuron"):
            indices = circuit.indices_of_role(role)
            if len(indices) > 0:
                groups[f"role:{role}"] = indices
        chosen: list[str] = list(requested)
        for role in ("hub", "output"):
            chosen.extend(table.loc[table["role"] == role, "type"].tolist())
        active = table.loc[table["mean_rate_hz"] > 0, "type"].tolist()
        for name in active:
            if len(chosen) >= max_types + len(requested):
                break
            chosen.append(name)
        for name in chosen:
            if name not in groups:
                groups[name] = circuit.indices_of_types([name])
        return groups

    # ---------- paths ----------

    def paths(self, request: PathRequest) -> PathResponse:
        circuit = self.circuit(request.circuit)
        normalization = request.normalization
        if normalization is None:
            normalization = circuit.config.path_finder.normalization
        graph = self.graph(request.circuit, request.level, normalization)
        sources = self.resolve(circuit, request.sources)
        targets = self.resolve(circuit, request.targets)
        if request.level == "type":
            sources = self._type_nodes(circuit, graph, sources)
            targets = self._type_nodes(circuit, graph, targets)
        result = k_shortest_paths(
            graph,
            sources,
            targets,
            k=request.k,
            max_hops=request.max_hops,
            sign_filter=request.sign_filter,
            min_synapses=request.min_synapses,
        )
        paths_out: list[PathOut] = []
        for found in result.paths:
            nodes = [
                PathNode(
                    label=graph.labels[n],
                    type=graph.node_types[n],
                    body_id=graph.node_body_ids[n],
                    index=int(n),
                )
                for n in found.nodes
            ]
            paths_out.append(
                PathOut(
                    nodes=nodes,
                    synapses=found.synapses,
                    shares=found.shares,
                    score=found.score,
                    cost=found.cost,
                    hops=found.hops,
                    sign=found.sign,
                )
            )
        return PathResponse(
            level=request.level,
            normalization=normalization,
            paths=paths_out,
            truncated=result.truncated,
            expansions=result.expansions,
        )

    @staticmethod
    def _type_nodes(circuit: Circuit, graph: PathGraph, indices: np.ndarray) -> np.ndarray:
        position = {name: i for i, name in enumerate(graph.labels)}
        names = set(circuit.neurons["type"].iloc[indices].tolist())
        return np.array(sorted(position[n] for n in names), dtype=np.int64)

    # ---------- lesions ----------

    def default_output_groups(self, circuit: Circuit) -> dict[str, np.ndarray]:
        groups: dict[str, np.ndarray] = {"all outputs": circuit.indices_of_role("output")}
        for cell_type in circuit.config.selection.hubs + circuit.config.selection.outputs:
            indices = circuit.indices_of_types([cell_type])
            if len(indices) > 0:
                groups[cell_type] = indices
        return groups

    def lesion(self, request: LesionRequest) -> LesionResponse:
        circuit = self.circuit(request.circuit)
        settings = self.settings(circuit, request)
        network, baseline, was_cached = self._baseline(request.circuit, request, settings)
        ablate = self.resolve(circuit, request.lesion)
        if request.output_groups:
            groups = {g.name: self.resolve(circuit, g.neurons) for g in request.output_groups}
        else:
            groups = self.default_output_groups(circuit)
        outcome = run_lesion(network, baseline, settings, ablate, groups, request.bin_ms)
        warnings = list(circuit.warnings)
        if len(ablate) == 0:
            warnings.append("Lesion set is empty: nothing was ablated.")
        bins = outcome.bin_starts_ms.tolist()
        return LesionResponse(
            n_ablated=int(len(ablate)),
            ablated_body_ids=[int(circuit.neurons.at[int(i), "body_id"]) for i in ablate],
            metrics=clean(outcome.metrics),
            psth_baseline=Psth(
                bin_ms=request.bin_ms, bin_starts_ms=bins, groups=clean(outcome.psth_baseline)
            ),
            psth_lesion=Psth(bin_ms=request.bin_ms, bin_starts_ms=bins, groups=clean(outcome.psth_lesion)),
            p_value_note=P_VALUE_NOTE,
            baseline_cached=was_cached,
            warnings=warnings,
        )

    # ---------- screens ----------

    def start_screen(self, request: ScreenRequest) -> ScreenStatus:
        circuit = self.circuit(request.circuit)
        job = ScreenJob(job_id=uuid.uuid4().hex[:12])
        with self._lock:
            self._jobs[job.job_id] = job
        self._executor.submit(self._run_screen, job, request, circuit)
        return self.screen_status(job.job_id)

    def _screen_candidates(self, circuit: Circuit, request: ScreenRequest) -> list[ScreenCandidate]:
        candidates: list[ScreenCandidate] = []
        if request.level == "type":
            names = request.candidates
            if names is None:
                names = sorted(circuit.neurons["type"].unique().tolist())
            for name in names:
                candidates.append(ScreenCandidate(label=name, indices=circuit.indices_of_types([name])))
            return candidates
        if request.candidates is None:
            body_ids = [int(b) for b in circuit.neurons["body_id"]]
        else:
            body_ids = [int(b) for b in request.candidates]
        for body_id in body_ids:
            index = circuit.index_of(body_id)
            label = f"{circuit.neurons.at[index, 'type']} ({body_id})"
            candidates.append(ScreenCandidate(label=label, indices=np.array([index], dtype=np.int64)))
        return candidates

    def _run_screen(self, job: ScreenJob, request: ScreenRequest, circuit: Circuit) -> None:
        job.status = "running"
        job.started = time.time()
        try:
            settings = self.settings(circuit, request)
            network, baseline, _ = self._baseline(request.circuit, request, settings)
            measure = self.resolve(circuit, request.measure)
            if len(measure) == 0:
                raise ValueError("The measured group is empty")

            def progress(done: int, total: int) -> None:
                job.done = done
                job.total = total

            outcome = lesion_screen(
                network,
                baseline,
                settings,
                self._screen_candidates(circuit, request),
                measure,
                metric=request.metric,
                rank_by=request.rank_by,
                max_columns=request.max_columns,
                progress=progress,
                should_stop=job.cancel.is_set,
            )
            job.results = clean(outcome.table.to_dict(orient="records"))
            job.skipped = outcome.skipped
            if job.cancel.is_set():
                job.status = "cancelled"
            else:
                job.status = "done"
        except Exception as error:  # surfaced to the client through the status endpoint
            job.status = "error"
            job.error = f"{type(error).__name__}: {error}"
        finally:
            job.finished = time.time()

    def screen_status(self, job_id: str) -> ScreenStatus:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown screen job {job_id}")
            job = self._jobs[job_id]
        end = job.finished
        if end is None:
            end = time.time()
        return ScreenStatus(
            job_id=job.job_id,
            status=job.status,
            done=job.done,
            total=job.total,
            elapsed_s=round(end - job.started, 1),
            results=job.results,
            skipped=job.skipped,
            error=job.error,
            p_value_note=P_VALUE_NOTE,
        )

    def cancel_screen(self, job_id: str) -> ScreenStatus:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown screen job {job_id}")
            self._jobs[job_id].cancel.set()
        return self.screen_status(job_id)


def _instance_text(circuit: Circuit, index: int) -> str:
    """Instance label of one neuron, or an empty string when the column is missing."""
    if "instance" not in circuit.neurons.columns:
        return ""
    return _text(circuit.neurons.at[index, "instance"])


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    return int(value)
