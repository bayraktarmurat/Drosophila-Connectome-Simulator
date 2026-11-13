"""Compute and cache the 2-D graph layout for a fetched circuit.

Usage:
    python scripts/compute_layout.py --config giant_fiber
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from connectome_app.data import load_circuit  # noqa: E402
from connectome_app.layout import LAYOUT_FILE, compute_layout  # noqa: E402


def run(config_name: str, iterations: int) -> Path:
    circuit = load_circuit(config_name)
    started = time.time()
    layout = compute_layout(circuit, iterations=iterations)
    out_path = circuit.config.data_dir() / LAYOUT_FILE
    layout.to_parquet(out_path, index=False)
    print(f"Wrote {out_path} ({circuit.n_neurons} neurons, {time.time() - started:.1f}s)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--iterations", type=int, default=150)
    args = parser.parse_args()
    run(args.config, args.iterations)


if __name__ == "__main__":
    main()
