# CAD 50 paper-trading experiment

The user authorized CAD 50 spot notional plus an equal-quantity perpetual short, with a minimum CAD 0.005 net profit per completed round trip. Short collateral is additional. No real orders, exchange credentials or money movements are involved.

## Admission and execution

Default settings preserve the report's more conservative assumptions: spot fees 20 bps per leg, perpetual fees 6 bps per leg, 40 bps extra execution allowance, 20 bps minimum holding allowance, and a 20 bps residual exit basis for entry screening. FX remains a manual 1.38 CAD/USDT scenario.

A CAD 0.005 threshold is approximately 0.00362319 USDT, not 0.005 USDT. Target arithmetic uses the configured CAD/USDT conversion. At CAD 50, the approximately 1.32% opening-gap deduction is about CAD 0.66; lowering the desired net to half a cent does not remove those costs. The entry formula also accounts for the slightly different short/exit fee notionals.

All supported routes receive quote screening every five seconds. Best bid/ask and full budget form an optimistic upper bound; routes that cannot cover the configured cost/target assumption do not need expensive depth checks. All routes that pass enter a fair oldest-checked queue, rather than a fixed coin sample. Depth confirmation requests both venues concurrently, publishes the pair atomically, and rejects slow/stale responses. Existing positions and pending orders receive four out of five scheduling turns; the fifth continues discovery. When no positions need monitoring, all turns confirm potential entries. Delays and queue counts are visible. This is full coin coverage with explicitly limited temporal/depth resolution, not a high-frequency feed.

A route can enter paper execution only after directional identity evidence passes. Bybit must identify the exact Gate spot pair as a positive-weight index component with multiplier 1 and a fresh index timestamp. Gate's currency metadata must permit trading and contain no invalid-address marker. Evidence expires after one hour and is revisited; unavailable/missing/non-1:1 evidence stays unverified. This establishes issuer-linked economic identity for research, not cross-chain deposit compatibility or account eligibility. Reverse routes (Bybit spot to Gate perpetual) are screened but are not automatically approved by this directional proof. Numeric-prefix instruments remain explicitly unresolved.

Sources: [Bybit index components](https://bybit-exchange.github.io/docs/v5/market/index-components), [Bybit tickers](https://bybit-exchange.github.io/docs/v5/market/tickers), [Bybit depth](https://bybit-exchange.github.io/docs/v5/market/orderbook), [Gate public API](https://www.gate.com/docs/developers/apiv4/en/).

Paper signals submit no orders. The simulator:

1. Freezes quantity, costs and price limits at signal time. Limits round VWAP to an exchange tick and allow one extra tick in the aggressive direction.
2. Waits at least 500 ms and requires new depth snapshots requested after that delay. Actual latency includes scheduling and network delay, and is recorded. Signals expire after 30 seconds without confirmation.
3. Applies a deterministic 50% haircut to displayed entry depth. Each IOC leg can fill independently, partially or not at all. It does not recheck profitability at fill time to cherry-pick favorable fills.
4. Reserves simulated spot cash/fees and twice the short notional as stress collateral, within the CAD 20,000 two-venue budget. Maximum concurrent pending/open positions is five, limiting outstanding exposure and monitoring load, not the screened coin universe.
5. If entry quantities differ, schedules an emergency unwind. If balanced, observes actual spot bids and perpetual asks for closing economics. Closing depth also uses the 50% haircut, with the additional execution-cost allowance retained.
6. Triggers a delayed close at the CAD 0.005 target, a CAD 2 modeled stop loss, or one-hour timeout. A target trigger can close at a loss after the delay. Closing requires sufficient fresh depth; missing data never fabricates an exit or clears exposure.
7. Deducts all four fees, execution buffer and holding allowance. The holding deduction is the maximum of a time-scaled allowance, an adverse-current-funding-rate stress, and the largest prior holding deduction. Favorable funding is not credited. This is not actual funding settlement accrual.

The haircut and latency assumptions are stress scenarios, not estimated fill probabilities. Exit fills assume sufficient displayed depth can be consumed after the delay; queue dynamics, subsequent partial exit fills and exchange-specific rejection behavior are not calibrated. No worst-case loss bound is claimed. Fee-token/rounding rules, exact funding history and liquidation mechanics remain further research work. Half-cent returns are below plausible model uncertainty; record them, but do not treat their sign as established real profitability.

## Persistence and observation integrity

New recordings use `data/paper-v2/`, preserving the first experiment in `data/`. Atomic `paper-state.json` snapshots retain open quantities, reserved collateral, realized balances and recent completed trades across restarts. Pending signals do not resume across downtime; they were never filled. Open positions wait for fresh books after restart. A removed market retains unresolved exposure. State is research accounting, not production exchange reconciliation.

Research events persist in SQLite, raw quote/depth responses in compressed JSONL. Retention remains 30 days of events and approximately 24 hours / 2 GiB of raw responses. No blanket reconstruction of the previous run at CAD 50 is attempted: its stored CAD 20 economics cannot simply be multiplied to represent larger depth fills.

Cached quotes no longer extend an episode's observed duration on each engine tick. Depth episodes count receipt observations; separate `screen_episode_*` events measure polled upper-bound signals. Five-second observations cannot establish uninterrupted sub-second spread availability. No remaining-lifetime or fill-probability estimates are invented.

## Network operation

The default feed uses compressed bulk HTTP quotes plus bounded depth and identity requests. The previous deep WebSocket collector is not started by the API. Requests are spaced globally, connections bounded, and compressed response bytes counted. A 30-second budget of 256 KiB/s stops collection on overload. It is a circuit breaker, not an instantaneous bandwidth cap, and excludes HTTP/TLS overhead. The initial local smoke test exercised the stop path; compressed follow-up requests operated below the budget. Actual current measurements appear in Coverage & health.

Run one backend. A data-directory lock prevents duplicate ownership. Collection is local and requires an awake laptop; no autostart, sleep-setting changes or external hosting were installed.

## Dashboard and report

The dashboard shows identity-checked candidates separately, all-symbol screening/depth coverage, measured exchange traffic, half-cent CAD precision, pending/open/closed paper results, holding times, matched fill fraction, actual confirmation delay, modeled costs, losses and both venue links.

Export current outcomes without exchange requests:

```sh
.venv/bin/python scripts/paper_report.py
```

The export distinguishes retained-event results, lifetime state totals and unresolved positions. Several clean days are still needed before evaluating frequency, convergence and profitability. The initial historic findings are unchanged, apart from the newly discovered need to avoid extending intervals using cached quotes; those earlier duration statistics should not be interpreted as continuously confirmed windows.
