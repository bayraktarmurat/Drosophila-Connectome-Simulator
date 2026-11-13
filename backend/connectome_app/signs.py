"""Neurotransmitter -> synaptic sign, one sign per presynaptic neuron (Dale's law).

Resolution order per neuron:
  1. config `type_overrides` for the neuron's cell type
  2. `consensus_nt` (neuPrint consensusNt) if it maps to a known sign
  3. `celltype_predicted_nt` if enabled and its confidence is high enough
  4. config `default_sign`
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from connectome_app.config import SignConfig

SOURCE_OVERRIDE = "type_override"
SOURCE_CONSENSUS = "consensus_nt"
SOURCE_CELLTYPE = "celltype_predicted_nt"
SOURCE_DEFAULT = "default"
UNCLEAR_VALUES = {"unclear", "unknown", ""}


@dataclass(frozen=True)
class SignResult:
    """Per-neuron signs plus where each sign came from."""

    signs: np.ndarray
    sources: list[str]
    warnings: list[str] = field(default_factory=list)


def _clean_nt(value: object) -> str | None:
    """Normalize an NT string; None for missing or unclear values."""
    if value is None:
        return None
    if pd.isna(value):
        return None
    text = str(value).strip().lower()
    if text in UNCLEAR_VALUES:
        return None
    return text


def _confidence(value: object) -> float:
    """Confidence as float; missing counts as 0."""
    if value is None:
        return 0.0
    if pd.isna(value):
        return 0.0
    return float(value)


def resolve_signs(neurons: pd.DataFrame, config: SignConfig) -> SignResult:
    """Compute the sign (+1, -1 or 0) for every neuron in `neurons`."""
    n_neurons = len(neurons)
    signs = np.zeros(n_neurons, dtype=np.int8)
    sources: list[str] = []
    warnings: list[str] = []
    unknown_nts: Counter[str] = Counter()
    default_types: Counter[str] = Counter()

    has_consensus = "consensus_nt" in neurons.columns and neurons["consensus_nt"].notna().any()
    has_celltype = "celltype_predicted_nt" in neurons.columns
    if not has_consensus:
        warnings.append(
            "NO NEUROTRANSMITTER PREDICTIONS in the data: signs come only from "
            "type_overrides and default_sign. Inhibition in this model is unreliable."
        )

    types = neurons["type"].tolist()
    if has_consensus:
        consensus = neurons["consensus_nt"].tolist()
    else:
        consensus = [None] * n_neurons
    if has_celltype:
        celltype_nt = neurons["celltype_predicted_nt"].tolist()
        celltype_conf = neurons["celltype_predicted_nt_confidence"].tolist()
    else:
        celltype_nt = [None] * n_neurons
        celltype_conf = [None] * n_neurons

    for i in range(n_neurons):
        cell_type = types[i]
        if cell_type in config.type_overrides:
            signs[i] = config.type_overrides[cell_type]
            sources.append(SOURCE_OVERRIDE)
            continue

        nt = _clean_nt(consensus[i])
        if nt is not None:
            if nt in config.nt_sign:
                signs[i] = config.nt_sign[nt]
                sources.append(SOURCE_CONSENSUS)
                continue
            unknown_nts[nt] += 1

        if config.use_celltype_fallback:
            fallback_nt = _clean_nt(celltype_nt[i])
            confident = _confidence(celltype_conf[i]) >= config.min_celltype_confidence
            if fallback_nt is not None and fallback_nt in config.nt_sign and confident:
                signs[i] = config.nt_sign[fallback_nt]
                sources.append(SOURCE_CELLTYPE)
                continue

        signs[i] = config.default_sign
        sources.append(SOURCE_DEFAULT)
        default_types[str(cell_type)] += 1

    if unknown_nts:
        warnings.append(f"NT values without a sign in config.nt_sign: {dict(unknown_nts)}")
    n_default = sum(default_types.values())
    if n_default > 0:
        top = ", ".join(f"{name} ({count})" for name, count in default_types.most_common(8))
        warnings.append(
            f"{n_default} neurons have no usable NT prediction and use default_sign="
            f"{config.default_sign}. Most common types: {top}"
        )
    n_zero = int(np.sum(signs == 0))
    if n_zero > 0:
        warnings.append(f"{n_zero} neurons have sign 0 (neuromodulators): their output is ignored.")
    return SignResult(signs=signs, sources=sources, warnings=warnings)
