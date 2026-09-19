"""Fixed-design time-series-momentum forecast engine.

This module turns completed price bars into a reproducible forecast. It does not
claim profitability and it does not submit orders. Model parameters are fixed at
fit time; no parameter search is performed inside the fit.

The probability estimate is a Laplace-smoothed historical hit rate conditioned on
three fixed momentum-strength buckets. The calibration score is one minus the
validation expected-calibration-error (ECE), clipped to [0,1]. Both are descriptive
statistics and must be combined with the separate research/economic gates before
a model can be promoted.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from math import isfinite
from typing import Iterable

from .models import Forecast
from .research_quality import expected_calibration_error

D0 = Decimal("0")
D1 = Decimal("1")


@dataclass(frozen=True)
class PriceBar:
    symbol: str
    event_time_ms: int
    usable_at_ms: int
    close: Decimal
    source: str
    source_version: str
    observation_id: str

    def validate(self) -> None:
        if not self.symbol.strip() or not self.source.strip() or not self.source_version.strip():
            raise ValueError("bar provenance is required")
        if not self.observation_id.strip():
            raise ValueError("observation_id is required")
        if self.event_time_ms <= 0 or self.usable_at_ms <= 0:
            raise ValueError("timestamps must be positive")
        if self.usable_at_ms < self.event_time_ms:
            raise ValueError("usable_at_ms cannot precede event_time_ms")
        if self.close <= 0:
            raise ValueError("close must be positive")


@dataclass(frozen=True)
class _BucketStats:
    n: int
    probability: Decimal
    expected_directional_return: Decimal


@dataclass(frozen=True)
class TSMOMValidation:
    model_id: str
    version: str
    lookback_bars: int
    horizon_bars: int
    development_n: int
    validation_n: int
    holdout_n: int
    validation_ece: Decimal
    calibration_score: Decimal
    feature_fingerprint: str
    dataset_fingerprint: str
    code_commit_sha: str
    calibration_gate: str
    validation_status: str


@dataclass(frozen=True)
class _Sample:
    signal: int
    bucket: int
    probability: Decimal
    directional_return: Decimal
    outcome: int


def _bucket(abs_z: Decimal) -> int:
    if abs_z < Decimal("0.5"):
        return 0
    if abs_z < Decimal("1.0"):
        return 1
    return 2


def _returns(closes: list[Decimal]) -> list[Decimal]:
    return [closes[i] / closes[i - 1] - D1 for i in range(1, len(closes))]


def _zscore(momentum: Decimal, one_bar_returns: list[Decimal]) -> Decimal:
    if len(one_bar_returns) < 2:
        return D0
    mean = sum(one_bar_returns, D0) / Decimal(len(one_bar_returns))
    variance = sum((x - mean) ** 2 for x in one_bar_returns) / Decimal(len(one_bar_returns))
    if variance <= 0:
        return D0
    return momentum / variance.sqrt()


class TSMOMForecastModel:
    MODEL_ID = "tsmom-fixed-v1"
    VERSION = "1"

    def __init__(
        self,
        *,
        lookback_bars: int = 24,
        horizon_bars: int = 6,
        min_training_samples: int = 30,
        bar_interval_seconds: int = 3600,
    ) -> None:
        if lookback_bars < 2 or horizon_bars < 1 or bar_interval_seconds < 1:
            raise ValueError("lookback_bars, horizon_bars and bar_interval_seconds must be positive")
        if min_training_samples < 10:
            raise ValueError("min_training_samples must be >= 10")
        self.lookback_bars = lookback_bars
        self.horizon_bars = horizon_bars
        self.min_training_samples = min_training_samples
        self.bar_interval_seconds = bar_interval_seconds
        self._buckets: dict[int, _BucketStats] = {}
        self._fallback: _BucketStats | None = None
        self.validation: TSMOMValidation | None = None
        self._fitted = False

    @staticmethod
    def _samples(bars: list[PriceBar], start: int, end: int, lookback: int, horizon: int) -> list[tuple[int, int, int, Decimal]]:
        samples: list[tuple[int, int, int, Decimal]] = []
        closes = [x.close for x in bars]
        one_bar = _returns(closes)
        first = max(start, lookback)
        # Keep the forward target strictly inside the same chronological split.
        # Otherwise a development/validation sample near the boundary can consume
        # a label from the next split, creating target leakage.
        last = min(end - horizon - 1, len(bars) - horizon - 1)
        for i in range(first, last + 1):
            momentum = closes[i] / closes[i - lookback] - D1
            signal = 1 if momentum > 0 else -1 if momentum < 0 else 0
            if signal == 0:
                continue
            window_start = max(1, i - lookback + 1)
            z = _zscore(momentum, one_bar[window_start - 1:i])
            bucket = _bucket(abs(z))
            forward = closes[i + horizon] / closes[i] - D1
            samples.append((signal, bucket, i, forward))
        return samples

    @staticmethod
    def _fit_stats(samples: list[tuple[int, int, int, Decimal]]) -> tuple[dict[int, _BucketStats], _BucketStats]:
        grouped: dict[int, list[Decimal]] = {0: [], 1: [], 2: []}
        for signal, bucket, _, forward in samples:
            grouped[bucket].append(signal * forward)
        all_directional = [signal * forward for signal, _, _, forward in samples]
        if not all_directional:
            raise ValueError("no training samples")
        fallback_n = len(all_directional)
        fallback_wins = sum(1 for value in all_directional if value > 0)
        fallback_prob = (Decimal(fallback_wins) + D1) / (Decimal(fallback_n) + Decimal("2"))
        fallback = _BucketStats(
            fallback_n,
            fallback_prob,
            sum(all_directional, D0) / Decimal(fallback_n),
        )
        stats: dict[int, _BucketStats] = {}
        for bucket, values in grouped.items():
            if not values:
                stats[bucket] = fallback
                continue
            wins = sum(1 for value in values if value > 0)
            stats[bucket] = _BucketStats(
                len(values),
                (Decimal(wins) + D1) / (Decimal(len(values)) + Decimal("2")),
                sum(values, D0) / Decimal(len(values)),
            )
        return stats, fallback

    def fit(
        self,
        bars: Iterable[PriceBar],
        *,
        development_fraction: Decimal = Decimal("0.60"),
        validation_fraction: Decimal = Decimal("0.20"),
        dataset_fingerprint: str,
        code_commit_sha: str,
    ) -> TSMOMValidation:
        rows = sorted(list(bars), key=lambda x: (x.event_time_ms, x.usable_at_ms, x.observation_id))
        for row in rows:
            row.validate()
        if not rows:
            raise ValueError("at least one bar is required")
        if any(rows[i].event_time_ms <= rows[i - 1].event_time_ms for i in range(1, len(rows))):
            raise ValueError("bars must have strictly increasing event_time_ms")
        holdout_fraction = D1 - development_fraction - validation_fraction
        if development_fraction <= 0 or validation_fraction <= 0 or holdout_fraction <= 0:
            raise ValueError("development, validation and holdout fractions must all be positive")

        sample_start = self.lookback_bars
        total_usable = len(rows) - self.horizon_bars - self.lookback_bars
        if total_usable < self.min_training_samples * 3:
            raise ValueError("insufficient bars for development/validation/holdout samples")

        dev_end = int(len(rows) * development_fraction)
        val_end = dev_end + int(len(rows) * validation_fraction)
        if dev_end <= sample_start or val_end <= dev_end:
            raise ValueError("chronological split leaves no training data")

        dev_samples = self._samples(rows, sample_start, dev_end - 1, self.lookback_bars, self.horizon_bars)
        val_samples = self._samples(rows, dev_end, val_end - 1, self.lookback_bars, self.horizon_bars)
        holdout_samples = self._samples(rows, val_end, len(rows) - 1, self.lookback_bars, self.horizon_bars)
        if len(dev_samples) < self.min_training_samples:
            raise ValueError("development sample below minimum")

        self._buckets, self._fallback = self._fit_stats(dev_samples)

        probabilities: list[Decimal] = []
        outcomes: list[int] = []
        for signal, bucket, _, forward in val_samples:
            stats = self._buckets.get(bucket, self._fallback)
            assert stats is not None
            probabilities.append(stats.probability if signal == 1 else D1 - stats.probability)
            outcomes.append(1 if signal * forward > 0 else 0)
        ece = expected_calibration_error(probabilities, outcomes) if probabilities else D1
        calibration = max(D0, min(D1, D1 - ece))
        self._fitted = True

        feature_fingerprint = sha256(
            f"{self.MODEL_ID}|{self.VERSION}|lookback={self.lookback_bars}|horizon={self.horizon_bars}|bar_interval={self.bar_interval_seconds}|buckets=0.5,1.0".encode()
        ).hexdigest()
        calibration_gate = "passed" if (
            len(val_samples) >= self.min_training_samples and
            calibration >= Decimal("0.65")
        ) else "failed"
        # Economic validation is deliberately separate. This fit never upgrades a
        # model to "validated" merely because its calibration gate passed.
        validation_status = "candidate"
        self.validation = TSMOMValidation(
            self.MODEL_ID, self.VERSION, self.lookback_bars, self.horizon_bars,
            len(dev_samples), len(val_samples), len(holdout_samples),
            ece, calibration, feature_fingerprint,
            dataset_fingerprint, code_commit_sha, calibration_gate, validation_status,
        )
        return self.validation

    def predict(self, bars: Iterable[PriceBar], *, decision_time_ms: int) -> Forecast:
        if not self._fitted or self.validation is None or self._fallback is None:
            raise RuntimeError("model must be fitted before predict")
        rows = [x for x in bars if x.usable_at_ms <= decision_time_ms]
        rows.sort(key=lambda x: (x.event_time_ms, x.usable_at_ms, x.observation_id))
        if len(rows) < self.lookback_bars + 1:
            raise ValueError("insufficient point-in-time bars for prediction")
        current = rows[-1]
        closes = [x.close for x in rows]
        momentum = closes[-1] / closes[-1 - self.lookback_bars] - D1
        signal = 1 if momentum > 0 else -1 if momentum < 0 else 0
        if signal == 0:
            raise ValueError("zero momentum does not produce a directional forecast")
        one_bar = _returns(closes)
        z = _zscore(momentum, one_bar[-self.lookback_bars:])
        stats = self._buckets.get(_bucket(abs(z)), self._fallback)
        assert stats is not None
        expected = stats.expected_directional_return * signal
        probability_up = stats.probability if signal == 1 else D1 - stats.probability
        evidence_ids = tuple(x.observation_id for x in rows[-self.lookback_bars - 1:])
        return Forecast(
            self.MODEL_ID,
            self.VERSION,
            current.event_time_ms,
            self.horizon_seconds,
            expected,
            "fraction",
            probability_up,
            self.validation.calibration_score,
            min(D1, max(D0, abs(z) / Decimal("3"))),
            frozenset(x.observation_id for x in rows[-self.lookback_bars - 1:]),
        )

    @property
    def horizon_seconds(self) -> int:
        # Callers using non-hourly bars should override this conversion at their adapter boundary.
        return self.horizon_bars * self.bar_interval_seconds


def dataset_fingerprint(bars: Iterable[PriceBar]) -> str:
    rows = sorted(
        (
            x.symbol, x.event_time_ms, x.usable_at_ms, str(x.close),
            x.source, x.source_version, x.observation_id
        )
        for x in bars
    )
    payload = "\n".join("|".join(map(str, row)) for row in rows)
    return sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["PriceBar", "TSMOMForecastModel", "TSMOMValidation", "dataset_fingerprint"]
