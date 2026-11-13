"""REST API tests on the synthetic circuit (and the real one when cached)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from connectome_app.api import create_app
from connectome_app.config import CircuitConfig, load_config
from connectome_app.data import load_circuit
from connectome_app.service import Service


@pytest.fixture()
def client(synthetic_config: CircuitConfig, synthetic_dir: Path) -> TestClient:
    service = Service()
    service.register_circuit(load_circuit(synthetic_config, synthetic_dir))
    return TestClient(create_app(service))


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_circuit_data(client: TestClient) -> None:
    data = client.get("/api/circuits/synthetic").json()
    n = len(data["body_ids"])
    assert n == 10
    for key in ("types", "roles", "signs", "sign_sources", "nts"):
        assert len(data[key]) == n
    assert len(data["edge_pre"]) == len(data["edge_post"]) == len(data["edge_weight"]) == 8
    assert len(data["extra_edge_pre"]) == 2


def test_unknown_circuit_is_404(client: TestClient) -> None:
    assert client.get("/api/circuits/does_not_exist").status_code == 404


def test_neuron_detail(client: TestClient) -> None:
    detail = client.get("/api/circuits/synthetic/neurons/10").json()
    assert detail["type"] == "GF"
    assert detail["in_degree"] == 2
    assert detail["top_inputs"][0]["body_id"] == 1
    assert client.get("/api/circuits/synthetic/neurons/12345").status_code == 404


def test_simulate(client: TestClient) -> None:
    body = {
        "circuit": "synthetic",
        "stimulus": {"targets": {"types": ["LCa"]}, "profile": "constant", "rate_hz": 100},
        "duration_ms": 200,
        "n_trials": 3,
        "record_body_ids": [10],
    }
    response = client.post("/api/simulate", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_spikes"] > 0
    assert len(data["raster_times_ms"]) == len(data["raster_neurons"])
    assert "role:input" in data["psth"]["groups"]
    assert len(data["voltage"]["10"]) == len(data["voltage_times_ms"]) == 200


def test_paths(client: TestClient) -> None:
    body = {"circuit": "synthetic", "sources": {"types": ["LCa"]}, "targets": {"roles": ["output"]}, "k": 5}
    data = client.post("/api/paths", json=body).json()
    assert len(data["paths"]) == 2
    assert data["paths"][0]["nodes"][0]["type"] == "LCa"
    assert data["normalization"] == "post"
    type_level = client.post("/api/paths", json={**body, "level": "type"}).json()
    assert [n["label"] for n in type_level["paths"][0]["nodes"]] == ["LCa", "GF", "MN"]


def test_lesion(client: TestClient) -> None:
    body = {
        "circuit": "synthetic",
        "stimulus": {"targets": {"types": ["LCa"]}, "profile": "constant", "rate_hz": 100},
        "duration_ms": 200,
        "n_trials": 4,
        "lesion": {"types": ["GF"]},
    }
    first = client.post("/api/lesion", json=body).json()
    assert first["n_ablated"] == 2
    assert first["baseline_cached"] is False
    assert "p-values" in first["p_value_note"]
    assert {row["metric"] for row in first["metrics"]} == {"spike_count", "rate_hz", "first_spike_ms"}
    second = client.post("/api/lesion", json={**body, "lesion": {"types": ["INH"]}}).json()
    assert second["baseline_cached"] is True


def test_screen_job(client: TestClient) -> None:
    body = {
        "circuit": "synthetic",
        "stimulus": {"targets": {"types": ["LCa"]}, "profile": "constant", "rate_hz": 100},
        "duration_ms": 100,
        "n_trials": 3,
        "measure": {"types": ["GF"]},
    }
    status = client.post("/api/screen", json=body).json()
    job_id = status["job_id"]
    deadline = time.time() + 30
    while status["status"] in ("queued", "running") and time.time() < deadline:
        time.sleep(0.05)
        status = client.get(f"/api/screen/{job_id}").json()
    assert status["status"] == "done", status
    assert status["done"] == status["total"]
    assert "GF" in status["skipped"]
    assert len(status["results"]) == status["total"]
    assert client.get("/api/screen/nope").status_code == 404


@pytest.mark.cached
def test_giant_fiber_end_to_end() -> None:
    config = load_config("giant_fiber")
    if not (config.data_dir() / "neurons.parquet").exists():
        pytest.skip("giant_fiber not fetched yet")
    client = TestClient(create_app(Service()))
    circuits = {c["name"]: c for c in client.get("/api/circuits").json()}
    assert circuits["giant_fiber"]["available"] is True
    data = client.get("/api/circuits/giant_fiber").json()
    assert len(data["body_ids"]) == circuits["giant_fiber"]["n_neurons"]
    paths = client.post(
        "/api/paths",
        json={"circuit": "giant_fiber", "sources": {"types": ["LC4"]}, "targets": {"types": ["TTMn"]}, "k": 5},
    ).json()
    assert len(paths["paths"]) == 5
    lesion = client.post(
        "/api/lesion",
        json={
            "circuit": "giant_fiber",
            "stimulus": {"profile": "ramp", "rate_hz": 100, "start_ms": 50, "end_ms": 450},
            "duration_ms": 500,
            "n_trials": 5,
            "lesion": {"types": ["DNp01"]},
        },
    )
    assert lesion.status_code == 200, lesion.text
    groups = {row["group"] for row in lesion.json()["metrics"]}
    assert {"all outputs", "TTMn", "DNp01"} <= groups
