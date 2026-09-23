from decimal import Decimal
import pytest

from apps.trading_runtime.canonical import CanonicalMarketStateFactory
from packages.models import Quote


class GatewayState:
    connected = True


class Gateway:
    gateway = GatewayState()


def factory():
    return CanonicalMarketStateFactory(Gateway(), max_quote_age_ms=1_000)


@pytest.mark.parametrize(
    "bid,ask",
    [
        (Decimal("0"), Decimal("1.0")),
        (Decimal("1.1"), Decimal("1.0")),
    ],
)
def test_malformed_quotes_fail_closed(bid, ask):
    with pytest.raises(RuntimeError):
        factory()(quote=Quote("EURUSD", bid, ask, 1000, "mt5"), now_ms=1000)


def test_future_quote_fails_closed():
    with pytest.raises(RuntimeError):
        factory()(quote=Quote("EURUSD", Decimal("1.0"), Decimal("1.1"), 1100, "mt5"), now_ms=1000)


def test_blank_source_fails_closed():
    with pytest.raises(RuntimeError):
        factory()(quote=Quote("EURUSD", Decimal("1.0"), Decimal("1.1"), 1000, ""), now_ms=1000)
