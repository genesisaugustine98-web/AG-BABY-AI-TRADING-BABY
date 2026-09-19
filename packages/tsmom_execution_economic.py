"""Execution-price-aware economic replay for fixed TSMOM research.

The replay uses historical Bid/Ask quotes at scheduled entry/exit timestamps and
explicitly parameterized slippage, commission and financing assumptions. It never
submits orders and never promotes a model.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from typing import Callable, Iterable, Sequence

from apps.execution_gateway.mt5_quote_history import HistoricalQuote
from packages.tsmom_forecast import PriceBar, TSMOMForecastModel

D0 = Decimal("0")
D1 = Decimal("1")
D10000 = Decimal("10000")


@dataclass(frozen=True)
class ExecutionEconomicResult:
    split: str
    n: int
    skipped_no_signal: int
    missing_entry_quote: int
    missing_exit_quote: int
    sample_start: int | None
    sample_end: int | None
    max_quote_gap_ms: int
    slippage_one_way_bps: Decimal
    commission_one_way_bps: Decimal
    financing_bps_per_day: Decimal
    mean_gross: Decimal | None
    mean_net: Decimal | None
    cumulative_net: Decimal | None
    max_drawdown: Decimal | None
    win_rate_net: Decimal | None
    profit_factor: Decimal | None
    sharpe_like: Decimal | None
    mean_entry_spread_bps: Decimal | None
    median_entry_spread_bps: Decimal | None


def _max_drawdown(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    wealth = D1
    peak = D1
    worst = D0
    for value in values:
        wealth *= D1 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - D1)
    return abs(worst)


def _median(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _summarize(
    *,
    split: str,
    rows: list[tuple[int, Decimal, Decimal, Decimal]],
    skipped_no_signal: int,
    missing_entry_quote: int,
    missing_exit_quote: int,
    max_quote_gap_ms: int,
    slippage_one_way_bps: Decimal,
    commission_one_way_bps: Decimal,
    financing_bps_per_day: Decimal,
) -> ExecutionEconomicResult:
    if not rows:
        return ExecutionEconomicResult(
            split, 0, skipped_no_signal, missing_entry_quote, missing_exit_quote,
            None, None, max_quote_gap_ms, slippage_one_way_bps,
            commission_one_way_bps, financing_bps_per_day,
            None, None, None, None, None, None, None, None, None
        )

    gross = [row[1] for row in rows]
    net = [row[2] for row in rows]
    spreads = [row[3] for row in rows]
    mean_gross = sum(gross, D0) / Decimal(len(gross))
    mean_net = sum(net, D0) / Decimal(len(net))
    cumulative = D1
    for value in net:
        cumulative *= D1 + value
    cumulative -= D1
    wins = sum(1 for value in net if value > D0)
    losses = sum(1 for value in net if value < D0)
    loss_sum = abs(sum((value for value in net if value < D0), D0))
    profit_factor = sum((value for value in net if value > D0), D0) / loss_sum if loss_sum > D0 else None
    variance = (
        sum((value - mean_net) ** 2 for value in net) / Decimal(len(net) - 1)
        if len(net) > 1 else D0
    )
    std = variance.sqrt() if variance > D0 else D0
    sharpe_like = mean_net / std * Decimal(str(sqrt(len(net)))) if std > D0 else None
    return ExecutionEconomicResult(
        split, len(rows), skipped_no_signal, missing_entry_quote, missing_exit_quote,
        rows[0][0], rows[-1][0], max_quote_gap_ms, slippage_one_way_bps,
        commission_one_way_bps, financing_bps_per_day, mean_gross, mean_net,
        cumulative, _max_drawdown(net), Decimal(wins) / Decimal(len(net)),
        profit_factor, sharpe_like,
        sum(spreads, D0) / Decimal(len(spreads)), _median(spreads)
    )


def _worse_execution_price(*, side: str, price: Decimal, entry: bool, slippage_bps: Decimal) -> Decimal:
    slip = slippage_bps / D10000
    if side == "BUY":
        return price * (D1 + slip) if entry else price * (D1 - slip)
    if side == "SELL":
        return price * (D1 - slip) if entry else price * (D1 + slip)
    raise ValueError("side must be BUY or SELL")


def evaluate_split_with_quotes(
    model: TSMOMForecastModel,
    bars: Iterable[PriceBar],
    *,
    split: str,
    start_index: int,
    end_index: int,
    quote_provider: Callable[[int], HistoricalQuote | None],
    max_quote_gap_ms: int = 300_000,
    slippage_one_way_bps: Decimal = D0,
    commission_one_way_bps: Decimal = D0,
    financing_bps_per_day: Decimal = D0,
    delay_bars: int = 1,
) -> ExecutionEconomicResult:
    """Evaluate one frozen-model split against historical executable Bid/Ask quotes.

    The quote provider must return the first quote at/after the requested execution
    timestamp, or None when no quote is available within max_quote_gap_ms.
    """
    rows = sorted(list(bars), key=lambda x: (x.event_time_ms, x.usable_at_ms, x.observation_id))
    if start_index < 0 or end_index <= start_index or end_index > len(rows):
        raise ValueError("invalid split bounds")
    for value, name in (
        (slippage_one_way_bps, "slippage_one_way_bps"),
        (commission_one_way_bps, "commission_one_way_bps"),
        (financing_bps_per_day, "financing_bps_per_day"),
    ):
        if value < D0:
            raise ValueError(f"{name} cannot be negative")
    if max_quote_gap_ms < 0:
        raise ValueError("max_quote_gap_ms cannot be negative")
    if delay_bars < 0:
        raise ValueError("delay_bars cannot be negative")

    trades: list[tuple[int, Decimal, Decimal, Decimal]] = []
    skipped_no_signal = 0
    missing_entry_quote = 0
    missing_exit_quote = 0
    first = max(start_index, model.lookback_bars)
    last = min(
        end_index - 1 - delay_bars - model.horizon_bars,
        len(rows) - 1 - delay_bars - model.horizon_bars,
    )
    for i in range(first, last + 1):
        decision = rows[i]
        lookback_price = rows[i - model.lookback_bars].close
        momentum = decision.close / lookback_price - D1
        if momentum == D0:
            skipped_no_signal += 1
            continue

        forecast = model.predict_at_index(rows, decision_index=i)
        side = "BUY" if forecast.expected_return > D0 else "SELL"
        entry_bar = rows[i + delay_bars]
        exit_bar = rows[i + delay_bars + model.horizon_bars]
        entry_quote = quote_provider(entry_bar.event_time_ms)
        if entry_quote is None:
            missing_entry_quote += 1
            continue
        exit_quote = quote_provider(exit_bar.event_time_ms)
        if exit_quote is None:
            missing_exit_quote += 1
            continue

        if side == "BUY":
            raw_entry = entry_quote.ask
            raw_exit = exit_quote.bid
        else:
            raw_entry = entry_quote.bid
            raw_exit = exit_quote.ask

        entry = _worse_execution_price(
            side=side, price=raw_entry, entry=True, slippage_bps=slippage_one_way_bps
        )
        exit = _worse_execution_price(
            side=side, price=raw_exit, entry=False, slippage_bps=slippage_one_way_bps
        )

        if side == "BUY":
            gross = exit / entry - D1
        else:
            gross = entry / exit - D1

        holding_days = Decimal(
            max(0, exit_bar.event_time_ms - entry_bar.event_time_ms)
        ) / Decimal(86_400_000)
        financing = holding_days * financing_bps_per_day / D10000
        commission = Decimal("2") * commission_one_way_bps / D10000
        net = gross - financing - commission
        spread_bps = (
            (entry_quote.ask - entry_quote.bid) / entry_quote.mid * D10000
        )
        trades.append((entry_bar.event_time_ms, gross, net, spread_bps))

    return _summarize(
        split=split,
        rows=trades,
        skipped_no_signal=skipped_no_signal,
        missing_entry_quote=missing_entry_quote,
        missing_exit_quote=missing_exit_quote,
        max_quote_gap_ms=max_quote_gap_ms,
        slippage_one_way_bps=slippage_one_way_bps,
        commission_one_way_bps=commission_one_way_bps,
        financing_bps_per_day=financing_bps_per_day,
    )


__all__ = ["ExecutionEconomicResult", "evaluate_split_with_quotes"]
