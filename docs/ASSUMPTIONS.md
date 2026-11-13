# Modelling assumptions

Every simulation output in this project depends on the choices below. **None of the outputs are biological ground truth.** They are what this particular simplified model does with this particular sub-circuit.

Status column: **data** = taken from the connectome; **choice** = our modelling decision; **literature** = supported by published work (cited); **placeholder** = not yet calibrated.

## 1. Data and sub-circuit selection

| Item | Value | Status | Notes |
|---|---|---|---|
| Dataset | `male-cns:v1.0` (neuPrint server 1.9.8) | data | Fetch date is in `data/<name>/manifest.json` |
| Synapse counts | `ConnectsTo.weight` (all synapses) | data | `weightHP` (high-precision only) is selectable via `weight_field` |
| Sub-circuit | seeds ∪ {≤`hops_down` from inputs} ∩ {≤`hops_up` to outputs} | choice | Neurons off these short paths are excluded, even if they modulate the circuit |
| Selection threshold | edges ≥ 10 synapses | choice | t=20 (lite config) drops half of the GFCs and breaks GF→GFC2→TTMn |
| Kept edges | ≥ 10 synapses between selected neurons | choice | Weak edges are dropped, e.g. GF→PSI (16 synapses spread over 4 pairs) |
| Outside inputs | ignored | choice | Neurons outside the sub-circuit contribute no activity; their synapses still count in path normalization (see §4) |

Giant Fiber circuit at t=10: 3,813 neurons, 88,355 edges, 2.85 M synapses.

## 2. Synaptic signs

