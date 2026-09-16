from decimal import Decimal

import pytest

from apps.research.research_governance import EvidenceRecord, Hypothesis, canonical_hash, append_negative_knowledge


def test_hypothesis_split_must_sum_to_one():
    h = Hypothesis("H1", "statement", "momentum", ("EURUSD_REFERENCE",), (1,), Decimal("0.6"), Decimal("0.2"), Decimal("0.2"))
    h.validate()

    bad = Hypothesis("H1", "statement", "momentum", ("EURUSD_REFERENCE",), (1,), Decimal("0.7"), Decimal("0.2"), Decimal("0.2"))
    with pytest.raises(ValueError):
        bad.validate()


def record(outcome: str = "not_supported") -> EvidenceRecord:
    return EvidenceRecord(
        hypothesis_id="H1",
        sample_start="2020-01-01",
        sample_end="2025-12-31",
        split="holdout",
        instrument="EURUSD_REFERENCE",
        horizon=1,
        one_way_cost_bps=Decimal("5"),
        n=100,
        mean_net=Decimal("-0.001"),
        cumulative_net=Decimal("-0.1"),
        max_drawdown=Decimal("-0.12"),
        outcome=outcome,
        dataset_revision_status="revised_history",
    )


def test_negative_knowledge_is_append_only(tmp_path):
    path = tmp_path / "negative.jsonl"
    rec = record()
    append_negative_knowledge(path, rec, "negative holdout")
    append_negative_knowledge(path, rec, "same failure reproduced")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert canonical_hash(rec) in lines[0]


def test_supported_record_cannot_enter_negative_knowledge(tmp_path):
    with pytest.raises(ValueError):
        append_negative_knowledge(tmp_path / "negative.jsonl", record("supported"), "bad call")
