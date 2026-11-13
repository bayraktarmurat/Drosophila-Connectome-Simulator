"""Phase 5 science sanity checks. Writes docs/SANITY_RESULTS.md.

1. Gap-junction calibration: smallest electrical strength for which ONE GF spike evokes
   exactly one TTMn spike with short latency (isolated pair, no other input).
2. Dose-response: looming-like ramp strength -> GF / TTMn / PSI / DLMn activity,
   with and without the electrical extra edges.
3. Sensitivity grid: w_syn x glutamate sign x unclear-NT default x selection threshold x
   extra edges -> does the qualitative story survive? (GF fires under strong looming,
   TTMn fires, GF lesion reduces TTMn.)

Usage:
    python scripts/sanity_checks.py            # full run (a few minutes)
    python scripts/sanity_checks.py --quick    # fewer grid points
"""

from __future__ import annotations

import argparse
import itertools
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from connectome_app.config import CircuitConfig, load_config  # noqa: E402
from connectome_app.data import Circuit, load_circuit  # noqa: E402
from connectome_app.lesion import RunSettings, group_metric  # noqa: E402
from connectome_app.lif import LIFNetwork, LIFParams  # noqa: E402
from connectome_app.stats import compare_paired  # noqa: E402
from connectome_app.stimulus import Stimulus  # noqa: E402

OUT_PATH = PROJECT_ROOT / "docs" / "SANITY_RESULTS.md"
GROUP_TYPES: dict[str, list[str]] = {
    "GF": ["DNp01"],
    "TTMn": ["TTMn"],
    "PSI": ["PSI"],
    "DLMn": ["DLMn a, b", "DLMn c-f"],
}


# ---------------------------------------------------------------- calibration


@dataclass
class CalibrationRow:
    synapse_equivalent: float
    kick_mv: float
    ttmn_spikes: int
    latency_ms: float


def calibrate_gap_junction(params: LIFParams, candidates: list[float]) -> list[CalibrationRow]:
    """Isolated pair: neuron 0 (GF) is forced to spike once at t=5 ms; neuron 1 = TTMn."""
    rows: list[CalibrationRow] = []
    for strength in candidates:
        electrical = sp.csr_matrix(([strength], ([1], [0])), shape=(2, 2))
        network = LIFNetwork(sp.csr_matrix((2, 2)), params, electrical_weights=electrical)
        start_step = int(round(5.0 / params.dt_ms))
        stimulus = Stimulus(
            targets=np.array([0]), profile="step", rate_hz=1000.0 / params.dt_ms,
            start_ms=start_step * params.dt_ms, end_ms=(start_step + 1) * params.dt_ms,
        )
        result = network.run(60.0, [1], stimulus=stimulus)
        counts = result.spike_counts()
        first = result.first_spike_ms()
        latency = float(first[1, 0] - first[0, 0])
        rows.append(CalibrationRow(strength, strength * params.w_syn_mv, int(counts[1, 0]), latency))
    return rows


def choose_strength(rows: list[CalibrationRow], max_latency_ms: float) -> CalibrationRow | None:
    """Strongest coupling that still gives exactly one TTMn spike (1:1) within `max_latency_ms`.

    Biology: ~1:1 transmission at ~0.8 ms. The model cannot reach both, so we keep 1:1
    and take the shortest latency compatible with it.
    """
    best: CalibrationRow | None = None
    for row in rows:
        if row.ttmn_spikes == 1 and np.isfinite(row.latency_ms) and row.latency_ms <= max_latency_ms:
            best = row
    return best


# ---------------------------------------------------------------- circuit runs


def groups_for(circuit: Circuit) -> dict[str, np.ndarray]:
    return {name: circuit.indices_of_types(types) for name, types in GROUP_TYPES.items()}


def looming(circuit: Circuit, peak_hz: float, duration_ms: float) -> Stimulus:
    return Stimulus(
        targets=circuit.indices_of_role("input"), profile="ramp", rate_hz=peak_hz,
        start_ms=50.0, end_ms=duration_ms - 50.0,
    )