One sign per presynaptic neuron (Dale's law). Resolution order: `type_overrides` → `consensusNt` → `celltypePredictedNt` (confidence ≥ 0.5) → `default_sign`.

| Transmitter | Sign | Status | Notes |
|---|---|---|---|
| acetylcholine | +1 | choice (standard) | Main fast excitatory transmitter in the fly CNS |
| GABA | −1 | choice (standard) | |
| glutamate | −1 | choice | Inhibitory through GluClα in much of the fly CNS, but excitatory at NMJs and some central synapses. Configurable; part of the Phase 5 sensitivity grid |
| histamine | −1 | choice | Histamine-gated chloride channels |
| dopamine, octopamine, serotonin | 0 | choice | Neuromodulators have no fast sign in this model, so their output is ignored |
| unclear / missing | celltype prediction, else +1 | choice | Phase 5 sensitivity grid |

NT predictions are themselves **machine-learning predictions** from EM images, not measurements.

Giant Fiber circuit: 3,755 neurons signed from `consensusNt`, 9 from the cell-type prediction, 49 by default (+1). Most of those 49 are motor neurons (Tergotr. MN, DLMn c-f, DVMn, STTMm), whose output inside the CNS hardly matters. 23 neuromodulatory neurons get sign 0.

## 3. Extra (non-connectome) edges: electrical synapses

**These are modelling assumptions, not connectome data.** EM connectomes record chemical synapses only. In the fly, the GF drives TTMn and PSI mainly through gap junctions made of Shaking-B (ShakB) innexins. Without them, the model sees only the chemical GF → TTMn contact (90 synapses, 70 on the right, 20 on the left) and an even weaker GF → PSI contact.

| Edge | Pairing | Strength | Status | Sources |
|---|---|---|---|---|
| DNp01 → TTMn (electrical) | each GF to the TTMn it has the most chemical synapses onto (R→R, L→L in the data) | 300 synapse-equivalents (90 mV kick) | literature (existence) + **calibrated (value)** | [1], [2], [3], [4] |
| DNp01 → PSI (electrical) | same side (no chemical partner ≥ 10 synapses, so falls back to soma side) | 300 synapse-equivalents | literature (existence) + **calibrated (value)** | [1], [2], [4] |

- **Off by default**; toggled in the UI. Phase 5 reports every result both with and without these edges.
- Modelled as **one-way** (GF → target). Supported qualitatively by the rectification of GF–TTMn junctions [5], but a real gap junction passes current in proportion to the voltage difference. The model does not do this.
- **The value 300 is not from the literature; it is a calibration.** The literature supports reliable, short-latency (~0.8 ms for TTMn), roughly 1:1 transmission of GF spikes [1]. In an isolated GF→TTMn pair (Phase 5, `docs/SANITY_RESULTS.md` §1), ≤120 equivalents never fire TTMn, 150–300 give exactly one spike (latency 7.3 → 2.0 ms), and ≥360 give two or more. This model cannot get both 1:1 and sub-millisecond latency, so we keep 1:1 and take the shortest latency compatible with it: 300 (2.0 ms). It is a fit to a qualitative expectation, not a measurement. The same value is used for GF→PSI, which is untested.

Sources (cited from the published literature; verify the exact pages and DOIs before using them formally):
1. Tanouye MA, Wyman RJ (1980). Motor outputs of giant nerve fiber in *Drosophila*. *J Neurophysiol* 44(2):405–421.
2. King DG, Wyman RJ (1980). Anatomy of the giant fibre pathway in *Drosophila*. I. Three thoracic components of the pathway. *J Neurocytol* 9:753–770.
3. Phelan P, Nakagawa M, Wilkin MB, et al. (1996). Mutations in *shaking-B* prevent electrical synapse formation in the *Drosophila* giant fiber system. *J Neurosci* 16(3):1101–1113.
4. Allen MJ, Godenschwege TA, Tanouye MA, Phelan P (2006). Making an escape: development and function of the *Drosophila* giant fibre system. *Semin Cell Dev Biol* 17(1):31–41.
5. Phelan P, Goulding LA, Tam JLY, et al. (2008). Molecular mechanism of rectification at identified electrical synapses in the *Drosophila* giant fiber system. *Curr Biol* 18(24):1955–1960.

## 4. Path finder (Phase 3)

| Item | Value | Status | Notes |
|---|---|---|---|
| Edge cost | −log(w_ij / D_i) | choice | D_i = postsynaptic neuron's **total input in the full dataset**, not the sub-circuit sum, so the sub-circuit boundary does not inflate shares |
| D_i | neuPrint `post` (all PSDs, `normalization: post`) | choice | Alternative `input_weight`: summed `ConnectsTo` weight from all Neurons. In this circuit the median ratio between the two is 0.965 |
| Why −log(share) and not 1/weight | | choice | −log makes path cost = −log(product of shares): "what fraction of each target's input does this chain provide". 1/weight sums inverse counts, which has no such meaning and ignores how many other inputs a target has |
| Search | A* over simple paths, exact | method | Heuristic = exact reverse-Dijkstra distance to the targets (admissible). Verified against brute-force enumeration in the tests |
| Type-level graph | synapses summed per type pair; D = sum of members' D_i; self-loops removed | choice | Type sign = majority sign of its neurons |
| Sign filter | path sign = product of the presynaptic signs; neuromodulator (sign 0) edges excluded when filtering | choice | "Net excitatory" is a parity count. It ignores timing and is not a prediction of the net effect |

**Paths are anatomical, not functional.** A high-score path has a large synaptic share at each step. Whether it carries activity depends on the dynamics, which is what the simulator is for.

## 4b. Lesions and statistics (Phase 3)

| Item | Choice | Notes |
|---|---|---|
| Ablation | the neuron never spikes (its column of W is effectively zero) | Its input row becomes irrelevant; no matrix copy |
| Pairing | baseline and lesion use the same per-trial seeds, so identical stimulus trains | A paired design: differences come from the lesion, not from stimulus noise |
| Baseline | computed once per (circuit, extra-edges flag, stimulus, duration, trials, seed) and cached | Columns never interact, so a cached baseline is bit-identical to one run alongside the lesion (tested) |
| Primary statistic | mean difference and Cohen's d (d_av: pooled SD = √((s²_base + s²_lesion)/2)), each with a percentile bootstrap 95% CI (2000 paired resamples) | |
| Zero variance | d = 0 if the means are equal, ±∞ otherwise | Common for silent groups: a deterministic change shows as ±∞, not as a "huge" finite d |
| Latency | compared only on trials where both conditions spiked; response fractions reported separately | |
| p-value | Wilcoxon signed-rank, **secondary only** | It shrinks with trial count alone; with enough simulated trials any non-zero effect is "significant" |
| Screen ranking | \|percent change\| by default (or \|d\|) | Candidates that overlap the measured group are skipped. Lesioning a type removes all its neurons, so large types (LC4: 126 neurons) are naturally large perturbations |

Full type-level screen on the Giant Fiber circuit (1,462 types, 5 trials × 300 ms, 200 columns per batch): **304 s** on the MacBook. It runs as a background job with progress.

## 5. LIF model (Phase 2)

Loosely inspired by published whole-brain fly LIF models; defaults, not measurements. The Phase 5 sensitivity analysis shows how much the conclusions depend on them.

| Parameter | Default | Notes |
|---|---|---|
| dt | 0.1 ms | Euler for v; g decays by the exact factor exp(−dt/τ_syn) |
| τ_m | 20 ms | same for every neuron (real neurons differ widely) |
| V_rest = V_reset | −52 mV | |
| V_threshold | −45 mV | |
| refractory | 2 ms | v is clamped at reset, no integration |
| τ_syn | 5 ms | one time constant for every transmitter |
| w_syn | 0.3 mV per synapse | **one global scale**; synapse count is assumed proportional to strength |
| chemical delay | 2 ms | same for every connection (ignores axon length) |
| electrical (extra-edge) delay | 0.1 ms (one step) | one-way, spike-triggered; not a true gap-junction current |
| precision | float32 state | enough for mV-scale dynamics; tests check the analytic rate within 2% |

**Stimulus.** Poisson trains whose rate follows a profile (constant / step / linear ramp = "looming-like"). The default mode `spikes` makes each Poisson event a spike of the input neuron directly, bypassing its membrane. The alternative mode `synaptic` adds a fixed mV kick to the input neuron's g. A linear rate ramp is a crude stand-in for looming: real LC4/LPLC2 responses depend on angular size and speed in a nonlinear way.

**Seeds.** Every column (trial) has its own seed, derived from `base_seed` with `numpy.random.SeedSequence`. Columns with the same seed get identical stimulus trains, which is how baseline and lesion runs are paired.

**Performance (MacBook, Python 3.14, numpy 2.5, scipy 1.18).** Giant Fiber circuit (3,813 neurons, 88k edges), 1 s simulated, ramp to 150 Hz on all 311 inputs: **10 trials in 1.9 s**. Cost grows linearly with columns: 300 ms takes 0.43 s at 10 columns, 1.9 s at 50, 7.7 s at 200.

## 6. Phase 5: sanity checks and sensitivity (`scripts/sanity_checks.py`, full tables in `docs/SANITY_RESULTS.md`)

Stimulus: linear ramp on all 311 LC4 + LPLC2 neurons, 0 → peak between 50 and 550 ms; 5 paired trials × 600 ms.

### Expected behaviour vs. what the model does

| Expectation | Result | Comment |
|---|---|---|
| No input → nothing fires | **holds** | Trivially: the model has no spontaneous activity or bias current |
| Strong looming-like input → GF fires → TTMn fires | **holds** in all 24 grid settings | DLMn fires from ~50 Hz input onward |
| PSI (flight) fires via GF | **only with the electrical edges** (when glutamate is inhibitory) | Chemical GF→PSI (16 synapses over 4 pairs) is below the edge threshold; consistent with GF→PSI being electrical in the fly |
| Weak input → GF stays silent | **fails** | GF fires ~20 Hz even at a 5 Hz peak. 311 inputs converge with ~11k synapses onto a single point neuron with a uniform w_syn, so the model GF integrates everything and has no looming selectivity |
| GF fires one or a few spikes per loom | **fails** | Model GF reaches 200–420 Hz (refractory cap ≈ 476 Hz). No adaptation, no high GF-specific threshold |
| GF lesion reduces TTMn | **sign is robust**: TTMn decreases in every setting | **Magnitude is not**: −0.4 % to −100 % depending on the settings below |

Not tuned away: these failures come from the point-neuron LIF with one global w_syn and threshold. Fixing them would need per-type parameters, which this project does not claim to know.

### Sensitivity of the GF-lesion result (t = 10 circuit, unclear-NT default +1; rates in Hz at 100 Hz peak input)

| w_syn (mV) | Glu sign | electrical | GF @10 Hz | GF @100 Hz | TTMn | PSI | network active | GF lesion: TTMn change |
|---|---|---|---|---|---|---|---|---|
| 0.15 | −1 | off | 48 | 263 | 60 | 0 | 25 % | −93 % |
| 0.15 | −1 | on | 50 | 267 | 215 | 157 | 25 % | −98 % |
| 0.15 | +1 | off | 257 | 362 | 267 | 165 | 56 % | −5 % |
| 0.15 | +1 | on | 259 | 363 | 319 | 283 | 56 % | −21 % |
| **0.30** | **−1** | **off** | **20** | **222** | **141** | **0** | **42 %** | **−54 %** (default) |
| 0.30 | −1 | on | 21 | 210 | 228 | 134 | 42 % | −72 % |
| 0.30 | +1 | off | 367 | 402 | 360 | 276 | 67 % | −2 % |
| 0.30 | +1 | on | 368 | 402 | 385 | 357 | 67 % | −9 % |
| 0.60 | −1 | off | 4 | 69 | 137 | 0 | 53 % | −18 % |
| 0.60 | −1 | on | 4 | 71 | 171 | 47 | 54 % | −34 % |
| 0.60 | +1 | off | 405 | 421 | 398 | 351 | 73 % | −0.4 % |
| 0.60 | +1 | on | 406 | 421 | 412 | 400 | 73 % | −4 % |

What drives the conclusions, in order:
1. **Glutamate sign** dominates. With glutamate excitatory, 56–80 % of the network fires, GF and TTMn saturate, and removing GF barely matters (−0.4 to −31 %). With glutamate inhibitory, the GF lesion removes 18–100 % of TTMn spikes.
2. **w_syn** is non-monotonic. Doubling it to 0.6 mV *lowers* GF firing (69 Hz), because GF's inhibitory inputs scale up too.
3. **Electrical edges** always make the GF lesion larger (more of TTMn's drive goes through GF) and are the only way PSI fires.
4. **Selection threshold.** The lite circuit (t = 20, fewer parallel pathways) gives larger GF-lesion effects (−63 % vs −54 % at default settings; up to −100 %). A smaller sub-circuit overstates how much one neuron matters.
5. **Unclear-NT default** (+1 vs 0) is negligible: ≤ 11 Hz on GF, ≤ 3 points on the lesion effect. It touches only 49 neurons, mostly motor.

**Robust conclusion:** in this model, GF is one of several routes from LC4/LPLC2 to TTMn, and removing it lowers TTMn output. **Not robust:** how much. Qualitatively, flies with a silenced GF can still take off, using slower "long-mode" escapes [6]; that fits the existence of parallel pathways but is not a quantitative validation.

### Effect sizes in simulations
Cohen's d in the grid reaches |d| > 100. The only trial-to-trial variability is the Poisson input, so the denominator (SD) is tiny and d reflects the model's low noise more than the size of the effect. **Read the magnitude from the % change; use d and its CI only to check that the direction is consistent across trials.** The UI shows both.

6. von Reyn CR, Breads P, Peek MY, et al. (2014). A spike-timing mechanism for action selection. *Nat Neurosci* 17:962–970.

## 7. Known gaps

- Single-compartment neurons: no dendritic computation, no graded (non-spiking) transmission. Many fly interneurons are partly graded.
- No neuromodulation, no plasticity, no adaptation.
- Motor neurons are the circuit's end point; there are no muscles or behaviour.
- Asymmetry: chemical GF→TTMn is 70 synapses on the right and 20 on the left. This may be biological or a reconstruction artefact.
- No per-type parameters (threshold, τ_m, adaptation): the main reason the model GF is neither selective nor sparse (§6).
