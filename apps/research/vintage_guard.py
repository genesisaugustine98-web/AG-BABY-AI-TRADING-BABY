"""Guards against falsely treating revised H.10 history as historical vintages."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VintageAssessment:
    dataset_revision_status: str
    has_observation_level_release_vintage: bool
    execution_grade: bool
    allowed_for_causal_backtest: bool
    reason: str


def assess_dataset(
    *,
    dataset_revision_status: str,
    has_observation_level_release_vintage: bool,
    execution_grade: bool,
) -> VintageAssessment:
    """Return a fail-closed assessment for historical research provenance."""
    if execution_grade:
        return VintageAssessment(
            dataset_revision_status,
            has_observation_level_release_vintage,
            execution_grade,
            False,
            "H.10 reference data is not execution-grade market data",
        )
    if dataset_revision_status != "point_in_time_vintage":
        return VintageAssessment(
            dataset_revision_status,
            has_observation_level_release_vintage,
            execution_grade,
            False,
            "revised history is not sufficient to claim historical release-vintage causality",
        )
    if not has_observation_level_release_vintage:
        return VintageAssessment(
            dataset_revision_status,
            has_observation_level_release_vintage,
            execution_grade,
            False,
            "each observation must carry its genuine historical publication vintage",
        )
    return VintageAssessment(
        dataset_revision_status,
        has_observation_level_release_vintage,
        execution_grade,
        True,
        "point-in-time release vintage is present",
    )