def run_condition(
    circuit: Circuit, network: LIFNetwork, peak_hz: float, n_trials: int, duration_ms: float, seed: int,
    with_gf_lesion: bool,
) -> dict:
    groups = groups_for(circuit)
    settings = RunSettings(duration_ms, n_trials, seed, looming(circuit, peak_hz, duration_ms))
    seeds = settings.seeds()
    columns = np.arange(n_trials)
    baseline = network.run(duration_ms, seeds, stimulus=settings.stimulus)
    row: dict = {}
    for name, indices in groups.items():
        row[f"{name}_rate"] = float(group_metric(baseline, indices, "rate_hz", columns).mean())
        latency = group_metric(baseline, indices, "first_spike_ms", columns)
        row[f"{name}_responded"] = float(np.mean(np.isfinite(latency)))
        if np.any(np.isfinite(latency)):
            row[f"{name}_latency"] = float(np.nanmean(latency))
        else:
            row[f"{name}_latency"] = float("nan")
    counts = baseline.spike_counts()
    row["fraction_active"] = float((counts > 0).any(axis=1).mean())
    row["mean_rate_all"] = float(counts.mean() / (duration_ms / 1000.0))
    if with_gf_lesion:
        alive = np.ones(circuit.n_neurons, dtype=bool)
        alive[groups["GF"]] = False
        lesion = network.run(duration_ms, seeds, stimulus=settings.stimulus, alive=alive)
        base_ttmn = group_metric(baseline, groups["TTMn"], "spike_count", columns)
        lesion_ttmn = group_metric(lesion, groups["TTMn"], "spike_count", columns)
        comparison = compare_paired(base_ttmn, lesion_ttmn)
        row["gf_lesion_ttmn_pct"] = comparison.percent_change
        row["gf_lesion_ttmn_d"] = comparison.cohens_d
        row["gf_lesion_ttmn_d_ci"] = comparison.cohens_d_ci
    return row


def with_overrides(
    base: CircuitConfig, w_syn: float, glutamate: int, unclear_default: int, extra_strength: float
) -> CircuitConfig:
    raw = base.model_dump()
    raw["simulation"]["w_syn_mv"] = w_syn
    raw["signs"]["nt_sign"]["glutamate"] = glutamate
    raw["signs"]["default_sign"] = unclear_default
    for edge in raw["extra_edges"]["edges"]:
        edge["synapse_equivalent"] = extra_strength
    return CircuitConfig.model_validate(raw)


def build(config: CircuitConfig, data_dir: Path, use_extra: bool) -> tuple[Circuit, LIFNetwork]:
    circuit = load_circuit(config, data_dir)
    return circuit, LIFNetwork.from_circuit(circuit, use_extra_edges=use_extra)


# ---------------------------------------------------------------- report helpers


def fmt(value: float, digits: int = 1) -> str:
    if value is None or not np.isfinite(value):
        if value is not None and np.isinf(value):
            if value > 0:
                return "+inf"
            return "-inf"
        return "–"
    return f"{value:.{digits}f}"


