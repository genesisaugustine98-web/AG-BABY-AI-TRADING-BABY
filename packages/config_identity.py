"""Deterministic, secret-free identity for an autonomous runtime configuration."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def config_fingerprint(config: Any, *, excluded_fields: frozenset[str] = frozenset()) -> str:
    if not is_dataclass(config):
        raise TypeError("config_fingerprint expects a dataclass instance")
    payload = _jsonable(config)
    if not isinstance(payload, dict):
        raise TypeError("dataclass configuration must serialize to an object")
    for field in excluded_fields:
        payload.pop(field, None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["config_fingerprint"]
