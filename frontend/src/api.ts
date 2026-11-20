// Typed client for the FastAPI backend. Types mirror backend/connectome_app/schemas.py.

export interface NeuronSet {
  types: string[];
  instances: string[];
  body_ids: number[];
  roles: string[];
}

export type Profile = "constant" | "step" | "ramp";
export type StimulusMode = "spikes" | "synaptic";

export interface StimulusSpec {
  targets: NeuronSet;
  profile: Profile;
  rate_hz: number;
  baseline_hz: number;
  start_ms: number;
  end_ms: number | null;
  mode: StimulusMode;
  synaptic_weight_mv: number;
}

export interface RunSpec {
  circuit: string;
  stimulus: StimulusSpec;
  duration_ms: number;
  n_trials: number;
  base_seed: number | null;
  use_extra_edges: boolean;
}

export interface CircuitSummary {
  name: string;
  description: string;
  available: boolean;
  n_neurons: number | null;
  n_edges: number | null;
}

export interface TypeSummary {
  type: string;
  role: string;
  n_neurons: number;
}

export interface CircuitData {
  name: string;
  description: string;
  manifest: Record<string, unknown>;
  warnings: string[];
  body_ids: number[];
  types: string[];
  instances: string[];
  roles: string[];
  soma_sides: string[];
  nts: string[];
  signs: number[];
  sign_sources: string[];
  x: number[];
  y: number[];
  edge_pre: number[];
  edge_post: number[];
  edge_weight: number[];
  extra_edge_pre: number[];
  extra_edge_post: number[];
  extra_edge_weight: number[];
  type_summary: TypeSummary[];
  simulation_defaults: Record<string, number>;
}

export interface Partner {
  body_id: number;
  index: number;
  type: string;
  instance: string;
  synapses: number;
  sign: number;
}

export interface NeuronDetail {
  body_id: number;
  index: number;
  type: string;
  instance: string;
  role: string;
  soma_side: string;
  consensus_nt: string;
  sign: number;
  sign_source: string;
  total_post: number | null;
  total_pre: number | null;
  in_degree: number;
  out_degree: number;
  in_synapses: number;
  out_synapses: number;
  top_inputs: Partner[];
  top_outputs: Partner[];
}

export interface SimulateRequest extends RunSpec {
  lesion: NeuronSet | null;
  record_body_ids: number[];
  bin_ms: number;
  raster_trial: number;
  max_raster_spikes: number;
  psth_types: string[];
  max_psth_types: number;
}

export interface TypeRate {
  type: string;
  role: string;
  n_neurons: number;
  mean_rate_hz: number;
  std_over_trials_hz: number;
  fraction_active: number;
}

export interface Psth {
  bin_ms: number;
  bin_starts_ms: number[];
  groups: Record<string, (number | null)[]>;
}

export interface SimulateResponse {
  duration_ms: number;
  dt_ms: number;
  n_trials: number;
  seeds: number[];
  raster_trial: number;
  raster_times_ms: number[];
  raster_neurons: number[];
  raster_truncated: boolean;
  total_spikes: number;
  type_rates: TypeRate[];
  psth: Psth;
  voltage_times_ms: number[];
  voltage: Record<string, number[]>;
  elapsed_s: number;
  warnings: string[];
}

export type SignFilter = "any" | "excitatory" | "inhibitory";
export type PathLevel = "neuron" | "type";

export interface PathRequest {
  circuit: string;
  sources: NeuronSet;
  targets: NeuronSet;
  k: number;
  max_hops: number;
  sign_filter: SignFilter;
  level: PathLevel;
  normalization: "post" | "input_weight" | null;
  min_synapses: number;
}

export interface PathNode {
  label: string;
  type: string;
  body_id: number | null;
  index: number;
}

export interface PathOut {
  nodes: PathNode[];
  synapses: number[];
  shares: number[];
  score: number;
  cost: number;
  hops: number;
  sign: number;
}

export interface PathResponse {
  level: PathLevel;
  normalization: string;
  paths: PathOut[];
  truncated: boolean;
  expansions: number;
}