def table(frame: pd.DataFrame) -> str:
    header = "| " + " | ".join(frame.columns) + " |"
    divider = "|" + "|".join(["---"] * len(frame.columns)) + "|"
    lines = [header, divider]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.tolist()) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------- main


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    started = time.time()
    base_config = load_config("giant_fiber")
    lite_config = load_config("giant_fiber_lite")
    params = LIFParams.from_config(base_config.simulation)
    report: list[str] = [
        "# Phase 5 sanity-check results",
        "",
        "Generated by `scripts/sanity_checks.py`. Model outputs, not biological measurements.",
        "",
    ]

    # 1. calibration
    candidates = [30, 60, 90, 120, 150, 180, 210, 240, 300, 360, 450, 600, 800]
    calibration = calibrate_gap_junction(params, [float(c) for c in candidates])
    chosen = choose_strength(calibration, max_latency_ms=3.0)
    cal_frame = pd.DataFrame(
        {
            "synapse-equivalents": [int(r.synapse_equivalent) for r in calibration],
            "kick (mV)": [fmt(r.kick_mv) for r in calibration],
            "TTMn spikes per GF spike": [r.ttmn_spikes for r in calibration],
            "latency (ms)": [fmt(r.latency_ms, 2) for r in calibration],
        }
    )
    report += ["## 1. Electrical-synapse calibration (isolated GF -> TTMn pair)", "", table(cal_frame), ""]
    if chosen is None:
        report.append("No strength gives exactly one spike within 3 ms: 1:1 transmission is not reachable in this model.")
        extra_strength = base_config.extra_edges.edges[0].synapse_equivalent
    else:
        extra_strength = chosen.synapse_equivalent
        report.append(
            f"Chosen: **{int(extra_strength)} synapse-equivalents** (strongest value that keeps exactly one TTMn spike "
            f"within 3 ms; latency {fmt(chosen.latency_ms, 2)} ms). Biological GF->TTMn latency is ~0.8 ms."
        )
    report.append("")
    print(f"[calibration] chosen={extra_strength}")

    # 2. dose-response
    n_trials = 5
    duration = 600.0
    if args.quick:
        rates = [0.0, 10.0, 50.0, 150.0]
    else:
        rates = [0.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0]
    calibrated = with_overrides(base_config, base_config.simulation.w_syn_mv, -1, 1, extra_strength)
    dose_rows: list[dict] = []
    for use_extra in (False, True):
        circuit, network = build(calibrated, base_config.data_dir(), use_extra)
        for peak in rates:
            row = run_condition(circuit, network, peak, n_trials, duration, base_config.simulation.base_seed, False)
            row["electrical"] = use_extra
            row["peak_hz"] = peak
            dose_rows.append(row)
            print(f"[dose] extra={use_extra} peak={peak} GF={row['GF_rate']:.1f} TTMn={row['TTMn_rate']:.1f}")
    dose = pd.DataFrame(dose_rows)
    dose_out = pd.DataFrame(
        {
            "electrical": dose["electrical"].map({False: "off", True: "on"}),
            "peak input (Hz)": dose["peak_hz"].map(lambda v: fmt(v, 0)),
            "GF rate (Hz)": dose["GF_rate"].map(fmt),
            "GF latency (ms)": dose["GF_latency"].map(fmt),
            "TTMn rate": dose["TTMn_rate"].map(fmt),
            "TTMn latency": dose["TTMn_latency"].map(fmt),
            "PSI rate": dose["PSI_rate"].map(fmt),
            "DLMn rate": dose["DLMn_rate"].map(fmt),
            "network active": dose["fraction_active"].map(lambda v: f"{v * 100:.0f}%"),
        }
    )
    report += [
        "## 2. Dose-response: looming-like ramp on all LC4 + LPLC2 inputs",
        "",
        f"Ramp from 0 Hz at 50 ms to the peak at {duration - 50:.0f} ms; {n_trials} trials x {duration:.0f} ms; "
        "rates are averaged over the whole run and over the neurons of each group; latency = first spike of the group.",
        "",
        table(dose_out),
        "",
    ]

    # 3. sensitivity grid
    if args.quick:
        w_values = [0.3]
        glu_values = [-1, 1]
        unclear_values = [1]
    else:
        w_values = [0.15, 0.3, 0.6]
        glu_values = [-1, 1]
        unclear_values = [1, 0]
    datasets = [("t=10", base_config), ("t=20 (lite)", lite_config)]
    grid_rows: list[dict] = []
    for (label, dataset_config), w_syn, glu, unclear, use_extra in itertools.product(
        datasets, w_values, glu_values, unclear_values, (False, True)
    ):
        config = with_overrides(dataset_config, w_syn, glu, unclear, extra_strength)
        circuit, network = build(config, dataset_config.data_dir(), use_extra)
        strong = run_condition(circuit, network, 100.0, n_trials, duration, base_config.simulation.base_seed, True)
        weak = run_condition(circuit, network, 10.0, n_trials, duration, base_config.simulation.base_seed, False)
        grid_rows.append(
            {
                "selection": label, "w_syn": w_syn, "glutamate": glu, "unclear": unclear, "electrical": use_extra,
                "GF weak": weak["GF_rate"], "GF strong": strong["GF_rate"], "TTMn strong": strong["TTMn_rate"],
                "PSI strong": strong["PSI_rate"], "DLMn strong": strong["DLMn_rate"],
                "active": strong["fraction_active"], "lesion pct": strong["gf_lesion_ttmn_pct"],
                "lesion d": strong["gf_lesion_ttmn_d"], "lesion ci": strong["gf_lesion_ttmn_d_ci"],
            }
        )
        print(f"[grid] {label} w={w_syn} glu={glu} unclear={unclear} extra={use_extra} "
              f"GF={strong['GF_rate']:.1f} TTMn={strong['TTMn_rate']:.1f} lesion={strong['gf_lesion_ttmn_pct']:.1f}%")
    grid = pd.DataFrame(grid_rows)
    grid_out = pd.DataFrame(
        {
            "selection": grid["selection"],
            "w_syn (mV)": grid["w_syn"],
            "Glu sign": grid["glutamate"].map(lambda v: f"{v:+d}"),
            "unclear NT": grid["unclear"].map(lambda v: f"{v:+d}"),
            "electrical": grid["electrical"].map({False: "off", True: "on"}),
            "GF @10 Hz": grid["GF weak"].map(fmt),
            "GF @100 Hz": grid["GF strong"].map(fmt),
            "TTMn @100": grid["TTMn strong"].map(fmt),
            "PSI @100": grid["PSI strong"].map(fmt),
            "DLMn @100": grid["DLMn strong"].map(fmt),
            "net active": grid["active"].map(lambda v: f"{v * 100:.0f}%"),
            "GF lesion: TTMn %": grid["lesion pct"].map(fmt),
            "d [95% CI]": [
                f"{fmt(d, 2)} [{fmt(ci[0], 2)}, {fmt(ci[1], 2)}]" for d, ci in zip(grid["lesion d"], grid["lesion ci"])
            ],
        }
    )
    report += [
        "## 3. Sensitivity grid (peak looming input 100 Hz unless noted; rates in Hz)",
        "",
        table(grid_out),
        "",
        f"Total runtime: {time.time() - started:.0f} s.",
        "",
    ]
    OUT_PATH.write_text("\n".join(report), encoding="utf-8")
    grid.to_csv(PROJECT_ROOT / "docs" / "sanity_grid.csv", index=False)
    dose.to_csv(PROJECT_ROOT / "docs" / "sanity_dose.csv", index=False)
    print(f"Wrote {OUT_PATH} in {time.time() - started:.0f}s")


if __name__ == "__main__":
    main()
