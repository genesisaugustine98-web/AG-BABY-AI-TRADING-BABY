from decimal import Decimal
import json

from apps.research.evidence_engine import compute_stats
from apps.research.evidence_report import build_evidence_row, write_jsonl


def test_build_evidence_row_is_json_safe():
    stats = compute_stats([Decimal("0.01"), Decimal("-0.005")])
    row = build_evidence_row(
        hypothesis_id="H1",
        instrument="EURUSD_REFERENCE",
        horizon=1,
        one_way_cost_bps=Decimal("2"),
        split="development",
        status="completed",
        reason="executed",
        stats=stats,
        dataset_revision_status="revised_history",
    )
    encoded = json.dumps(row, sort_keys=True)
    assert "0.0025" in encoded
    assert row["dataset_revision_status"] == "revised_history"


def test_write_jsonl(tmp_path):
    path = tmp_path / "evidence.jsonl"
    write_jsonl([{"x": "y"}], path)
    assert path.read_text(encoding="utf-8") == '{"x": "y"}\n'
