# Initial recording findings — 19 September 2026

**Conclusion: price discrepancies exist in the recordings; a profitable, executable strategy has not been demonstrated. No verified paper round trips or real trades were recorded.** The right next step is better measurement, not committing the CAD 20,000 budget.

## Evidence

Read-only audit of `data/research.sqlite3`, reproduced with `.venv/bin/python scripts/analyze_recording.py`; machine-readable output: `reports/recording-audit.json`.

- Window: 10:57:33–13:35:32 Toronto time, approximately 158 minutes. Four run starts include overlapping collectors; this is not 158 minutes of clean, independent observations.
- Final catalog: 498 shared coin tickers, 757 cross-venue spot/perpetual routes on Bybit and Gate; 4,182 total discovered instruments. Catalog size is not usable feed coverage.
- Final snapshot: only 225 of 757 routes passed calculation checks (29.7%). This is one snapshot, not average uptime.
- 1,564 episode starts, 1,563 ends. One unmatched start. Episode IDs deduplicated, but overlapping economic signals across runs are not deduplicated.
- 300 ended below the scenario profit threshold; 1,263 (80.8%) ended on skew, invalid/stale books, or insufficient depth. These cannot establish when the spread actually disappeared.
- Median observed interval: 4.58 seconds overall. For the 300 threshold-ending episodes, median 0.56 seconds, maximum 25.25 seconds. Starts can be left-censored; these are observation intervals, not guaranteed execution windows or holding times.
- No identity overrides, paper entries, or paper closes. Consequently there is no measured win rate, fill probability, holding-time distribution, or realized profit.

## Signals worth investigating

These are unverified ticker matches, not a vetted trading list. Reported profit is the median first-observation estimate under the original approximately 0.82% cost allowance and assumed complete convergence, converted at the manual 1.38 CAD/USDT scenario. Actual order sizes can round below CAD 20. We do not sum these figures or select hindsight peaks.

| Ticker | Ended episodes | Median opening gap | Median conditional net, CAD | Median observed interval |
|---|---:|---:|---:|---:|
| G | 99 | 1.29% | $0.091 | 2.69 s |
| BANK | 60 | 1.20% | $0.075 | 0.32 s |
| BR | 54 | 1.38% | $0.087 | 2.76 s |
| ZAMA | 38 | 1.21% | $0.078 | 1.23 s |
| B2 | 28 | 1.24% | $0.082 | 1.42 s |
| ARX | 21 | 1.27% | $0.082 | 0.83 s |

The huge EDGE, ON, AMC and BNC estimates are unusable without identity and product normalization checks. For example, one EDGE observation bought at about 0.083 USDT and shorted at about 0.597 USDT. Matching tickers alone cannot establish equivalent exposure. These could be different assets/products or normalization errors; the audit has not established which.

The smaller signals above are interesting enough to investigate, but their typical 1.2–1.4% opening gaps leave little margin under the more conservative scenario below.

## Conservative CAD 20 mock trades

Interpret CAD 20 as spot purchase notional plus a matching short quantity, with additional short collateral. It is not CAD 20 of total capital tied up. Calculations below are illustrative approximations, not measured returns or exchange fee quotes.

Budget, as a percentage of the CAD 20 spot notional:

- Spot buy and sell fees: 0.40% total (0.20% each).
- Perpetual open and close fees: approximately 0.12% total (0.06% each).
- Extra execution slippage/latency across the round trip: 0.40% total.
- Funding/holding allowance: 0.20% total; actual funding can exceed it.
- Residual exit basis: 0.20%; we do not assume perfect convergence.

Total deduction from opening gap: approximately **1.32%, or CAD 0.264**. Residual exit basis is foregone convergence, not a trading fee. The other allowances total 1.12%. Fees actually depend on each fill's notional; this table approximates similar opening/closing spot levels. It assumes all four legs fill and the position closes at the assumed residual basis. It is more cautious than our initial settings, but not a worst-case bound.

| Opening executable gap | Gross potential at full convergence | Mock net after deductions |
|---|---:|---:|
| 1.00% | $0.20 | -$0.064 |
| 1.25% | $0.25 | -$0.014 |
| 1.50% | $0.30 | $0.036 |
| 2.00% | $0.40 | $0.136 |
| 3.00% | $0.60 | $0.336 |

A roughly 1.82% opening gap is needed to target CAD 0.10 under these assumptions. This is only an admission threshold: profit remains dependent on subsequent closing fills. For a spot long and equal-quantity perpetual short:

`net = quantity × [(short entry − spot entry) − (short exit − spot exit)] − four fees − net funding − other costs`

Use actual executable fill prices in this formula; do not subtract slippage twice if already reflected in those prices. Trading and funding costs belong in realized P&L; see [Bybit's P&L documentation](https://www.bybit.com/en/help-center/article/Profit-Loss-calculations-USDT-Contract).

At the 2% opening-gap scenario, 10 / 50 / 100 successful round trips would yield approximately **CAD 1.36 / 6.80 / 13.60** before failed hedges, infrastructure, rebalancing/FX costs and taxes. These are counts of completed trades, not daily forecasts. The data cannot tell us whether even ten qualifying fills per day are available.

One additional CAD 1 emergency-unwind loss wipes out about 7.4 successes at CAD 0.136. Failure frequencies and loss sizes are unmeasured; assigning an invented probability would create false confidence. If the basis widens or does not converge, losses and funding can exceed the allowances. More available capital does not create more qualifying trades.

## Internet impact and next implementation steps

Earlier collectors overlapped, and one run counted approximately 27.8 million book updates. Raw compressed retention reached about 2 GiB, but this is not a network-bandwidth measurement. Deep all-market subscriptions plus repeated reconnects are plausible contributors to the household slowdown; router bandwidth and latency were not measured, so causation is not proven.

No collectors were running during this audit. A process lock now prevents two backends sharing the same data directory. It does not prevent intentionally separate data directories or cap bandwidth. Live scanning has not been restarted.

Next work, in order:

1. Add receive-byte/rate and reconnect telemetry, then a configurable network budget that stops collection visibly on overload. Sleeping while messages accumulate would produce stale books.
2. Preserve all supported coins using lightweight whole-universe feeds; request deeper books only for potential routes. Clearly distinguish screening signals from depth-qualified signals and record depth-confirmation latency. No fixed coin sample. Lower update frequency can miss brief windows and must be labeled.
3. Verify underlying identities and contract units per route. Keep unresolved symbols visible in a separate research category with no paper execution.
4. Capture continuous, simultaneous books and realistic exit quotes. Simulate delayed entries, partial fills and emergency hedges; calibrate fill probabilities only with evidence.
5. Collect several clean days, then report independent executable entries, actual simulated closes, holding times, capital usage and P&L after costs. Apply the stronger cost scenario alongside the original settings, preserving both results.

For immediate relief, stop the collector; a router per-device bandwidth cap or queue management can also help if supported. Moving the same feed workload to a Raspberry Pi on the same connection will not reduce internet traffic.
