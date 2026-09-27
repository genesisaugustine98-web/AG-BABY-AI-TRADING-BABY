from dataclasses import dataclass
from decimal import Decimal

from packages.config_identity import config_fingerprint


@dataclass(frozen=True)
class Config:
    size: Decimal
    symbols: tuple[str, ...]


def test_config_fingerprint_is_deterministic():
    left = Config(Decimal("0.01"), ("EURUSD", "GBPUSD"))
    right = Config(Decimal("0.01"), ("EURUSD", "GBPUSD"))
    assert config_fingerprint(left) == config_fingerprint(right)


def test_material_config_change_changes_fingerprint():
    left = Config(Decimal("0.01"), ("EURUSD",))
    right = Config(Decimal("0.02"), ("EURUSD",))
    assert config_fingerprint(left) != config_fingerprint(right)


def test_excluded_field_does_not_change_fingerprint():
    left = {"alpha": Decimal("1"), "secret_runtime": "a"}
    right = {"alpha": Decimal("1"), "secret_runtime": "b"}

    @dataclass(frozen=True)
    class Wrapper:
        alpha: Decimal
        secret_runtime: str

    assert config_fingerprint(Wrapper(**left), excluded_fields=frozenset({"secret_runtime"})) == config_fingerprint(
        Wrapper(**right), excluded_fields=frozenset({"secret_runtime"})
    )
