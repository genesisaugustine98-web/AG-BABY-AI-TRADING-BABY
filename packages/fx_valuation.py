"""Fail-closed FX conversion graph for portfolio USD valuation."""
from __future__ import annotations
from collections import deque
from decimal import Decimal
from typing import Mapping

class USDConversionGraph:
    def __init__(self, rates: Mapping[str, Decimal] | None = None):
        self.rates={}
        for pair, rate in (rates or {}).items():
            self.add_pair(pair, rate)

    def add_pair(self, pair: str, mid: Decimal) -> None:
        token="".join(ch for ch in str(pair).upper() if ch.isalpha())
        if len(token)!=6: raise ValueError(f"FX pair must contain six currency letters:{pair}")
        rate=Decimal(str(mid))
        if rate<=0 or not rate.is_finite(): raise ValueError("FX mid must be positive and finite")
        base, quote=token[:3],token[3:]
        self.rates[(base,quote)]=rate
        self.rates[(quote,base)]=Decimal("1")/rate

    def rate_to_usd(self, currency: str) -> Decimal:
        currency=currency.strip().upper()
        if currency=="USD": return Decimal("1")
        queue=deque([(currency,Decimal("1"),0)])
        visited={currency}
        while queue:
            current, value, depth=queue.popleft()
            if depth>=3: continue
            for (src,dst), rate in self.rates.items():
                if src!=current or dst in visited: continue
                converted=value*rate
                if dst=="USD": return converted
                visited.add(dst); queue.append((dst,converted,depth+1))
        raise RuntimeError(f"USD conversion unavailable:{currency}")

    def quote_notional_usd(self, *, base_ccy: str, quote_ccy: str, units: Decimal, price: Decimal) -> Decimal:
        units=Decimal(str(units)); price=Decimal(str(price))
        if units==0: return Decimal("0")
        if units < 0: sign=Decimal("-1"); units=abs(units)
        else: sign=Decimal("1")
        if price<=0: raise ValueError("price must be positive")
        base=base_ccy.strip().upper(); quote=quote_ccy.strip().upper()
        if base=="USD": return sign*units
        quote_notional=units*price
        return sign*quote_notional*self.rate_to_usd(quote)

__all__=["USDConversionGraph"]
