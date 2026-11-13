import type { CircuitData, Profile, StimulusMode } from "../api";
import type { RunSettings } from "../state";
import NeuronSetPicker from "./NeuronSetPicker";

interface StimulusFormProps {
  data: CircuitData;
  value: RunSettings;
  onChange: (value: RunSettings) => void;
}

function NumberField(props: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
  min?: number;
  title?: string;
}) {
  return (
    <label className="field" title={props.title}>
      <span className="field-label">{props.label}</span>
      <input
        type="number"
        value={props.value}
        step={props.step}
        min={props.min}
        onChange={(event) => {
          const parsed = Number(event.target.value);
          if (Number.isFinite(parsed)) {
            props.onChange(parsed);
          }
        }}
      />
    </label>
  );
}

/** Stimulus target set, rate profile, strength, duration and trials. */
export default function StimulusForm(props: StimulusFormProps) {
  const settings = props.value;
  const stimulus = settings.stimulus;
  const setStimulus = (patch: Partial<typeof stimulus>) => {
    props.onChange({ ...settings, stimulus: { ...stimulus, ...patch } });
  };

  let endValue = settings.duration_ms;
  if (stimulus.end_ms !== null) {
    endValue = stimulus.end_ms;
  }

  let profileHelp = "Linear rise from baseline to peak rate between start and end (looming-like).";
  if (stimulus.profile === "constant") {
    profileHelp = "Peak rate for the whole run.";
  } else if (stimulus.profile === "step") {
    profileHelp = "Baseline, then peak rate between start and end.";
  }

  let seedText = "";
  if (settings.base_seed !== null) {
    seedText = String(settings.base_seed);
  }

  let synapticField = null;
  if (stimulus.mode === "synaptic") {
    synapticField = (
      <NumberField
        label="kick (mV)"
        value={stimulus.synaptic_weight_mv}
        onChange={(v) => setStimulus({ synaptic_weight_mv: v })}
      />
    );
  }

  return (
    <div className="stimulus-form">
      <NeuronSetPicker
        label="Stimulated neurons"
        data={props.data}
        value={stimulus.targets}
        onChange={(targets) => setStimulus({ targets })}
      />
      <div className="field-row">
        <label className="field">
          <span className="field-label">profile</span>
          <select
            value={stimulus.profile}
            onChange={(event) => setStimulus({ profile: event.target.value as Profile })}
          >
            <option value="ramp">ramp (looming-like)</option>
            <option value="step">step</option>
            <option value="constant">constant</option>
          </select>
        </label>
        <label className="field" title="spikes: each Poisson event is a spike of the input neuron">
          <span className="field-label">mode</span>
          <select
            value={stimulus.mode}
            onChange={(event) => setStimulus({ mode: event.target.value as StimulusMode })}
          >
            <option value="spikes">force spikes</option>
            <option value="synaptic">synaptic kick</option>
          </select>
        </label>
        {synapticField}
      </div>
      <p className="hint">{profileHelp}</p>
      <div className="field-row">
        <NumberField label="peak rate (Hz)" value={stimulus.rate_hz} min={0} onChange={(v) => setStimulus({ rate_hz: v })} />
        <NumberField label="baseline (Hz)" value={stimulus.baseline_hz} min={0} onChange={(v) => setStimulus({ baseline_hz: v })} />
        <NumberField label="start (ms)" value={stimulus.start_ms} min={0} onChange={(v) => setStimulus({ start_ms: v })} />
        <NumberField label="end (ms)" value={endValue} min={0} onChange={(v) => setStimulus({ end_ms: v })} />
      </div>
      <div className="field-row">
        <NumberField
          label="duration (ms)"
          value={settings.duration_ms}
          min={10}
          step={100}
          onChange={(v) => props.onChange({ ...settings, duration_ms: v })}
        />
        <NumberField
          label="trials"
          value={settings.n_trials}
          min={1}
          onChange={(v) => props.onChange({ ...settings, n_trials: Math.max(1, Math.round(v)) })}
        />
        <label className="field" title="Leave empty to use the config's base seed">
          <span className="field-label">seed</span>
          <input
            type="number"
            value={seedText}
            placeholder="config"
            onChange={(event) => {
              const text = event.target.value;
              if (text === "") {
                props.onChange({ ...settings, base_seed: null });
              } else {
                props.onChange({ ...settings, base_seed: Math.round(Number(text)) });
              }
            }}
          />
        </label>
      </div>
    </div>
  );
}
