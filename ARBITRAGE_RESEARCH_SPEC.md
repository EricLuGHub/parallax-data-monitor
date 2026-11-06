> Current implementation update (19 September 2026): CAD 50 spot notional, CAD 0.005 net target, public-data paper execution. The authoritative current experiment is [PAPER_TRADING_V2.md](reports/PAPER_TRADING_V2.md). Earlier CAD 20 / WebSocket / optimistic-fill sections below describe design history and are superseded where they conflict.

# Altcoin arbitrage research system

Date: 2026-09-17. Status: proposed specification; no collectors, backtests, or live trading have been run.

## 1. Objective and research question

Measure how often an altcoin can be bought spot on one venue and shorted on another for positive estimated net profit at small sizes, including the costs and feasibility of closing or settling both legs. Report executable size, duration, latency sensitivity, required capital, and inventory sustainability. A price discrepancy is a hypothesis, not evidence of a fill.

The initial product is a market-data recorder, opportunity detector, replay simulator, and research report. Live orders and withdrawals are a subsequent project decision. The workspace currently has no application to preserve.

Confirmed user constraints and working assumptions:

- User operates from Montréal, Québec, with approximately $20 per trade and $20,000 total capital. Currency is not specified: provisionally use CAD for both, with configurable USD scenarios. Treat $20 as buy-leg notional with a matched sell leg, not $20 combined turnover.
- Prioritize spot buys paired with eligible borrowed-coin or perpetual shorts; collateral, borrowing, and liquidation constraints must be modeled. Start with account-eligible CAD, USD, and USDC markets; prioritize same-quote comparisons and explicitly price conversion for other routes. USDT markets may be observed but are not the default executable universe.
- Primary simulated buy notional: CAD 20 equivalent; sensitivity sizes: CAD 10, 15, 25, and 50. Convert using contemporaneous executable FX/crypto routes and include their costs.
- Compare total capital scenarios of CAD 2,000, 5,000, 10,000, and 20,000. The full budget is a ceiling, not an instruction to deposit or deploy it. Include reserves, fees, and funding costs within that ceiling.
- Model low-volume assets broadly, including a very-low-volume bucket. Group using observed depth and trades as well as exchange-reported volume.
- Currency denomination, exchange/account eligibility, existing accounts, and desired minimum net profit remain open. Research visibility and trading eligibility are separate fields.
- Public data first. Optional read-only credentials improve account-specific fee and funding-status accuracy.

## 2. Exchange universe and integration order

### Québec execution priority (supersedes the global ordering below)

