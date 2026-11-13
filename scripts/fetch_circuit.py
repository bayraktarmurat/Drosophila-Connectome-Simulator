"""Fetch a sub-circuit from neuPrint and cache it as parquet.

This is the ONLY module that talks to neuPrint. The web app reads the cache.

Usage:
    python scripts/fetch_circuit.py --config giant_fiber

The token is read by neuprint-python from the NEUPRINT_APPLICATION_CREDENTIALS
environment variable. It is never printed or written anywhere.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from connectome_app.config import CircuitConfig, load_config  # noqa: E402

TOKEN_ENV = "NEUPRINT_APPLICATION_CREDENTIALS"
CHUNK_SIZE = 2000

log = logging.getLogger("fetch_circuit")


@dataclass
class Selection:
    """Result of the hop-limited selection at one threshold."""

    body_ids: set[int]
    min_weight: int
    dist_from_inputs: dict[int, int]
    dist_to_outputs: dict[int, int]
    seed_types: pd.DataFrame


def make_client(config: CircuitConfig):
    """Create a neuPrint client; fails clearly if the token is missing."""
    if not os.environ.get(TOKEN_ENV):
        raise SystemExit(f"{TOKEN_ENV} is not set. Add it to ~/.zshrc (see README) and open a new terminal.")
    from neuprint import Client

    return Client(config.neuprint.server, dataset=config.neuprint.dataset)


def cypher_list(values: list) -> str:
    """Render a Python list as a Cypher list literal (strings double-quoted)."""
    return json.dumps(list(values))


def resolve_types(client, types: list[str]) -> pd.DataFrame:
    """Return bodyId + type for all Neurons whose type is in `types`."""
    query = (
        "MATCH (n:Neuron) WHERE n.type IN " + cypher_list(types) + " "
        "RETURN n.bodyId AS body_id, n.type AS type"
    )
    return client.fetch_custom(query)


def fetch_edges(
    client, body_ids: set[int], direction: str, min_weight: int, weight_field: str
) -> pd.DataFrame:
    """Edges leaving (direction='down') or entering (direction='up') `body_ids`."""
    ids = sorted(body_ids)
    frames: list[pd.DataFrame] = []
    for start in range(0, len(ids), CHUNK_SIZE):
        chunk = cypher_list(ids[start : start + CHUNK_SIZE])
        if direction == "down":
            where = f"a.bodyId IN {chunk}"
        else:
            where = f"b.bodyId IN {chunk}"
        query = (
            "MATCH (a:Neuron)-[e:ConnectsTo]->(b:Neuron) "
            f"WHERE {where} AND e.{weight_field} >= {int(min_weight)} "
            "RETURN a.bodyId AS pre, b.bodyId AS post"
        )
        frames.append(client.fetch_custom(query))
    if not frames:
        return pd.DataFrame({"pre": [], "post": []})
    return pd.concat(frames, ignore_index=True)


def bfs_distances(
    client, start_ids: set[int], hops: int, direction: str, min_weight: int, weight_field: str
) -> dict[int, int]:
    """Breadth-first hop distances from `start_ids` following edges in `direction`."""
    distances: dict[int, int] = {}
    for body_id in start_ids:
        distances[body_id] = 0
    frontier = set(start_ids)
    for hop in range(1, hops + 1):
        if not frontier:
            break
        edges = fetch_edges(client, frontier, direction, min_weight, weight_field)
        if direction == "down":
            neighbours = set(edges["post"].tolist())
        else:
            neighbours = set(edges["pre"].tolist())
        new_ids = neighbours - set(distances)
        for body_id in new_ids:
            distances[body_id] = hop
        frontier = new_ids
        log.info("  %s hop %d: %d edges, %d new neurons", direction, hop, len(edges), len(new_ids))
    return distances


def select_circuit(client, config: CircuitConfig, min_weight: int) -> Selection:
    """Seeds plus every neuron that is within reach of the inputs AND of the outputs."""
    sel = config.selection
    all_seed_types = sel.inputs + sel.hubs + sel.outputs
    seed_types = resolve_types(client, all_seed_types)
    found = set(seed_types["type"].tolist())
    missing = [t for t in all_seed_types if t not in found]
    if missing:
        log.warning("Seed types not found in dataset: %s", missing)

    input_ids = set(seed_types.loc[seed_types["type"].isin(sel.inputs), "body_id"].tolist())
    hub_ids = set(seed_types.loc[seed_types["type"].isin(sel.hubs), "body_id"].tolist())
    output_ids = set(seed_types.loc[seed_types["type"].isin(sel.outputs), "body_id"].tolist())
    if not input_ids or not output_ids:
        raise SystemExit("No input or no output neurons found; check the type names in the config.")

    log.info("Selecting at min_weight=%d", min_weight)
    down = bfs_distances(client, input_ids, sel.hops_down, "down", min_weight, sel.weight_field)
    up = bfs_distances(client, output_ids, sel.hops_up, "up", min_weight, sel.weight_field)
    on_path = set(down) & set(up)
    body_ids = input_ids | hub_ids | output_ids | on_path
    return Selection(body_ids, min_weight, down, up, seed_types)


def fetch_metadata(client, body_ids: set[int]) -> pd.DataFrame:
    """Neuron properties for the selected neurons."""
    ids = sorted(body_ids)
    frames: list[pd.DataFrame] = []
    for start in range(0, len(ids), CHUNK_SIZE):
        chunk = cypher_list(ids[start : start + CHUNK_SIZE])
        query = (
            f"MATCH (n:Neuron) WHERE n.bodyId IN {chunk} RETURN "
            "n.bodyId AS body_id, n.type AS type, n.instance AS instance, n.group AS group_id, "
            "n.somaSide AS soma_side, n.superclass AS superclass, n.subclass AS subclass, "
            "n.class AS cell_class, n.consensusNt AS consensus_nt, n.predictedNt AS predicted_nt, "
            "n.predictedNtConfidence AS predicted_nt_confidence, "
            "n.celltypePredictedNt AS celltype_predicted_nt, "
            "n.celltypePredictedNtConfidence AS celltype_predicted_nt_confidence, "
            "n.pre AS total_pre, n.post AS total_post, n.size AS size, n.status AS status, "
            "n.somaLocation.x AS soma_x, n.somaLocation.y AS soma_y, n.somaLocation.z AS soma_z"
        )
        frames.append(client.fetch_custom(query))
    return pd.concat(frames, ignore_index=True)


def fetch_total_weights(client, body_ids: set[int], weight_field: str) -> pd.DataFrame:
    """Full-dataset input/output synapse totals (from all Neurons), per selected neuron."""
    ids = sorted(body_ids)
    in_frames: list[pd.DataFrame] = []
    out_frames: list[pd.DataFrame] = []
    for start in range(0, len(ids), CHUNK_SIZE):
        chunk = cypher_list(ids[start : start + CHUNK_SIZE])
        in_query = (
            f"MATCH (a:Neuron)-[e:ConnectsTo]->(b:Neuron) WHERE b.bodyId IN {chunk} "
            f"RETURN b.bodyId AS body_id, sum(e.{weight_field}) AS input_weight_total"
        )
        out_query = (
            f"MATCH (a:Neuron)-[e:ConnectsTo]->(b:Neuron) WHERE a.bodyId IN {chunk} "
            f"RETURN a.bodyId AS body_id, sum(e.{weight_field}) AS output_weight_total"
        )
        in_frames.append(client.fetch_custom(in_query))
        out_frames.append(client.fetch_custom(out_query))
    inputs = pd.concat(in_frames, ignore_index=True)
    outputs = pd.concat(out_frames, ignore_index=True)
    base = pd.DataFrame({"body_id": ids})
    merged = base.merge(inputs, on="body_id", how="left").merge(outputs, on="body_id", how="left")
    merged = merged.fillna({"input_weight_total": 0, "output_weight_total": 0})
    return merged.astype({"input_weight_total": "int64", "output_weight_total": "int64"})


def fetch_internal_edges(client, body_ids: set[int], min_weight: int, weight_field: str) -> pd.DataFrame:
    """All edges with both endpoints inside the selected set."""
    ids = sorted(body_ids)
    all_ids = cypher_list(ids)
    frames: list[pd.DataFrame] = []
    for start in range(0, len(ids), CHUNK_SIZE):
        chunk = cypher_list(ids[start : start + CHUNK_SIZE])
        query = (
            "MATCH (a:Neuron)-[e:ConnectsTo]->(b:Neuron) "
            f"WHERE a.bodyId IN {chunk} AND b.bodyId IN {all_ids} "
            f"AND e.{weight_field} >= {int(min_weight)} "
            "RETURN a.bodyId AS pre_id, b.bodyId AS post_id, e.weight AS weight, e.weightHP AS weight_hp"
        )
        frames.append(client.fetch_custom(query))
    edges = pd.concat(frames, ignore_index=True)
    edges = edges.fillna({"weight_hp": 0})
    return edges.astype({"pre_id": "int64", "post_id": "int64", "weight": "int64", "weight_hp": "int64"})


def run(config_name: str) -> Path:
    """Fetch and cache one circuit. Returns the output directory."""
    config = load_config(config_name)
    sel_cfg = config.selection
    client = make_client(config)
    started = time.time()

    min_weight = sel_cfg.min_weight
    raised_from: int | None = None
    while True:
        selection = select_circuit(client, config, min_weight)
        count = len(selection.body_ids)
        log.info("Selected %d neurons at min_weight=%d", count, min_weight)
        if count <= sel_cfg.max_neurons:
            break
        if not sel_cfg.auto_raise_threshold:
            raise SystemExit(
                f"{count} neurons exceeds max_neurons={sel_cfg.max_neurons}; "
                "raise min_weight or enable auto_raise_threshold."
            )
        if raised_from is None:
            raised_from = min_weight
        min_weight = int(math.ceil(min_weight * 1.5))
        log.warning("Over the cap; raising min_weight to %d", min_weight)

    edge_min_weight = sel_cfg.edge_min_weight
    log.info("Fetching metadata, totals and internal edges ...")
    neurons = fetch_metadata(client, selection.body_ids)
    totals = fetch_total_weights(client, selection.body_ids, sel_cfg.weight_field)
    neurons = neurons.merge(totals, on="body_id", how="left")
    neurons["dist_from_inputs"] = neurons["body_id"].map(selection.dist_from_inputs).astype("Int64")
    neurons["dist_to_outputs"] = neurons["body_id"].map(selection.dist_to_outputs).astype("Int64")
    neurons = neurons.sort_values("body_id").reset_index(drop=True)
    edges = fetch_internal_edges(client, selection.body_ids, edge_min_weight, sel_cfg.weight_field)

    out_dir = config.data_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    neurons.to_parquet(out_dir / "neurons.parquet", index=False)
    edges.to_parquet(out_dir / "edges.parquet", index=False)

    seed_counts = selection.seed_types["type"].value_counts().to_dict()
    manifest = {
        "name": config.name,
        "server": config.neuprint.server,
        "dataset": config.neuprint.dataset,
        "neuprint_server_version": str(client.fetch_version()),
        "fetched_at": datetime.now(UTC).isoformat(),
        "selection": sel_cfg.model_dump(),
        "effective_min_weight": min_weight,
        "min_weight_raised_from": raised_from,
        "edge_min_weight": edge_min_weight,
        "n_neurons": int(len(neurons)),
        "n_edges": int(len(edges)),
        "n_synapses": int(edges["weight"].sum()),
        "seed_type_counts": {str(k): int(v) for k, v in seed_counts.items()},
        "fetch_seconds": round(time.time() - started, 1),
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    log.info(
        "Wrote %s: %d neurons, %d edges (%.0fs)",
        out_dir,
        manifest["n_neurons"],
        manifest["n_edges"],
        manifest["fetch_seconds"],
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", required=True, help="Config name (e.g. giant_fiber) or path to YAML")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.config)


if __name__ == "__main__":
    main()
