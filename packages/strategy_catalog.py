"""Research strategy catalog for the multi-asset research pipeline.

The catalog is deliberately declarative: it describes hypotheses and their
validation constraints, but it cannot submit broker orders. Production/demo
execution remains behind the deterministic execution kernel and risk engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ResearchWindow:
    evaluation_start: str
    evaluation_end: str
    warmup_start: str
    timezone: str = "UTC"


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    name: str
    role: str
    families: tuple[str, ...]
    raw: dict[str, Any]


@dataclass(frozen=True)
class MultiAssetResearchSlate:
    window: ResearchWindow
    asset_universe: dict[str, tuple[str, ...]]
    strategies: tuple[StrategySpec, ...]
    validation_protocol: dict[str, Any]
    live_promotion: str

    def get(self, strategy_id: str) -> StrategySpec:
        for strategy in self.strategies:
            if strategy.strategy_id == strategy_id:
                return strategy
        raise KeyError(strategy_id)


def load_slate(path: str | Path) -> MultiAssetResearchSlate:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))

    window_payload = payload["research_window"]
    window = ResearchWindow(
        evaluation_start=window_payload["evaluation_start"],
        evaluation_end=window_payload["evaluation_end"],
        warmup_start=window_payload["warmup_start"],
        timezone=window_payload.get("timezone", "UTC"),
    )

    universe = {
        key: tuple(values)
        for key, values in payload["asset_universe"].items()
    }
    strategies = tuple(
        StrategySpec(
            strategy_id=item["id"],
            name=item["name"],
            role=item["role"],
            families=tuple(item.get("families", ())),
            raw=item,
        )
        for item in payload["strategies"]
    )

    ids = [strategy.strategy_id for strategy in strategies]
    if len(ids) != len(set(ids)):
        raise ValueError("strategy ids must be unique")
    if window.warmup_start > window.evaluation_start:
        raise ValueError("warmup_start must not be after evaluation_start")
    if window.evaluation_start > window.evaluation_end:
        raise ValueError("evaluation_start must not be after evaluation_end")

    validation_protocol = dict(payload["validation_protocol"])
    live_promotion = validation_protocol.get("live_promotion", "disabled")
    if live_promotion != "disabled":
        raise ValueError("live promotion must remain disabled")

    return MultiAssetResearchSlate(
        window=window,
        asset_universe=universe,
        strategies=strategies,
        validation_protocol=validation_protocol,
        live_promotion=live_promotion,
    )


def default_slate() -> MultiAssetResearchSlate:
    repo_root = Path(__file__).resolve().parents[1]
    return load_slate(repo_root / "configs" / "multiasset_research_slate.json")
