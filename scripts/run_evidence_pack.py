"""Generate the deterministic evidence pack."""
from __future__ import annotations
import argparse,os,json
from packages.evidence_protocol import EvidenceClass,EvidencePack,EvidenceStatus
from scripts.run_control_plane_drills import run_simulated_drills

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--output",default="artifacts/evidence/simulated-evidence.json"); ap.add_argument("--commit-sha",default=os.environ.get("GITHUB_SHA","unknown")); args=ap.parse_args()
    pack=EvidencePack.create(commit_sha=args.commit_sha)
    for name,row in run_simulated_drills().items():
        pack.add(name=name,evidence_class=EvidenceClass.SIMULATED,status=EvidenceStatus(row["status"]),details=row["details"],required_for_gate=False)
    required=[
      ("demo_24h_soak","continuous HFM demo observation"),
      ("demo_reconciliation_drift","intentional internal/broker mismatch produces freeze"),
      ("demo_unknown_recovery","ambiguous demo order resolves from broker truth"),
      ("demo_restart_recovery","actual process restart requires reconciliation"),
      ("demo_network_outage","transport outage remains fail-closed"),
      ("demo_database_outage","database outage remains fail-closed"),
      ("strategy_validation","chronological validation and untouched holdout under explicit costs/delay"),
    ]
    for name,req in required:
        pack.add(name=name,evidence_class=EvidenceClass.HISTORICAL if name=="strategy_validation" else EvidenceClass.LIVE_DEMO,status=EvidenceStatus.UNOBSERVED,details={"requirement":req})
    pack.write_json(args.output); print(json.dumps(pack.summary(),indent=2,sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