Audit **Kraken, Coinbase Advanced Trade, and NDAX first**; evaluate **Crypto.com Exchange** next, conditional on confirming that the actual Exchange/API product is available to the Québec account. The AMF lists Kraken, Coinbase, NDAX, and Crypto.com as registered platforms, but registration does not establish access to every product, API, or token. [AMF register, checked 2026-09-17](https://lautorite.qc.ca/en/general-public/registers/cryptoasset-trading-platforms). [NDAX API documentation](https://apidoc.ndax.io/) documents trading and WebSocket access.

Kraken explicitly restricts USDT and many other assets for Canadian accounts, and prohibits Canadian margin and derivatives trading. Load the current regional asset eligibility before selecting markets. [Kraken regional restrictions](https://support.kraken.com/articles/where-is-kraken-licensed-or-regulated).

The global venues below remain comparison/research candidates where public-data access is permitted. Do not include a route in the user's feasible portfolio unless both venue accounts, products, assets, and funding routes have been verified as available. Do not infer access from a working public endpoint. Start with two Québec execution candidates, expand to three/four after overlap validation, and add global reference feeds only where they help the research question.

The AMF also lists Coinsquare, Netcoins, Newton, Shakepay, Wealthsimple, and Fidelity Digital Assets. Audit them only if shared altcoins and an accessible trading/depth API justify it; registration alone does not make a platform suitable for this system.

### Global discovery candidates

This is a prioritized candidate universe, not a claim to cover every exchange or an endorsement of venue solvency. Selection priorities are research judgments to validate against live market overlap, API coverage, and usable depth. Linked documentation establishes integration surfaces, not eligibility or fill quality.

| Priority | Venues and official references | Research role |
| --- | --- | --- |
| Global reference group | [Gate](https://www.gate.com/docs/developers/apiv4/en/), [MEXC](https://www.mexc.com/api-docs/spot-v3/introduction), [KuCoin](https://www.kucoin.com/docs-new), [Bitget](https://www.bitget.com/docs/uta/Introduction), [Binance](https://developers.binance.com/en/docs/introduction), [OKX](https://www.okx.com/docs-v5/en/) | Test long-tail overlap while including comparison venues; use only eligible markets for executable simulations. |
| Global expansion group | [Bybit](https://bybit-exchange.github.io/docs/v5/intro), [HTX](https://huobiapi.github.io/docs/spot/v1/en/), [CoinEx](https://docs.coinex.com/api/v2/authorization), [BitMart](https://developer-pro.bitmart.com/en/spot/) | Expand overlapping altcoin routes after initial data-quality validation. |
| Additional candidates | [LBank](https://www.lbank.com/docs/), [AscendEX](https://ascendex.github.io/ascendex-pro-api/), [Poloniex](https://api-docs.poloniex.com/spot), [Bitfinex](https://docs.bitfinex.com/docs/introduction), [Backpack](https://docs.backpack.exchange/) | Add when incremental shared listings justify collection and maintenance. |
| Comparison and accessible execution candidates | [Kraken](https://docs.kraken.com/), [Coinbase](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/sdk), [Crypto.com Exchange](https://exchange-docs.crypto.com/exchange/v1/rest-ws/index.html), [Bitstamp](https://www.bitstamp.net/api/), [Gemini](https://developer.gemini.com/) | Include shared assets, alternative quotes, and account-accessible routes; jurisdiction can move these to phase one. |
| Regional and further discovery | [Upbit](https://global-docs.upbit.com/); Bithumb and BingX pending a deeper current API/access audit | Regional pricing and additional overlap. Fiat conversion and account restrictions can prevent closing a cycle. Upbit regional products must be treated separately. |
| Later on-chain expansion | [Hyperliquid](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api), [Uniswap](https://developers.uniswap.org/docs), [Raydium](https://docs.raydium.io/); PancakeSwap pending integration audit | Spot CEX–DEX or DEX–DEX comparisons using amount-specific executable quotes and exact asset identities. Perpetuals are a separate strategy. |

[Jupiter](https://developers.jup.ag/) is an aggregation source for Solana routes, not an independent exchange to double-count alongside the same underlying pools. Other aggregators can be evaluated later.

Including NDAX, there are 22 named CEX candidates with documentation reviewed, two additional CEX audit candidates, and four later on-chain venues, plus the Canadian platform audit list above. This is deliberately broader than the initial ten. Integrating all simultaneously is not the first milestone.

For every exchange, maintain a capability record: API product/version, account region, spot symbols actually available by API, L2 depth coverage, sequence/checksum support, subscription limits, fee source, funding-status source, precision and minimums, private-order support, and last verification timestamp. A website listing alone is insufficient.

Promotion score: additional verified shared assets, usable depth at target size, eligible routes, feed reliability, duration of conservative opportunities, and adapter effort. Discovery scans the wider universe daily; continuous depth recording targets every supported verified spot/short route across selected venues. No sampled coin subset or liquidity-based inclusion filter is permitted. Regional account eligibility is separately labeled; the current research audits global venue capabilities.

## 3. Strategies to test

### Primary strategy: broad spot-buy and short discovery

Keep cash and accepted collateral across approximately 5–10 eligible exchanges; do not pre-own every altcoin. Start with five only if eligibility and shorting coverage justify them, and expand based on incremental tradable asset coverage. Equal capital splits are simulation baselines, not deposit instructions. For CAD 20,000, those baselines are CAD 4,000 across five or CAD 2,000 across ten, with reserves and margin buffers included. Québec shorting eligibility remains a feasibility gate; do not assume the spot shortlist offers shorts.

Discover the widest practical universe of verified spot-plus-short routes. Inventory of altcoins is acquired selectively after a signal. Pre-existing accepted collateral and quote balances are still required. Verify borrow availability and rate for a spot short, or the exact matching perpetual contract and contract multiplier for a derivatives short. Match underlying exposure rather than equal dollar notionals.

- **Borrowed-coin short:** buy spot on A and borrow-and-sell the actual coin on B. Transfer purchased coins later to repay borrowing when a verified compatible repayment route exists. Successful matched opening fills can capture the price difference without waiting for convergence, but borrow interest, transfer delays, fee-adjusted repayment quantity, collateral requirements, and failures affect the result.
- **Spot plus perpetual:** buy spot and short the matching perpetual. Model eventual sale of spot and repurchase of the perpetual, including four trading fills, funding cash flows, basis changes, and liquidation constraints. The opening basis is not realized profit. Evaluate specified exit-basis targets, holding horizons, and timeouts; estimate exit outcomes on chronological holdout data.

Prefunded spot below remains an optional strategy for selected assets with demonstrated recurring opportunities. Broad discovery should not assume that all listed coins have a short instrument, that a perpetual bid equals the other venue's spot bid, or that a public market is available to the user's account.

### A. Prefunded spot arbitrage — secondary, selected-asset experiment

Hold quote currency on A and the altcoin on B. Buy on A while selling the same net quantity on B. This avoids waiting for a transfer between the two trade legs, but execution is not atomic. Either leg can partially fill or fail.

Each simulated trade moves inventory between venues. Repeated one-way spreads eventually consume B's altcoin and A's quote. Model reverse opportunities, transfers, and conversion routes to restore balances. Track initial altcoin exposure and mark-to-market separately from spread capture; owning volatile inventory is economically consequential even when each matched trade is profitable.

### B. Buy, transfer, then sell — separate experiment

Check source withdrawal and destination deposit status on the same supported network, fees, minimums, confirmations, and operational delays. Sell against the order book observed after the modeled credit time, not the original bid. Until actual transfer timings exist, use explicitly labeled sensitivity scenarios, such as 1, 5, 15, and 60 minutes. These are assumptions, not measured service times.

This is price exposure during settlement, not a locked-in spread. Exclude blocked or unknown funding routes from actionable results while retaining them as explanations for apparent discrepancies.

### C. Later experiments

- Triangular spot arbitrage within one exchange: three fees, per-leg depth, rounding, and sequential execution risk.
- Maker/taker strategies: queue position and adverse selection require a different fill model; do not assume every touched limit order fills.
- CEX–DEX: amount-specific quotes, pool fees, gas/priority fees, token transfer taxes, block timing, MEV, transaction failure, and route overlap.
- Additional derivatives strategies beyond the primary spot–perpetual module remain later work. A perpetual price is never substituted for a spot sell price.

## 4. Asset identity and discovery

Never match symbols alone. Store canonical economic asset identity plus chain ID and contract/mint address where applicable, decimals, migration history, exchange-specific ticker, and supported deposit/withdrawal networks. Native assets use explicit native identifiers. Wrapped and bridged representations require verified redemption paths and costs; do not silently merge them.

Each mapping has evidence, source, timestamp, confidence, and optional manual review. Unresolved identity is observable but ineligible. Exclude leveraged tokens, derivatives, IOUs, and redenominations unless separately modeled.

Discover spot markets and rules via REST, intersect verified identities, then subscribe to depth. Use exact same quotes first. Later compare quotes only through an executable conversion path including depth and fees; account for stablecoin differences and fiat FX.

Liquidity cohorts should include observed two-sided depth within 10/50/100 basis points, trades per hour, time since last trade, top-of-book persistence, and reported daily volume. A quiet valid book is not automatically stale; heartbeat/sequence health and periodic reconciliation establish validity.

## 5. Profit and sizing engine

For a fee-consistent sellable base quantity q:

    estimated_net(q) = sell_proceeds_B(q) - buy_cost_A(q)
                       - trading_fees - incremental_quote_conversion_cost
                       - allocated_rebalance_cost - execution_uncertainty_buffer

Buy cost walks the asks and sell proceeds walk the bids, so observed depth impact is already included. Do not subtract the same slippage twice. Adjust purchased quantity when a fee is charged in base; value third-token fees explicitly. Report modeled buffers separately from expenses actually incurred.

Optimize q over depth breakpoints and configured size caps, after tick/step rounding, order minimums, maximums, fee currency, balances, and risk limits. Report both highest estimated dollar profit and results at each fixed size. Missing fee or funding data is unknown, never zero.

Produce four labels: raw discrepancy; depth-and-fee positive; latency-stressed candidate; inventory-feasible simulated cycle. Only measured fills can establish realized trading profit.

Example, entirely hypothetical and denominated in CAD: buy cost 20.00, sell proceeds 20.20 (1% gross spread), assumed taker fees of 0.20% on each leg cost 0.0804, leaving 0.1196 before rebalancing and execution uncertainty. These are illustrative fees, not verified account rates. A CAD 1 transfer cost is 5% of a CAD 20 buy notional.

Prefer prefunded inventory and batched restoration for this experiment. Track how many actual successful cycles share each batch cost; never assume enough future trades to amortize it. Compare CAD 0.05, 0.10, 0.25, and 0.50 net-profit thresholds. Report throughput required to cover measured monthly operating cost: cost divided by net profit per completed cycle. A CAD 50 monthly cost at CAD 0.10 net per cycle requires 500 cycles merely to cover that expense. The system must not multiply small-trade capacity by the budget without depth, inventory, and time constraints.

Use conservative taker fees initially. Fee schedules are time-versioned and account-specific when available. CCXT exposes fee and network methods, but coverage is incomplete; validate underlying fields and avoid treating static defaults as account truth. [CCXT fee and network documentation](https://github.com/ccxt/ccxt/wiki/Manual).

Do not charge a full withdrawal fee on every prefunded trade and then charge it again in the portfolio simulator. The detector can show an allocation estimate; the simulator replaces it with explicit costs for actual modeled rebalances and terminal restoration.

## 6. Event collection and book validity

- REST for discovery, rules, fees, funding status, snapshots, and reconciliation; WebSockets for depth and trades.
- Follow each venue's snapshot-plus-delta protocol. Validate continuity, checksums where supplied, deletions, and ordering. Invalidate on gaps and resnapshot before emitting another candidate.
- Retain exchange timestamps, local UTC receipt time, monotonic receipt time, sequence identifiers, payload schema version, connection ID, and processing lag. Track clock synchronization. Never assume exchange clocks are mutually accurate.
- Bound cross-venue observation skew and feed-health age. Sweep freshness thresholds instead of selecting one arbitrary universal cutoff.
- Heartbeats, reconnect backoff with jitter, connection sharding, and token-bucket rate limits belong in adapters. Queue overflow marks a recording gap and invalidates affected books.
- Separate API status freshness from actual book-update frequency; preserve a valid unchanging illiquid book while confirming connection health and reconciling periodically.
- Store raw messages plus periodic snapshots and normalized events so a result can be reconstructed. Measure actual storage volume before broadening subscriptions.

## 7. Opportunity episodes and empirical metrics

An episode is keyed by asset, directed venue pair, quote route, and strategy. Start when a configured conservative threshold is crossed; close when it ceases to qualify. Use documented hysteresis to avoid flicker. A thousand messages during one gap are not a thousand independent trades. Keep the raw timeline so episode rules can be changed later.

Report:

- Unique episodes per observed pair-hour, per day, per asset, and per route; data coverage and outages alongside every denominator.
- Duration distribution and fraction surviving 100/250/500 milliseconds, 1/2/5 seconds, and longer manual-response delays.
- Profit/size curves, maximum supported size, and profit thresholds such as CAD 0.05, 0.10, 0.25, and 0.50 after currency conversion.
- Rejection breakdown: identity, stale/inconsistent book, fees, depth, minimums, funding status, account eligibility, inventory, or conversion.
- Shared liquidity and capital conflicts between candidates; no summing overlapping opportunities as independently executable profits.
- Portfolio P&L, turnover, capital utilization, venue balances, inventory exposure, peak-to-trough drawdown, recovery losses, and restoration costs.
- Opportunity concentration by asset/day/venue, and out-of-sample persistence.

## 8. Replay and portfolio simulator

Replay in local receipt order. A decision can only use data available then; advance each leg to its modeled submission/arrival time. Use separate leg latency and failure scenarios, not a single perfectly synchronized fill. A later displayed book can support an estimate, but does not prove an order would have filled.

Run an optimistic displayed-depth bound and conservative scenarios with reduced available depth, disappearing quotes, partial fills, rejections, and cancellation/recovery latency. Do not describe depth haircuts as calibrated fill probabilities without live evidence.

Reserve balances and available depth across competing simulated orders. Maintain per-venue inventories, pending transfers, fee tokens, quote assets, and minimum trade sizes. Retire simulated consumed liquidity conservatively rather than repeatedly filling on unchanged historical depth. Historical replay cannot perfectly reconstruct the market impact of our own orders; label this limitation.

Use the CAD 2,000/5,000/10,000/20,000 seeded capital scenarios (currency assumption pending confirmation). Never assume inventory in every small coin for free. Mark inventory to conservative liquidation values and report spread-capture P&L separately from inventory price changes. Finish with explicit inventory restoration or mark residual holdings and trapped funds, including exit costs. Deduct infrastructure expense at portfolio-report level.

Evaluate on chronological holdout days with strategy parameters frozen before the holdout. Record delisted and suspended assets rather than silently dropping them. Report day-block uncertainty ranges and coverage; a short study cannot establish year-round profitability.

## 9. Architecture and technology choices

Proposed modular Python service, with collector workers isolated per venue when needed:

    REST discovery/status + WebSocket adapters
        -> identity registry + validated in-memory order books
        -> size/fee/route engine -> episode tracker
        -> live research tables and alerts

    raw events + snapshots -> replay -> capital-constrained simulator -> reports

Use the same pure calculation functions in live detection and replay to prevent inconsistent definitions.

| Layer | Proposed choice | Purpose |
| --- | --- | --- |
| Runtime | Python, asyncio, uv-managed locked dependencies | Fast iteration, concurrent feeds, research ecosystem |
| Exchange abstraction | CCXT / CCXT Pro where tested; native adapters where necessary | Discovery and streaming, with explicit feature checks |
| Precision and models | Decimal or integer price/quantity units; Pydantic at boundaries | Correct fee math, rounding, and validated metadata |
| Historical storage | Compressed Parquet via PyArrow | Append-oriented normalized events and snapshots |
| Query and analysis | DuckDB and Polars | Local research and replay without an initial database cluster |
| Metadata | SQLite initially | Versioned assets, markets, fees, configuration, and runs |
| Initial interface | CLI + generated HTML charts and CSV reports | Review findings before building a separate web product |
| Later interface | FastAPI backend; optional web dashboard | Live filtering and episode drill-down if needed |
| Operations | Structured logs, health metrics, Docker Compose on one Linux host | Repeatable collection and outage visibility |
| Verification | pytest, property-based tests, recorded protocol fixtures | Book correctness, accounting invariants, deterministic replay |

These are architectural choices, not claims about required package versions. Pin supported versions during implementation and test the exact adapters. CCXT support is not uniform across all endpoint types or products. [CCXT](https://github.com/ccxt/ccxt), [WebSocket coverage](https://github.com/ccxt/ccxt/wiki/ccxt.pro.manual).

No Kafka, Kubernetes, or distributed matching system in the MVP. Profile first; move storage to object storage/ClickHouse or hot calculations to another runtime only if measured load requires it. Initial hosting hypothesis: 4 vCPU and 8–16 GB RAM; measure 24-hour CPU, network, and storage use before selecting a paid host or retention budget.

Suggested modules: adapters/, registry/, books/, economics/, detector/, recorder/, replay/, portfolio/, reports/, tests/fixtures/. Data records include Asset, VenueAsset, Market, FeeSchedule, FundingRoute, BookEvent, OpportunityEpisode, SimulatedOrder, Fill, Transfer, and PortfolioSnapshot. Every result stores config hash, code version, data references, and reason codes.

## 10. Delivery plan and acceptance gates

1. **Discovery and feasibility:** audit Kraken, Coinbase, NDAX, and conditional Crypto.com Exchange access, retrieve market catalogs, verify shared identities, map API capabilities, and quantify overlap. Deliver a coverage matrix and a complete catalog of supported shared routes, with every excluded or unmonitored instrument and its reason recorded. If eligible overlap is poor, change venues before building more adapters.
2. **Collector pilot:** start with two venues, prove book reconstruction and replay, then grow to the three/four eligible venues and selected reference feeds. Complete a 24–48-hour soak test, including forced disconnects and gaps. Every invalid interval must be visible and excluded from actionable metrics.
3. **Economic detector:** implement depth walking, fees, minimums, quantity normalization, funding eligibility, and episodes. Golden examples and property tests must verify conservation, no extra profit from worse prices or higher fees, and correct rounding/partial depth behavior.
4. **Observation study:** gather at least 14 days, preferably 30, with continuous depth coverage and daily quality reports. Include quiet periods and weekends. Report only the population actually observed; unrecorded markets and feed gaps are unknown.
5. **Replay and portfolio study:** compare latency, fees, depth haircuts, capital allocations, and restoration methods on chronological holdout data. Deliver candidate route rankings, rejected-spread explanations, capacity estimates, and a reproducible go/no-go report.
6. **Optional execution validation:** if evidence warrants and the user requests it, add small capped two-leg execution using marketable limits and IOC where supported. Paper estimates alone do not establish profitability. Require idempotent client IDs, fill reconciliation, bounded residual exposure, recovery procedures, inventory caps, and a kill switch before this stage. Withdrawal automation is a separate explicit feature.

Proceed beyond research only if positive results persist out of sample under realistic fees, latency, and inventory limits, across multiple days, and exceed infrastructure and restoration costs. Stop or redesign if apparent edges primarily come from inaccessible accounts, suspended transfers, stale books, or tiny untradeable amounts. Finding no viable edge is a successful answer to the research question.

## 11. Initial dashboard/report specification

Each row shows asset identity, buy/sell venue, quote, buy/sell VWAP, quantity, gross spread, trading fees, estimated rebalance, buffer, modeled net profit, feasible size, episode age, book validity, observation skew, funding route, inventory availability, and eligibility status.

Drill-down shows both depth curves, episode timeline, raw-event references, fee provenance, rejected quantities, and delayed replay outcomes. Summary views show opportunities by liquidity bucket, size, venue pair, latency, and day, alongside recording coverage. Unknown inputs stay visible. Reports distinguish displayed opportunities, simulated realizations, and eventual measured fills.

## 12. Decisions to resolve before implementation

Confirmed: Montréal, Québec; approximately $20 per trade; approximately $20,000 total budget. Remaining: CAD versus USD denomination; account/product eligibility; desired minimum net profit; spot-only versus later DEX interest; hosting region and operating budget; existing exchange accounts and fee tiers. None prevents drafting or public-data feasibility work, but they change which opportunities could actually be acted on.


## 13. Venue links and live dashboard

Build a read-only React/TypeScript dashboard backed by Python/FastAPI with summarized streaming updates. Market recording must continue independently of the browser. Views: live candidates, candidate drill-down, research results, and account/feed health. Provide filtering, sorting, and freeze/pause of displayed rows without pausing collection.

Each candidate has **Open buy market** and **Open short market** links to the exact venue product, underlying, and quote. Clearly distinguish spot, margin spot, and perpetual markets and regional sites. Store verified URL templates in each adapter; validate mappings, escape symbols correctly, use allowlisted official hosts, and exclude credentials from links. If no reliable deep link exists, use a labeled official market-search fallback. Open links in new tabs. Display instrument names beside links so users can check the destination. Exchange UI last prices may differ from our executable bid/ask observations; show API source, observation timestamp, and age explicitly.

Candidate columns: coin, buy/short venue and product, notional, matched underlying quantity, depth-based prices, gross entry gap, opening/closing or settlement costs, conditional net profit, exit assumption, duration, feed health, account eligibility, and short availability. Distinguish estimated, simulated, and realized values.

Drill-down includes depth curves, spread timeline, profit-versus-size, exit/settlement plan, cost provenance, and execution risk controls. Show modeled probability of both legs filling, residual-exposure risk, expected recovery cost, and model confidence only when adequately supported. Otherwise show scenario results and 'uncalibrated / insufficient data'. Add a 'why not tradable' panel. Health shows cash, accepted collateral, margin headroom, borrow status, positions, recording gaps, and latency.

## 14. Joint fill risk and adaptive price limits

### Quantities, events, and horizon

For chosen size q, price limits, order types, and execution horizon H, estimate the joint distribution of buy filled quantity Qb and short filled quantity Qs, expressed in equivalent underlying units. Include base-currency fees and contract multipliers in exposure calculations. Define residual exposure as Qb - Qs, with an explicit small tolerance for valid rounding; track its amount and duration, not only whether an order has a fill.

For the simplified full-fill binary case, let pb = P(buy fills), ps = P(short fills), and pbs = P(both fill). Then P(exactly one fills) = pb + ps - 2*pbs. Do not substitute pb*ps for pbs: both fills can be dependent through common price moves, liquidity withdrawal, and exchange latency. Full/partial/no-fill combinations require the richer quantity distribution.

### Features and data

Use executable depth inside proposed limits relative to order quantity, book imbalance, spread in basis points, tick size, recent aggressive trade flow, order-book depletion and replenishment, price changes over short horizons, volatility over multiple horizons, feed age, observation skew, submission/acknowledgment latency distributions, exchange rejects, and borrow/collateral availability. Daily volume is a coarse discovery feature, not a sufficient fill predictor. Separate trade prints from book cancellations where the feed allows it; do not infer exact queue priority from aggregate L2 data.

Record these features at decision time plus intended limits, order type, send/ack/fill/cancel timestamps, actual partial fills, and recovery actions when execution is implemented. Public data replay provides counterfactual estimates, not true fill labels. Paper results and live labels must be kept distinct.

### Modeling progression

1. Start with replay-based latency/depth stress scenarios and empirical liquidity-survival measurements. Sweep per-leg latency, displayed-depth reductions, and limit offsets; show bounds and assumptions rather than invented probabilities.
2. With adequate actual order outcomes, fit a simple calibrated joint outcome model, starting with regularized multinomial regression for outcome categories and a residual-size model. Compare a tree-based model only if holdout results improve. Passive-order fill models require queue and adverse-selection assumptions distinct from taker models.
3. Evaluate by chronological splits, grouped by episode/day, using calibration curves, Brier/log loss, confidence intervals, residual exposure, and recovery loss. Prevent leakage from later fills, prices, or revised metadata. For sparse coins, pool by venue/product and liquidity cohort with explicit uncertainty; do not claim a calibrated coin-specific probability from a handful of observations.
4. Monitor drift and policy-selection bias: outcomes from conservative orders do not directly identify fill odds for untried aggressive policies. Abstain or revert to stress bounds when outside observed support. Never place real orders solely to gather labels without an explicitly authorized execution phase.

### Price aggressiveness

A conservative **execution** policy can permit a slightly worse price while keeping a strict maximum cost:

    buy_limit = current_best_ask + kb * buy_tick_size
    short_sell_limit = current_best_bid - ks * short_tick_size

kb and ks are nonnegative independently selected integers; prices must follow exchange tick rules. Buying below the ask or selling above the bid is more price-conservative but usually less immediately executable. For trades needing multiple levels, calculate whether the complete quantity fits inside each limit. One tick may be large as a percentage of a small coin's price, so constrain both ticks and basis points.

Compare offset candidates (initially 0, 1, 2, and 3 ticks, within configured bps caps) at the chosen size. A more permissive limit does not force a worse fill: it allows execution at that price or better. Recompute remaining profit and exit assumptions at adverse allowed prices. Skip if the remaining economic margin or residual-risk limit fails. The two legs need not use equal offsets.

Use marketable limit orders and IOC where supported to bound price and cancel unfilled remainders. FOK can avoid a partial fill on one venue but cannot make two different venues atomic. Verify each adapter's order semantics and account support. [Example of documented IOC/FOK/limit semantics: Kraken](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/add_order). Documentation of an order type is not evidence that Québec clients may use it for a short.

### Decision objective and recovery

Evaluate complete outcome scenarios:

    expected_net = sum_s P(s | current_state, execution_policy)
                           * net_PnL(s, exit_or_settlement_policy, recovery_policy)

Outcomes include both fills, partial mismatches, one-sided fills, neither fill, and timeouts/rejections. Net P&L includes entry and exit/settlement fees, funding/borrow costs, conversion, recovery, and remaining inventory valuation without double-counting. For perpetual routes, even the both-filled outcome must integrate the exit-basis distribution and holding costs; it is not the entry spread alone.

Select size and price limits to maximize conservative expected net subject to hard bounds on slippage, collateral use, residual exposure, and loss scenarios. Display both expected loss and tail recovery loss; positive average expectancy alone is insufficient. Use an uncertainty-adjusted estimate when model confidence is limited.

Predefine recovery: reconcile actual fills and outstanding orders, cancel remaining orders, then hedge only the verified residual quantity or unwind it using bounded price limits and a timeout. Handle late fills and unknown order state before retrying to avoid duplicate exposure. Include alternative-venue eligibility, order minimums, and quantities too small to hedge; record residual dust. Bounded orders can still fail, so a configured loss budget is not a guaranteed maximum realized loss. Surface unresolved exposure and stop new entries when limits are breached.

### Acceptance checks

Verify exact product deep links and fallbacks; tick rounding and bps caps; joint-probability arithmetic; partial-fill exposure with fee currency and contract sizes; no probability claims without calibration evidence; no duplicate recovery on timeout/late fill; and declining profitability as permitted adverse execution costs rise. Every displayed probability or scenario must retain model/config version, feature timestamp, horizon, sample coverage, and confidence provenance.


## 15. Live scanning and opportunity duration

Live scanning begins as soon as the initial adapters and validity checks work; historical collection runs alongside it. Do not wait for 14–30 days of observations before showing candidates. Earlier data improves evaluation and model calibration, but initial live candidates use explicit fee/exit assumptions and uncalibrated stress scenarios. Public historical candles cannot reconstruct historical executable order books; label available backfills by data type and start reliable episode measurement from recorded live depth.

### Opportunity lifetime versus position holding time

Expose two separate clocks:

- **Opportunity duration:** how long a directed spot-buy/short route continuously meets the configured qualification rules at a fixed target size (primary CAD 20 equivalent). Show 'active for' while open, and observed total duration when it closes.
- **Position holding time:** for paper positions initially, time from first entry fill until both legs are closed or borrowing is settled. Also show matched-entry time and unhedged exposure time. This clock can continue after the entry opportunity disappears. No actual position exists merely because a candidate is displayed.

An open opportunity's future remaining lifetime is unknown. Show observed duration, not a countdown or guarantee. Later, optional survival estimates can report the probability of remaining qualified for another H milliseconds/seconds, conditional on current age and features, with calibration and uncertainty. Until then show empirical historical cohort survival separately.

### Episode rules

Maintain state per verified asset, directed venue/product pair, quote route, strategy, fixed size, and qualification/config version. First qualifying valid observation starts the episode; each subsequent valid update reevaluates depth, fees, eligibility, available short route, and the specified exit/settlement assumptions. Reevaluate on metadata changes and health timers too, not just price changes. Duration is elapsed time, not a count of WebSocket messages.

Record first qualifying receipt timestamp, last confirmed qualifying timestamp, first failing timestamp, start/end reason, initial/peak/latest net estimate, gross entry gap, size, data quality, and qualification level. True crossing time lies between observations; retain those bounds instead of implying exact continuous observability.

On stale/disconnected/gapped data, mark the episode interrupted and right-censored at the last confirmed valid observation. Do not continue a profitable timer through an outage or record an outage as economic convergence. If already qualifying at startup/reconnection, flag the start as unknown/left-censored. Resume with a linked new observed segment once the book is valid again. Apply analogous censoring at end of recording.

Keep strict qualifying intervals for financial statistics. Optional display hysteresis may visually group brief flicker, but expose interruptions and never count below-threshold time as continuously profitable. Changing size, thresholds, fees, model assumptions, or exit target starts a separately versioned series. Share episode IDs across repeated messages and avoid duplicate opportunity counts.

### Live UI additions

Live table columns: first seen, active duration, last validated age, target size, latest net estimate, peak net estimate, gross gap, qualification level, status, and exact buy/short venue links. Status values include active, ended, interrupted, and insufficient inputs. 'Net estimate' for perpetual routes must visibly reference its exit assumption; unknown borrow availability or fees cannot produce a verified executable label.

Selecting a row shows its observed lifetime timeline, qualification threshold, gaps, book prices/depth, cost changes, and the reason it ended. Keep ended opportunities searchable by last X hours/days; X is configurable within available retention. Live counters include active episodes, new episodes today, observed coverage, and duration distributions with censoring disclosed.

Paper-position view shows entry time, elapsed holding time, current executable close estimate, accrued funding/borrow costs, exit target, timeout, and closure/settlement time. Report opportunity lifetime and position holding time in different columns and charts.

### Incremental delivery

The first usable interface delivers live candidates, exact venue links, active-duration timers, and completed/interrupted episode history on the initial connected venues. Persistent recording starts at the same time. Historical research, calibrated fill models, and position-holding simulations follow incrementally; the existing 14–30-day study is an observation target, not a prerequisite for using the live scanner.

Acceptance checks: timers track elapsed time correctly without new trades; feed failures interrupt qualification; identical messages do not create new episodes; threshold crossings and changed configurations produce correct boundaries; reconnect/startup censoring is visible; future data is never used to label past live decisions; open episode duration is never presented as predicted remaining life or actual position age.

## 16. Raspberry Pi deployment and staged funding

### Target and scope

User intends to run the scanner continuously on a Raspberry Pi and consider funding only if research shows promising opportunities. The initial deployment is public-data research and paper simulation; it does not place orders or require trading-enabled credentials. A future funded execution stage remains a separate implementation and authorization step.

Confirmed hardware: Raspberry Pi 4 with 4 GB RAM. Operating system, storage (microSD versus external SSD), and network connection remain to be confirmed. Target a supported 64-bit Linux/ARM64 environment where hardware permits; verify exact dependency wheels and build requirements on the device. Do not assume desktop performance or availability of every analysis dependency on every Pi. Raspberry Pi deployment supersedes the earlier generic 4-vCPU/8–16-GB host sizing hypothesis.

### Resource-aware architecture

Run collectors, validated in-memory books, detector, and lightweight API on the Pi. Serve a prebuilt React frontend as static files; build frontend assets on the development machine rather than keeping a development server or Node build process running on the Pi. The browser renders charts on the viewing device. Prefer Python virtual environment plus systemd services for the first deployment; containers are optional after ARM64 compatibility and memory overhead are verified.

Keep online calculation incremental: update only routes affected by a changed book or metadata record. Use bounded queues, bounded book depth, connection/subscription budgets, per-venue rate limits, and explicit backpressure. Separate ingestion from persistence so a slow disk cannot silently delay candidate evaluation. Any dropped sequence-dependent data invalidates its book and triggers resynchronization.

Use full-universe discovery and continuous depth coverage for all supported routes on selected venues. Do not substitute a representative sample or rotate coins based on apparent profitability. Shard subscriptions and workers within exchange limits. If hardware or API limits prevent complete coverage, report the shortfall and evaluate additional capacity; do not silently reduce scope. The optional Pi deployment is viable only if it can meet the chosen coverage requirement.

Use lightweight live scoring and cached metadata. Run large replays, model training, and multi-day analytical queries on the development computer initially, exporting recorded files from the Pi. Deploy only a small validated inference model to the Pi if later needed. Heavy analysis must not interfere with the live loop.

### Storage and retention

Prefer an external SSD for sustained market-data recording when available. Do not design around unlimited microSD writes or unlimited retention. Batch writes into compressed, time-partitioned files, rotate logs, and checkpoint episode state with SQLite transactions. Keep SQLite access controlled through a bounded writer queue and use WAL when supported by the local filesystem.

Make retention configurable by both age and byte budget: short retention for complete raw feeds, longer retention for normalized snapshots/events and episode evidence, and compact long-term episode/coverage summaries. Suggested pilot policy is 48 hours of raw feeds and 14 days of selected normalized data, subject to measured storage use; these are proposals, not capacity guarantees. Preserve the exact event windows needed for research runs before pruning. Store a coverage/retention manifest so missing history is never interpreted as no opportunities.

Measure bytes/hour during a 24-hour pilot before setting final retention. Reserve configurable free-space headroom. On low space, prune only data allowed by policy; if recording still cannot proceed, show degraded recording status and stop claiming fully reproducible research coverage. Never silently overwrite retained experiment evidence. Use atomic file finalization and recover safely after interrupted writes.

### All-day operation

Use systemd restart policies with bounded backoff, graceful shutdown, startup reconciliation, and persistent run IDs. Monitor process heartbeat, event-loop lag, reconnects, feed health, clock synchronization, queue pressure, CPU temperature/throttling where exposed, RAM, disk space, and recording lag. Alert locally in the UI; external notifications require a separately configured destination and user authorization.

After a reboot, rebuild exchange books from fresh snapshots and mark the downtime as a coverage gap. Restore episode records for history but do not continue an active timer through unknown data. Use monotonic clocks for durations within a boot and UTC for cross-run records. Persist paper balances, positions, and configuration; reconcile their state before restarting simulation.

Prefer stable networking, adequate cooling, and reliable power. Test connection loss, service crashes, abrupt restart, disk-pressure behavior, and resubscription after exchange maintenance. Continuous operation means automatic recovery plus visible gaps, not a guarantee of uninterrupted observation.

Serve the dashboard on the local network with configurable bind address and authentication when accessible beyond a trusted local machine. Keep secrets outside source control and browser payloads. For remote viewing, use an authenticated private network or tunnel rather than exposing an unauthenticated API publicly. No remote service purchase, installation on the user's Pi, or external exposure is implied by this specification.

### Performance acceptance gates

Profile the actual Pi before expanding venues: run a 24–48-hour soak with the intended feeds, record peak memory, data rate, disk growth, event-loop/processing latency percentiles, reconnection time, and observed data coverage. Set explicit device-specific limits after this baseline. A candidate must fail freshness checks when processing falls behind. Reduce subscriptions or move collection to stronger hardware if the supported load cannot meet the research's timing requirements.

Capture latency from the Pi's actual network path; replay execution-delay scenarios based on measured distributions and conservative stress cases. Opportunities shorter than attainable response time remain research observations, not executable candidates. A later execution service should run on the Pi only if its measured performance meets the strategy's requirements.

### Evidence before funding

Deliver live scanning and paper outcomes first. Evaluate multiple weeks of observations, chronological holdout performance, actual account-eligible shorting routes, complete entry/exit or settlement costs, one-sided-fill recovery, and finite collateral. Report uncertainty and concentration rather than extrapolating a few winning episodes into monthly income.

If results support proceeding and the user explicitly requests funded trading, implement a small capped execution pilot using a separately chosen capital allocation, account-specific fees, verified borrowing/product access, trading-only credentials, and tested reconciliation/recovery. The previously stated CAD 20,000 working budget is an eventual ceiling, not authorization to deploy it. Compare actual fills and net results with paper estimates before increasing capital or venue count. Funds should not be committed merely because the live scanner displays positive spreads.


### Optional later Raspberry Pi 4 / 4 GB pilot configuration

Confirmed device target is Raspberry Pi 4 with 4 GB RAM. Use a minimal supported 64-bit OS installation if compatible with the existing setup. Benchmark full required coverage before migrating from the Mac; the Pi must not impose a sampled universe. Small protocol fixtures are development tests only, not the production scanning scope.

Keep the frontend build and model training off-device. Initially use a single collector/detector service with asynchronous venue tasks plus a lightweight API/static-file service and one bounded persistence writer. Avoid duplicating book state across multiple API workers. Use bounded file batches and avoid loading historical datasets into RAM. Keep optional analysis dependencies outside the minimal collector installation where practical.

Set a provisional aggregate application-memory target below 2 GB, leaving headroom for the OS, filesystem cache, and transient reconnect/snapshot work. Measure process RSS and system available memory during the soak test; this target is an engineering budget, not measured consumption. Under sustained memory pressure or processing lag, reduce active subscriptions and visibly mark coverage changes. Do not rely on swap to keep the timing-sensitive scanner responsive.

Use SSD-backed recording if available; otherwise start with shorter raw retention and measure microSD write latency before increasing workload. Final storage policy depends on the actual disk capacity and measured bytes/hour. A successful pilot requires bounded memory and queue sizes, recoverable reconnects, recording within the selected disk budget, and freshness checks that reject delayed observations. No full-universe coverage or execution-latency guarantee is made before this benchmark.


## 17. Initial deployment: M2 MacBook Pro, 32 GB RAM

Latest user direction: develop and run the first scanner on an M2 MacBook Pro with 32 GB RAM. This is the active initial deployment target and supersedes the Pi-specific workload and memory budgets above. The Raspberry Pi 4 / 4 GB remains an optional later deployment profile, not a constraint on the initial implementation.

Do not impose the proposed Pi limits of two feeds, 20–50 shared assets, or a 2 GB application budget on the Mac. Target broad discovery across the selected 5–10 venues and continuous depth for as much verified shared spot/short coverage as their APIs and measured throughput support. Account eligibility and short availability still determine the executable universe. Introduce adapters incrementally to verify correctness, not to enforce a Pi-sized universe.

Run the Python collectors, detector, recorder, FastAPI service, React dashboard, and ordinary research queries locally on macOS/Apple Silicon. Frontend development and builds can run on this machine. Run heavier replays and model training locally too, while measuring their impact on live collection; schedule or isolate them if they delay feed processing. Verify ARM64 dependency compatibility during setup.

Retain exchange rate/subscription limits, bounded queues, stale-book rejection, log rotation, disk monitoring, and configurable retention as correctness and operational requirements. Set practical capacities from actual Mac measurements; do not inherit Pi-specific numeric limits or assume 32 GB allows unlimited recording. Require complete continuous-depth observation of supported routes, with explicit coverage gaps and no coin sampling.

For long unattended local sessions, provide a documented macOS launch command and optional user-controlled sleep prevention; record laptop sleep/network interruptions and resynchronize books after waking. Do not change system sleep settings automatically. Linux systemd setup belongs to the later Pi deployment profile.

Keep deployment-specific resource settings in configuration so migration to the Pi can be evaluated later without rewriting strategy logic. The first milestone is a working live Mac dashboard and recorder with venue links and opportunity-duration tracking, followed by expanded coverage and historical evaluation.


## 18. Full-universe scanning requirement

User explicitly rejects coin sampling. Continuously scan every supported verified spot-plus-short route on the selected exchanges, including low-volume markets, and automatically discover new listings and delistings. Do not choose a finite handpicked subset, rotate an active coin sample, or gate depth subscriptions on pre-existing visible spreads. The universe is necessarily bounded by venue listings, verifiable identities, short-product availability, and API access, not arbitrary coin-count limits.

Maintain counts of discovered instruments, identity-resolved instruments, supported routes, live synchronized routes, and gaps with reasons. Short borrow inventory may require authenticated checks; distinguish listed margin support from confirmed current borrowability without deleting research observations. Respect API limits through connection sharding and scheduling; where continuous coverage is infeasible, make the limitation visible and assess added infrastructure or a different feed. Do not claim complete observation until measured coverage supports it.

For the current shorting research, assess global product capability independently of Québec eligibility as requested. Preserve regional restrictions as metadata for any eventual funded deployment, not as an exclusion from this capability study.
