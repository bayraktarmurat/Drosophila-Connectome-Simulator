"""Circuit configuration: YAML file -> validated pydantic models.

A config may contain `extends: other.yaml`; the other file is loaded first and this
file's keys are deep-merged on top of it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
CONFIG_DIR: Path = PROJECT_ROOT / "configs"
DATA_DIR_ENV: str = "CONNECTOME_DATA_DIR"


class StrictModel(BaseModel):
    """Base model that rejects unknown keys, so config typos fail loudly."""

    model_config = ConfigDict(extra="forbid")


class NeuprintConfig(StrictModel):
    server: str
    dataset: str


class SelectionConfig(StrictModel):
    inputs: list[str]
    hubs: list[str] = Field(default_factory=list)
    outputs: list[str]
    hops_down: int = Field(default=2, ge=0, le=4)
    hops_up: int = Field(default=2, ge=0, le=4)
    min_weight: int = Field(default=10, ge=1)
    edge_min_weight: int = Field(default=10, ge=1)
    max_neurons: int = Field(default=5000, ge=1)
    auto_raise_threshold: bool = True
    weight_field: Literal["weight", "weightHP"] = "weight"


class SignConfig(StrictModel):
    nt_sign: dict[str, int]
    use_celltype_fallback: bool = True
    min_celltype_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    default_sign: int = Field(default=1, ge=-1, le=1)
    type_overrides: dict[str, int] = Field(default_factory=dict)


class PathFinderConfig(StrictModel):
    normalization: Literal["post", "input_weight"] = "post"


class ExtraEdgeSpec(StrictModel):
    pre_type: str
    post_type: str
    kind: Literal["electrical", "chemical"] = "electrical"
    pairing: Literal["strongest_chemical", "same_side", "all"] = "strongest_chemical"
    synapse_equivalent: float = Field(gt=0)
    source_key: str


class ExtraEdgesConfig(StrictModel):
    enabled: bool = False
    edges: list[ExtraEdgeSpec] = Field(default_factory=list)


class SimulationConfig(StrictModel):
    dt_ms: float = Field(default=0.1, gt=0)
    tau_m_ms: float = Field(default=20.0, gt=0)
    v_rest_mv: float = -52.0
    v_reset_mv: float = -52.0
    v_threshold_mv: float = -45.0
    refractory_ms: float = Field(default=2.0, ge=0)
    tau_syn_ms: float = Field(default=5.0, gt=0)
    w_syn_mv: float = 0.3
    delay_ms: float = Field(default=2.0, ge=0)
    electrical_delay_ms: float = Field(default=0.1, ge=0)
    default_duration_ms: float = Field(default=1000.0, gt=0)
    default_trials: int = Field(default=10, ge=1)
    base_seed: int = 12345


class CircuitConfig(StrictModel):
    name: str
    description: str = ""
    neuprint: NeuprintConfig
    selection: SelectionConfig
    signs: SignConfig
    path_finder: PathFinderConfig = Field(default_factory=PathFinderConfig)
    extra_edges: ExtraEdgesConfig = Field(default_factory=ExtraEdgesConfig)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)

    def data_dir(self) -> Path:
        """Directory holding the cached parquet files for this circuit."""
        override = os.environ.get(DATA_DIR_ENV)
        if override:
            return Path(override) / self.name
        return PROJECT_ROOT / "data" / self.name


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict with `override` merged recursively into `base`."""
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(base_value, value)
        else:
            merged[key] = value
    return merged


def _load_raw(path: Path, seen: set[Path]) -> dict[str, Any]:
    """Load a YAML file and resolve its `extends` chain."""
    resolved = path.resolve()
    if resolved in seen:
        raise ValueError(f"Circular 'extends' in config: {resolved}")
    seen.add(resolved)
    with resolved.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if raw is None:
        raw = {}
    parent_name = raw.pop("extends", None)
    if parent_name is None:
        return raw
    parent_path = resolved.parent / parent_name
    parent_raw = _load_raw(parent_path, seen)
    return _deep_merge(parent_raw, raw)


def resolve_config_path(name_or_path: str | Path) -> Path:
    """Accept a config name ('giant_fiber') or a path to a YAML file."""
    candidate = Path(name_or_path)
    if candidate.suffix in (".yaml", ".yml"):
        return candidate
    return CONFIG_DIR / f"{name_or_path}.yaml"


def load_config(name_or_path: str | Path) -> CircuitConfig:
    """Load and validate a circuit config."""
    path = resolve_config_path(name_or_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    raw = _load_raw(path, set())
    return CircuitConfig.model_validate(raw)


def list_configs() -> list[str]:
    """Names of all configs in the configs/ directory."""
    names: list[str] = []
    for path in sorted(CONFIG_DIR.glob("*.yaml")):
        names.append(path.stem)
    return names
