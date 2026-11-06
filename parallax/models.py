from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_DOWN
from math import lcm
import time

D = Decimal

@dataclass
class Market:
    venue: str
    kind: str
    symbol: str
    base: str
    step: D
    minimum: D
    min_notional: D
    tick: D
    multiplier: D = D(1)
    quote: str = 'USDT'
    funding_rate: str | None = None
    funding_interval_hours: float | None = None
    url: str = ''

    @property
    def key(self): return f'{self.venue}:{self.kind}:{self.symbol}'

    def public(self):
        return {k: str(v) if isinstance(v, D) else v for k,v in asdict(self).items()} | {'key': self.key}

@dataclass
class Book:
    bids: dict = field(default_factory=dict)
    asks: dict = field(default_factory=dict)
    received: float = 0
    mono: float = 0
    exchange_ms: float = 0
    sequence: int = 0
    valid: bool = False

    def apply(self, bids, asks, snapshot=True, sequence=0, exchange_ms=0, multiplier=D(1), max_depth=50):
        if not snapshot and not self.valid:
            raise ValueError('delta before snapshot')
        if not snapshot and sequence and sequence <= self.sequence:
            return False
        if snapshot:
            self.bids.clear(); self.asks.clear()
        for target, rows in ((self.bids,bids),(self.asks,asks)):
            for row in rows:
                p,q = (row['p'],row['s']) if isinstance(row,dict) else row[:2]
                p,q = D(str(p)), D(str(q))*multiplier
                if not p.is_finite() or not q.is_finite() or p <= 0 or q < 0: raise ValueError('invalid level')
                if q == 0: target.pop(p,None)
                else: target[p] = q
        # Channels deliver bounded depth. Never retain older levels beyond it.
        self.bids = dict(sorted(self.bids.items(),reverse=True)[:max_depth])
        self.asks = dict(sorted(self.asks.items())[:max_depth])
        self.sequence=sequence; self.exchange_ms=exchange_ms
        self.received=time.time(); self.mono=time.monotonic()
        self.valid=bool(self.bids and self.asks and max(self.bids)<min(self.asks))
        return True

    def levels(self,side): return sorted(getattr(self,side).items(),reverse=side=='bids')


def common_step(a:D,b:D)->D:
    places=max(0,-a.as_tuple().exponent,-b.as_tuple().exponent)
    scale=10**places
    return D(lcm(int(a*scale),int(b*scale)))/D(scale)


def walk(levels, quantity:D):
    remaining=quantity; value=D(0)
    for price, available in levels:
        take=min(remaining,available); value+=take*price; remaining-=take
        if remaining<=0: return value
    return None


def quantity_for_budget(levels,budget:D):
    q=D(0)
    for p,available in levels:
        take=min(available,budget/p); q+=take; budget-=take*p
        if budget<=0: break
    return q


def economics(spot:Market,short:Market,a:Book,b:Book,settings:dict):
    budget=D(str(settings['trade_cad']))/D(str(settings['cad_per_usdt']))
    if sum((p*q for p,q in a.levels('asks')),D(0))<budget:return None,'insufficient_depth'
    step=common_step(spot.step,short.step)
    q=(quantity_for_budget(a.levels('asks'),budget)/step).to_integral_value(rounding=ROUND_DOWN)*step
    if q<=0 or q<max(spot.minimum,short.minimum): return None,'minimum_quantity'
    cost=walk(a.levels('asks'),q); proceeds=walk(b.levels('bids'),q)
    if cost is None or proceeds is None: return None,'insufficient_depth'
    if cost<spot.min_notional or proceeds<short.min_notional: return None,'minimum_notional'
    sf=D(str(settings['spot_fee_bps']))/10000; pf=D(str(settings['perp_fee_bps']))/10000
    entry_fees=cost*sf+proceeds*pf
    # Scenario exit: spot unchanged, perp bought at configured premium to spot.
    exit_gap=D(str(settings['exit_gap_bps']))/10000
    assumed_exit_spot=cost
    assumed_exit_perp=cost*(1+exit_gap)
    exit_fees=assumed_exit_spot*sf+assumed_exit_perp*pf
    buffer=cost*D(str(settings['execution_buffer_bps']))/10000
    holding=cost*D(str(settings['holding_cost_bps']))/10000
    net=proceeds-cost + assumed_exit_spot-assumed_exit_perp-entry_fees-exit_fees-buffer-holding
    return {k:float(v) for k,v in dict(quantity=q,buy_cost=cost,short_proceeds=proceeds,buy_vwap=cost/q,
        short_vwap=proceeds/q,entry_gap_bps=(proceeds/cost-1)*10000,entry_fees=entry_fees,
        exit_fees=exit_fees,execution_buffer=buffer,holding_allowance=holding,
        exit_basis_cost=assumed_exit_perp-assumed_exit_spot,net=net,actual_cad=cost*D(str(settings['cad_per_usdt']))).items()},None
