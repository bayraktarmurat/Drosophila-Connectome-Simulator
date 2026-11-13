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
| DNp01 → TTMn (electrical) | each GF to the TTMn it has the most chemical synapses onto (R→R, L→L in the data) | 60 synapse-equivalents | literature (existence) + **placeholder (value)** | [1], [2], [3], [4] |
| DNp01 → PSI (electrical) | same side (no chemical partner ≥ 10 synapses, so falls back to soma side) | 60 synapse-equivalents | literature (existence) + **placeholder (value)** | [1], [2], [4] |

- **Off by default**; toggled in the UI. Phase 5 reports every result both with and without these edges.
- Modelled as **one-way** (GF → target). Supported qualitatively by the rectification of GF–TTMn junctions [5], but a real gap junction passes current in proportion to the voltage difference. The model does not do this.
- **The value 60 is not from the literature.** The literature supports reliable, short-latency (sub-millisecond for TTMn), roughly 1:1 transmission of GF spikes [1]. The number will be calibrated in Phase 5 against that qualitative target: one GF spike gives one target spike. This calibration is a fit to a behavioural expectation, not a measurement.

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

## 5. LIF parameters (Phase 2)

Loosely inspired by published whole-brain fly LIF models; defaults, not measurements. The table and the sensitivity analysis are added in Phases 2 and 5.

| Parameter | Default |
|---|---|
| dt | 0.1 ms (Euler) |
| τ_m | 20 ms |
| V_rest = V_reset | −52 mV |
| V_threshold | −45 mV |
| refractory | 2 ms |
| τ_syn | 5 ms |
| w_syn | 0.3 mV per synapse |
| synaptic delay | 2 ms |

## 6. Known gaps

- Single-compartment neurons: no dendritic computation, no graded (non-spiking) transmission. Many fly interneurons are partly graded.
- No neuromodulation, no plasticity, no adaptation.
- Motor neurons are the circuit's end point; there are no muscles or behaviour.
- Asymmetry: chemical GF→TTMn is 70 synapses on the right and 20 on the left. This may be biological or a reconstruction artefact.
