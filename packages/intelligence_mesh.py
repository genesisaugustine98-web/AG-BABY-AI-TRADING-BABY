"""Provider/model contracts for the institutional FX intelligence mesh.

External text, news, documents and datasets are untrusted inputs. This module defines
an evidence-only interface: adapters produce provenance-rich observations, while the
execution path still requires independent quantitative validation and deterministic risk.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Mapping, Protocol


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source: str
    source_version: str
    observed_at: datetime
    usable_at: datetime
    instrument: str | None
    feature: str
    value: Decimal | str | int | float
    provenance: Mapping[str, str] = field(default_factory=dict)
    trust_class: str = "external"

    def is_usable_at(self, decision_time: datetime) -> bool:
        return self.usable_at <= decision_time


class EvidenceProvider(Protocol):
    name: str

    def fetch(self, *, instrument: str, start: datetime, end: datetime) -> tuple[Evidence, ...]: ...


@dataclass(frozen=True)
class ModelForecast:
    model_id: str
    version: str
    generated_at: datetime
    horizon_seconds: int
    expected_return: Decimal
    probability_up: Decimal
    calibration_score: Decimal
    feature_fingerprint: str
    evidence_ids: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.horizon_seconds < 1:
            raise ValueError("horizon_seconds must be positive")
        if not (Decimal("0") <= self.probability_up <= Decimal("1")):
            raise ValueError("probability_up must be in [0,1]")
        if not (Decimal("0") <= self.calibration_score <= Decimal("1")):
            raise ValueError("calibration_score must be in [0,1]")
        if not self.feature_fingerprint:
            raise ValueError("feature_fingerprint is required")


class ForecastEngine(Protocol):
    name: str

    def predict(self, evidence: tuple[Evidence, ...]) -> ModelForecast: ...


def point_in_time_evidence(evidence: tuple[Evidence, ...], decision_time: datetime) -> tuple[Evidence, ...]:
    """Drop all evidence that was not legally usable at decision time."""
    return tuple(item for item in evidence if item.is_usable_at(decision_time))


def ensemble_forecasts(forecasts: tuple[ModelForecast, ...]) -> ModelForecast:
    """Simple equal-weight ensemble; production weighting belongs in model governance."""
    if not forecasts:
        raise ValueError("at least one forecast required")
    for forecast in forecasts:
        forecast.validate()
    horizon = forecasts[0].horizon_seconds
    if any(f.horizon_seconds != horizon for f in forecasts):
        raise ValueError("all forecasts must share horizon")
    n = Decimal(len(forecasts))
    expected = sum((f.expected_return for f in forecasts), Decimal("0")) / n
    probability = sum((f.probability_up for f in forecasts), Decimal("0")) / n
    calibration = sum((f.calibration_score for f in forecasts), Decimal("0")) / n
    generated_at = max(f.generated_at for f in forecasts)
    evidence_ids = tuple(sorted({e for f in forecasts for e in f.evidence_ids}))
    fingerprint = "ensemble:" + ":".join(sorted(f"{f.model_id}:{f.version}:{f.feature_fingerprint}" for f in forecasts))
    return ModelForecast("ensemble", "1", generated_at, horizon, expected, probability, calibration, fingerprint, evidence_ids)


__all__ = ["Evidence", "EvidenceProvider", "ForecastEngine", "ModelForecast", "ensemble_forecasts", "point_in_time_evidence"]
