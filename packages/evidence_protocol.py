"""Evidence-pack primitives with explicit provenance and fail-closed aggregation."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any

class EvidenceStatus(str, Enum):
    PASS="PASS"; FAIL="FAIL"; UNOBSERVED="UNOBSERVED"; NOT_APPLICABLE="NOT_APPLICABLE"

class EvidenceClass(str, Enum):
    HISTORICAL="HISTORICAL"; SIMULATED="SIMULATED"; LIVE_DEMO="LIVE_DEMO"; OPERATOR="OPERATOR"

@dataclass(frozen=True)
class EvidenceRecord:
    name:str; evidence_class:EvidenceClass; status:EvidenceStatus; observed_at:str
    details:dict[str,Any]; artifact:str|None=None; required_for_gate:bool=True

@dataclass
class EvidencePack:
    commit_sha:str; generated_at:str; records:list[EvidenceRecord]
    @classmethod
    def create(cls, *, commit_sha:str)->"EvidencePack":
        return cls(str(commit_sha).strip() or "unknown",datetime.now(timezone.utc).isoformat(),[])
    def add(self, *, name:str, evidence_class:EvidenceClass, status:EvidenceStatus, details:dict[str,Any]|None=None, artifact:str|None=None, required_for_gate:bool=True)->None:
        if any(r.name==name for r in self.records): raise ValueError(f"duplicate evidence record:{name}")
        self.records.append(EvidenceRecord(name,evidence_class,status,datetime.now(timezone.utc).isoformat(),dict(details or {}),artifact,required_for_gate))
    def required_records(self)->tuple[EvidenceRecord,...]: return tuple(r for r in self.records if r.required_for_gate)
    def gate_status(self)->EvidenceStatus:
        req=self.required_records()
        if not req: return EvidenceStatus.UNOBSERVED
        if any(r.status==EvidenceStatus.FAIL for r in req): return EvidenceStatus.FAIL
        if any(r.status==EvidenceStatus.UNOBSERVED for r in req): return EvidenceStatus.UNOBSERVED
        return EvidenceStatus.PASS
    def summary(self)->dict[str,Any]:
        counts={}
        for r in self.records: counts[r.status.value]=counts.get(r.status.value,0)+1
        return {"commit_sha":self.commit_sha,"generated_at":self.generated_at,"gate_status":self.gate_status().value,"counts":counts,"records":[asdict(r) for r in self.records]}
    def write_json(self,path:str|Path)->None:
        p=Path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(self.summary(),indent=2,sort_keys=True,default=str)+"\n",encoding="utf-8")

__all__=["EvidenceClass","EvidencePack","EvidenceRecord","EvidenceStatus"]
