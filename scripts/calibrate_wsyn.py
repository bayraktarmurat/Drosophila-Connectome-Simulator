"""Calibrate the global synaptic weight w_syn with the criterion of Shiu et al. 2024.

Criterion (Nature 634, 210-219, Methods): choose w_syn so that stimulating sugar gustatory
receptor neurons at 100 Hz drives MN9 to roughly 80% of its maximal firing rate.
"Maximal" is taken here as the highest MN9 rate over the tested input rates.

Usage:
    python scripts/calibrate_wsyn.py --config feeding
    python scripts/calibrate_wsyn.py --config feeding --weights 0.15 0.16 0.17 --trials 10
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from connectome_app.config import CircuitConfig, load_config  # noqa: E402
from connectome_app.data import Circuit, load_circuit  # noqa: E402
from connectome_app.lif import LIFNetwork, LIFParams, trial_seeds  # noqa: E402
from connectome_app.stimulus import Stimulus  # noqa: E402

DEFAULT_RATES = [10.0, 25.0, 50.0, 100.0, 150.0, 200.0, 300.0, 400.0]
DEFAULT_WEIGHTS = [0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18, 0.19, 0.2, 0.25, 0.3]
REFERENCE_RATE = 100.0
TARGET_FRACTION = 0.8


def output_rates(
    circuit: Circuit,
    config: CircuitConfig,
    w_syn: float,
    inputs: np.ndarray,
    outputs: np.ndarray,
    rates: list[float],
    seeds: np.ndarray,
    duration_ms: float,
) -> list[float]:
    """Mean output firing rate (Hz) for each constant input rate, at one w_syn."""
    simulation = config.simulation.model_copy(update={"w_syn_mv": w_syn})
    network = LIFNetwork.from_circuit(circuit, LIFParams.from_config(simulation))
    values: list[float] = []
    for rate in rates:
        stimulus = Stimulus(targets=inputs, profile="constant", rate_hz=rate)
        result = network.run(duration_ms, seeds, stimulus=stimulus)
        counts = result.spike_counts()
        values.append(float(counts[outputs, :].mean()) / (duration_ms / 1000.0))
    return values


def fraction_of_max(values: list[float], rates: list[float]) -> float:
    """Output at the reference rate divided by the maximal output (NaN if always silent)."""
    peak = max(values)
    if peak <= 0:
        return float("nan")
    return values[rates.index(REFERENCE_RATE)] / peak


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", default="feeding")
    parser.add_argument("--inputs", nargs="+", default=["LB3b", "LB3c"], help="sugar GRN types")
    parser.add_argument("--output", default="MN9", help="measured motor neuron type")
    parser.add_argument("--weights", nargs="+", type=float, default=DEFAULT_WEIGHTS)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--duration-ms", type=float, default=1000.0)
    args = parser.parse_args()

    config = load_config(args.config)
    circuit = load_circuit(config)
    inputs = circuit.indices_of_types(args.inputs)
    outputs = circuit.indices_of_types([args.output])
    if len(inputs) == 0 or len(outputs) == 0:
        raise SystemExit(f"Input types {args.inputs} or output type {args.output} not in the circuit")
    rates = DEFAULT_RATES
    seeds = trial_seeds(config.simulation.base_seed, args.trials)

    input_names = ", ".join(args.inputs)
    print(f"{config.name}: {len(inputs)} input neurons ({input_names}), {len(outputs)} x {args.output}")
    print(f"configured w_syn = {config.simulation.w_syn_mv} mV")
    print(f"target: {REFERENCE_RATE:.0f} Hz input -> {TARGET_FRACTION:.0%} of maximal {args.output} rate\n")
    header = " ".join(f"{rate:>6.0f}" for rate in rates)
    print(f"w_syn (mV) | {args.output} rate (Hz) at input rate (Hz) {header} | fraction")

    best_weight: float | None = None
    best_distance = float("inf")
    for weight in args.weights:
        values = output_rates(circuit, config, weight, inputs, outputs, rates, seeds, args.duration_ms)
        fraction = fraction_of_max(values, rates)
        cells = " ".join(f"{value:6.1f}" for value in values)
        print(f"{weight:10.3f} | {' ' * 33}{cells} | {fraction:6.2f}")
        if not np.isnan(fraction):
            distance = abs(fraction - TARGET_FRACTION)
            if distance < best_distance:
                best_distance = distance
                best_weight = weight

    if best_weight is None:
        print("\nThe output never fired: widen the w_syn range.")
    else:
        print(f"\nClosest tested w_syn to the criterion: {best_weight} mV")
        print(f"(|fraction - {TARGET_FRACTION}| = {best_distance:.2f})")


if __name__ == "__main__":
    main()
