"""Typed request/response schemas for the REST API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NeuronSet(BaseModel):
    """A union of cell types, instances (e.g. "LB3c_L"), bodyIds and roles."""

    types: list[str] = Field(default_factory=list)
    instances: list[str] = Field(default_factory=list)
    body_ids: list[int] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)


class StimulusSpec(BaseModel):
    targets: NeuronSet = Field(default_factory=lambda: NeuronSet(roles=["input"]))
    profile: Literal["constant", "step", "ramp"] = "ramp"
    rate_hz: float = Field(default=100.0, ge=0, le=5000)
    baseline_hz: float = Field(default=0.0, ge=0, le=5000)
    start_ms: float = Field(default=0.0, ge=0)
    end_ms: float | None = None
    mode: Literal["spikes", "synaptic"] = "spikes"
    synaptic_weight_mv: float = 10.0


class RunSpec(BaseModel):
    circuit: str
    stimulus: StimulusSpec = Field(default_factory=StimulusSpec)
    duration_ms: float = Field(default=1000.0, gt=0, le=10000)
    n_trials: int = Field(default=10, ge=1, le=200)
    base_seed: int | None = None
    use_extra_edges: bool = False


# ---------- circuit ----------


class TypeSummary(BaseModel):
    type: str
    role: str
    n_neurons: int


class CircuitSummary(BaseModel):
    name: str
    description: str
    available: bool
    n_neurons: int | None = None
    n_edges: int | None = None


class CircuitData(BaseModel):
    """Columnar arrays: index i in every neuron list refers to the same neuron."""

    name: str
    description: str
    manifest: dict
    warnings: list[str]
    body_ids: list[int]
    types: list[str]
    instances: list[str]
    roles: list[str]
    soma_sides: list[str]
    nts: list[str]
    signs: list[int]
    sign_sources: list[str]
    x: list[float]
    y: list[float]
    edge_pre: list[int]
    edge_post: list[int]
    edge_weight: list[int]
    extra_edge_pre: list[int]
    extra_edge_post: list[int]
    extra_edge_weight: list[float]
    type_summary: list[TypeSummary]
    simulation_defaults: dict


class Partner(BaseModel):
    body_id: int
    index: int
    type: str
    instance: str
    synapses: int
    sign: int


class NeuronDetail(BaseModel):
    body_id: int
    index: int
    type: str
    instance: str
    role: str
    soma_side: str
    consensus_nt: str
    sign: int
    sign_source: str
    total_post: int | None
    total_pre: int | None
    in_degree: int
    out_degree: int
    in_synapses: int
    out_synapses: int
    top_inputs: list[Partner]
    top_outputs: list[Partner]


# ---------- simulation ----------


class SimulateRequest(RunSpec):
    lesion: NeuronSet | None = None
    record_body_ids: list[int] = Field(default_factory=list, max_length=50)
    bin_ms: float = Field(default=10.0, gt=0)
    raster_trial: int = Field(default=0, ge=0)
    max_raster_spikes: int = Field(default=300_000, ge=1)
    psth_types: list[str] = Field(default_factory=list)
    max_psth_types: int = Field(default=40, ge=0)


class TypeRate(BaseModel):
    type: str
    role: str
    n_neurons: int
    mean_rate_hz: float
    std_over_trials_hz: float
    fraction_active: float


class Psth(BaseModel):
    bin_ms: float
    bin_starts_ms: list[float]
    groups: dict[str, list[float]]


class SimulateResponse(BaseModel):
    duration_ms: float
    dt_ms: float
    n_trials: int
    seeds: list[int]
    raster_trial: int
    raster_times_ms: list[float]
    raster_neurons: list[int]
    raster_truncated: bool
    total_spikes: int
    type_rates: list[TypeRate]
    psth: Psth
    voltage_times_ms: list[float]
    voltage: dict[str, list[float]]
    elapsed_s: float
    warnings: list[str]


# ---------- paths ----------


class PathRequest(BaseModel):
    circuit: str
    sources: NeuronSet
    targets: NeuronSet
    k: int = Field(default=10, ge=1, le=200)
    max_hops: int = Field(default=4, ge=1, le=8)
    sign_filter: Literal["any", "excitatory", "inhibitory"] = "any"
    level: Literal["neuron", "type"] = "neuron"
    normalization: Literal["post", "input_weight"] | None = None
    min_synapses: int = Field(default=1, ge=1)


class PathNode(BaseModel):
    label: str
    type: str
    body_id: int | None
    index: int


class PathOut(BaseModel):
    nodes: list[PathNode]
    synapses: list[int]
    shares: list[float]
    score: float
    cost: float
    hops: int
    sign: int


class PathResponse(BaseModel):
    level: str
    normalization: str
    paths: list[PathOut]
    truncated: bool
    expansions: int


# ---------- lesions ----------


class NamedGroup(BaseModel):
    name: str
    neurons: NeuronSet


class LesionRequest(RunSpec):
    lesion: NeuronSet
    output_groups: list[NamedGroup] = Field(default_factory=list)
    bin_ms: float = Field(default=10.0, gt=0)


class LesionResponse(BaseModel):
    n_ablated: int
    ablated_body_ids: list[int]
    metrics: list[dict]
    psth_baseline: Psth
    psth_lesion: Psth
    p_value_note: str
    baseline_cached: bool
    warnings: list[str]


class ScreenRequest(RunSpec):
    level: Literal["type", "neuron"] = "type"
    candidates: list[str] | None = None
    measure: NeuronSet = Field(default_factory=lambda: NeuronSet(roles=["output"]))
    metric: Literal["spike_count", "rate_hz", "first_spike_ms"] = "spike_count"
    rank_by: Literal["percent_change", "cohens_d", "mean_difference"] = "percent_change"
    max_columns: int = Field(default=200, ge=1, le=2000)
    duration_ms: float = Field(default=300.0, gt=0, le=5000)
    n_trials: int = Field(default=5, ge=2, le=50)


class ScreenStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error", "cancelled"]
    done: int
    total: int
    elapsed_s: float
    results: list[dict] | None = None
    skipped: list[str] = Field(default_factory=list)
    error: str | None = None
    p_value_note: str
