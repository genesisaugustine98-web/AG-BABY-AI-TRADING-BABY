import json, hashlib
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

class AuditLog:
    def __init__(self, path: str):
        self.path=Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
    def append(self, event_type: str, payload: Any):
        body = asdict(payload) if is_dataclass(payload) else payload
        raw = json.dumps(body, default=str, sort_keys=True, separators=(',', ':'))
        rec={'event_type':event_type,'payload':body,'payload_hash':hashlib.sha256(raw.encode()).hexdigest()}
        with self.path.open('a', encoding='utf-8') as f: f.write(json.dumps(rec, default=str, sort_keys=True)+'\n')
        return rec
