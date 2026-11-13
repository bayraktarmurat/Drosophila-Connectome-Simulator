import type { CircuitData, StimulusSpec } from "./api";

/** Stimulus + run length, shared by the simulation and lesion panels. */
export interface RunSettings {
  stimulus: StimulusSpec;
  duration_ms: number;
  n_trials: number;
  base_seed: number | null;
}

export function defaultRunSettings(data: CircuitData): RunSettings {
  let duration = 1000;
  const configured = data.simulation_defaults["default_duration_ms"];
  if (configured !== undefined) {
    duration = configured;
  }
  let trials = 10;
  const configuredTrials = data.simulation_defaults["default_trials"];
  if (configuredTrials !== undefined) {
    trials = configuredTrials;
  }
  return {
    stimulus: {
      targets: { types: [], body_ids: [], roles: ["input"] },
      profile: "ramp",
      rate_hz: 100,
      baseline_hz: 0,
      start_ms: 100,
      end_ms: duration * 0.8,
      mode: "spikes",
      synaptic_weight_mv: 10,
    },
    duration_ms: duration,
    n_trials: trials,
    base_seed: null,
  };
}

/** Value or fallback, without the ?? operator (project style: explicit branches). */
export function orDefault<T>(value: T | null | undefined, fallback: T): T {
  if (value === null || value === undefined) {
    return fallback;
  }
  return value;
}
