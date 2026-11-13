"""Graph layout: bounded coordinates, signal flow left to right, served by the API."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from connectome_app.api import create_app
from connectome_app.config import CircuitConfig
from connectome_app.data import load_circuit
from connectome_app.layout import compute_layout, flow_depth, load_or_flow_layout
from connectome_app.service import Service


def test_flow_depth_puts_inputs_left_outputs_right(
    synthetic_config: CircuitConfig, synthetic_dir: Path
) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    depth = flow_depth(circuit)
    assert np.all(depth[circuit.indices_of_role("input")] == -1.0)
    assert np.all(depth[circuit.indices_of_role("output")] == 1.0)


def test_compute_layout_is_bounded_and_ordered(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    layout = compute_layout(circuit, iterations=60)
    assert len(layout) == circuit.n_neurons
    assert np.isfinite(layout[["x", "y"]].to_numpy()).all()
    assert np.abs(layout[["x", "y"]].to_numpy()).max() <= 1.0 + 1e-9
    x = layout["x"].to_numpy()
    assert x[circuit.indices_of_role("input")].mean() < x[circuit.indices_of_role("output")].mean()


def test_flow_layout_fallback_when_no_cache(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    circuit = load_circuit(synthetic_config, synthetic_dir)
    layout = load_or_flow_layout(circuit)
    assert list(layout["body_id"]) == list(circuit.body_ids)


def test_api_serves_positions(synthetic_config: CircuitConfig, synthetic_dir: Path) -> None:
    service = Service()
    service.register_circuit(load_circuit(synthetic_config, synthetic_dir))
    data = TestClient(create_app(service)).get("/api/circuits/synthetic").json()
    assert len(data["x"]) == len(data["y"]) == len(data["body_ids"])
