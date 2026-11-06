# Parallax — local arbitrage paper research

Bybit + Gate USDT spot/perpetual research on the Mac. Public market data only; no order endpoints or API secrets. The dashboard and simulator run locally.

## Start

Requires Python 3.12+ and Node 22.13+.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
npm --prefix dashboard ci
./scripts/run.sh
```

Open **http://localhost:3000**. The API listens on 127.0.0.1:8000. Stop with Ctrl-C; the launcher owns and shuts down both process groups. A data-directory lock rejects duplicate backends. No workers/reload, autostart or sleep-setting modifications. The laptop must remain awake to collect.

For an empty offline preview, use `PARALLAX_OFFLINE=1 PARALLAX_DATA=data/offline ./scripts/run.sh`. Offline mode does not replay historical markets.

## Current experiment

- CAD 50 spot notional plus matching short quantity; short collateral is additional.
- Minimum net: **CAD 0.005**, converted using the manual CAD/USDT scenario (1.38 by default).
- Conservative entry assumptions: spot fees 20 bps/leg, perp fees 6 bps/leg, execution allowance 40 bps, holding allowance 20 bps, residual exit basis 20 bps.
- All supported market symbols screened every five seconds, without a coin-count/volume filter. All economically qualifying screens enter a fair depth-confirmation queue. Depth requests are bounded; queued routes and missed temporal resolution remain visible.
- Automatic directional identity evidence uses Bybit's index constituents to link an exact Gate spot pair with multiplier 1. Missing/expired evidence stays unverified. Numeric-prefix instruments remain unresolved. Reverse routes are screened but not automatically approved by that evidence.
- Paper entries/exits wait at least 500 ms and require new books; actual confirmation delay is recorded. Independent IOC entry fills use 50% displayed depth, partial/unmatched fills, emergency unwind, all fees, execution/holding stress, one-hour timeout and CAD 2 stop trigger. Five pending/open positions maximum; this limits exposure, not screening coverage.
- Open positions, reserves and realized balances survive restarts. Stale or insufficient closing books keep exposure unresolved instead of fabricating profit.
- Network traffic is compressed, metered and guarded by a 256 KiB/s budget over 30 seconds. On overload, collection stops visibly. This is not an instantaneous router bandwidth cap.

The **Paper positions** view shows modeled P&L in CAD to four decimals, holding time, fill fraction, confirmation latency, costs and both venue links. **Coverage & health** shows screening, identity/depth coverage and network usage. **Live routes** distinguishes unverified ticker matches from identity-checked candidates.

## Interpretation

An opening gap is not a completed profitable trade. Entry screening assumes a future residual basis; paper closing uses subsequently observed spot bids/perpetual asks. A profit trigger can close at a loss after latency. The depth haircut is a deterministic stress assumption, not calibrated fill probability.

Funding uses a time/current-rate allowance, not actual settlement history. Fee rounding/token charges, exact liquidation, queue dynamics, exchange rejections and partial exit behavior are not fully modeled. Half-cent signs are smaller than plausible model error. Several clean days of observations are needed; no daily earnings forecast is implied.

See [the experiment specification](reports/PAPER_TRADING_V2.md) for execution, identity and limitation details, and [the original audit](reports/INITIAL_FINDINGS.md) for the previous CAD 20 recordings. The broader design history remains in `ARBITRAGE_RESEARCH_SPEC.md`.

## Data and reports

New experiment: `data/paper-v2/`. The first experiment in `data/` is preserved. SQLite events: 30 days; raw compressed responses: approximately 24 hours / 2 GiB. `paper-state.json` retains current exposure, lifetime realized balances and recent closes independently of event retention. Export evidence before retention removes it.

```sh
.venv/bin/python scripts/paper_report.py
.venv/bin/python scripts/analyze_recording.py # original CAD 20 run only
```

`reports/paper-results.json` reports retained simulated outcomes and unresolved exposure, separately from lifetime accounting. It does not extrapolate trades per day or count unverified gaps as profits.

API:

- `GET /api/state`, `/api/stream`: current routes, paper positions and health.
- `GET /api/detail?route=...`: depth, costs and route evidence.
- `GET /api/history?hours=24`: ended depth episodes.
- `GET /api/catalog`: markets, identities and exclusions.
- `POST /api/assumptions`: local research parameters, including `min_net_cad`. Changes expire pending entries/end active episodes; existing positions retain entry assumptions.

## Validation

```sh
.venv/bin/python -m pytest -q
npm --prefix dashboard run typecheck
npm --prefix dashboard run build
```

Tests exercise accounting, independent/partial fills, delayed loss after a profit trigger, stale data, restart persistence, identity mismatches/scaling, network budget/compression, lot rules and full-universe route discovery. They do not establish real trading profitability.