export interface NamedGroup {
  name: string;
  neurons: NeuronSet;
}

export interface LesionRequest extends RunSpec {
  lesion: NeuronSet;
  output_groups: NamedGroup[];
  bin_ms: number;
}

export type Metric = "spike_count" | "rate_hz" | "first_spike_ms";

export interface MetricRow {
  group: string;
  metric: Metric;
  n_neurons: number;
  n_ablated_in_group: number;
  responded_baseline: number;
  responded_lesion: number;
  comparison_valid: boolean;
  n_trials: number;
  baseline_mean: number | null;
  baseline_std?: number | null;
  lesion_mean: number | null;
  lesion_std?: number | null;
  mean_difference?: number | null;
  mean_difference_ci?: (number | null)[];
  percent_change?: number | null;
  cohens_d: number | null;
  cohens_d_ci?: (number | null)[];
  p_value_wilcoxon?: number | null;
}

export interface LesionResponse {
  n_ablated: number;
  ablated_body_ids: number[];
  metrics: MetricRow[];
  psth_baseline: Psth;
  psth_lesion: Psth;
  p_value_note: string;
  baseline_cached: boolean;
  warnings: string[];
}

export interface ScreenRequest extends RunSpec {
  level: "type" | "neuron";
  candidates: string[] | null;
  measure: NeuronSet;
  metric: Metric;
  rank_by: "percent_change" | "cohens_d" | "mean_difference";
  max_columns: number;
}

export interface ScreenRow extends Omit<MetricRow, "group" | "metric" | "n_neurons" | "n_ablated_in_group"> {
  label: string;
  n_ablated: number;
}

export interface ScreenStatus {
  job_id: string;
  status: "queued" | "running" | "done" | "error" | "cancelled";
  done: number;
  total: number;
  elapsed_s: number;
  results: ScreenRow[] | null;
  skipped: string[];
  error: string | null;
  p_value_note: string;
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = JSON.stringify(payload.detail);
    } catch {
      // keep statusText
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

export const api = {
  circuits: () => request<CircuitSummary[]>("GET", "/api/circuits"),
  circuit: (name: string) => request<CircuitData>("GET", `/api/circuits/${encodeURIComponent(name)}`),
  /** `top` = 0 returns every partner. */
  neuron: (name: string, bodyId: number, top: number) =>
    request<NeuronDetail>("GET", `/api/circuits/${encodeURIComponent(name)}/neurons/${bodyId}?top=${top}`),
  simulate: (body: SimulateRequest) => request<SimulateResponse>("POST", "/api/simulate", body),
  paths: (body: PathRequest) => request<PathResponse>("POST", "/api/paths", body),
  lesion: (body: LesionRequest) => request<LesionResponse>("POST", "/api/lesion", body),
  startScreen: (body: ScreenRequest) => request<ScreenStatus>("POST", "/api/screen", body),
  screenStatus: (jobId: string) => request<ScreenStatus>("GET", `/api/screen/${jobId}`),
  cancelScreen: (jobId: string) => request<ScreenStatus>("DELETE", `/api/screen/${jobId}`),
};

export function emptySet(): NeuronSet {
  return { types: [], instances: [], body_ids: [], roles: [] };
}

export function isEmptySet(set: NeuronSet): boolean {
  return (
    set.types.length === 0 &&
    set.instances.length === 0 &&
    set.body_ids.length === 0 &&
    set.roles.length === 0
  );
}

/** Matrix indices covered by a NeuronSet, resolved on the client from circuit data. */
export function resolveSet(data: CircuitData, set: NeuronSet): number[] {
  const types = new Set(set.types);
  const instances = new Set(set.instances);
  const roles = new Set(set.roles);
  const ids = new Set(set.body_ids);
  const out: number[] = [];
  for (let i = 0; i < data.body_ids.length; i += 1) {
    const matches =
      types.has(data.types[i]) ||
      instances.has(data.instances[i]) ||
      roles.has(data.roles[i]) ||
      ids.has(data.body_ids[i]);
    if (matches) {
      out.push(i);
    }
  }
  return out;
}
