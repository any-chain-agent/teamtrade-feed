# desks.json feed — MUSE TRIAD

The one file the three Lovable sites poll every 5 minutes. Built by
`build-desks-json.py` (stdlib only, read-only) from the live trading-lane
sources named in `../lovable-triad-feed-contract.md`. Nothing is published
or hosted from here — hosting is a separate decision Alex has not made yet.

## Run

```
python3 build-desks-json.py            # writes desks.json next to the script
python3 build-desks-json.py --out PATH # writes elsewhere
```

Re-run any time; output is deterministic from the source files at run time.
`generated_at` is UTC. `"seed": false` — this is a live snapshot, not the seed.

## Schema (top level)

Contract sections (from `lovable-triad-feed-contract.md`):

| Section | Source | Notes |
|---|---|---|
| `desks[]` | the five `state.json` files + latest `desk` event in each `trades.log` | ref/sell/buy/stacks/baseline/earned/guard/halted verbatim; `band_pct` derived from sell/ref; `live_price` from the bots' own Jupiter quote in the log, freshness-gated at 15 min (older → `null`, `price_source: "unavailable"`) |
| `assigned[]` | **seed only** — Lovable prompt seed, 2026-11-26 | every entry `live: false, seed: true`; live assigned state is the portal server |
| `whale{}` | `whale-watch/whale-state-<lane>.json` | top10/largest/top20/holders_tracked/`as_of` = last live snapshot; `top10[]` = top-10 wallet list (address + share) behind the figures; `thresholds` names the FLAGGED/CAUTION lines; SOL is `no_data` with no list |
| `bundle{}` | **computed here** from the whale figures, portal thresholds | FLAGGED top10≥50 or largest≥20; CAUTION ≥30/≥10; CLEAN below; UNAVAILABLE when not live; SOL NOT_APPLICABLE (WSOL proxy). Concentration only (Stage 1), not cluster detection |
| `cross_pair` | `cross-pair-watch/cross-pair-state.json` | `near_miss` = prospective candidates ≤1.5pp from a buy trigger (currently none); `turnover_ranking` = all candidates ranked by score/day; `open_paper_loans` (3, all → HAPPY); `arb_scans`; `last_near_miss_signals`. PAPER ONLY |
| `shadow[]` | `shadow-state.json` | 4 paper portfolios; `earned_pct` computed exactly as shadow.mjs does (token + usdc/last price vs seed_token + seed_usdc/seed_reference) |
| `backtest` | `backtest-shuffle.json` | p-values + runs only (SOL 0.145, HAPPY 0.195, 200 runs each) — never `live_earned` (see caveats) |
| `trades[]` | `TRADE_EXECUTED` events, all five `trades.log` files | 8 events, full tx + solscan link; buys use the `<token>_expected` amount the log records; the 2026-11-24 SOL buy carries its reconciliation note verbatim |
| `decisions[]` | latest `desk` event per desk | manager reason verbatim, decision parsed from its prefix |
| `nightly_review` | `feed/nightly-review.json` (written by cron `trading-nightly-review`, daily 21:04 MST) | first file lands 2026-11-27 21:04 MST; until then `status: "unavailable"`. Carries date, regime call, per-desk outcome vs Grok's calls, trades that day, losses-first summary. Old `nightly` key kept as a pointer to it |
| `market` | `feed/market.json` (written by cron `trading-stock-market-watch`, weekdays ~15:07 MST) | next run Fri 2026-11-27 15:07 MST; until then `status: "unavailable"`. S&P/Nasdaq/Dow/VIX + BTC/SOL divergence note |

Extension sections (not in the contract's printed schema):

| Section | Source | Notes |
|---|---|---|
| `wallet` | `state.json` `pool_SOL` (all five agree) | 0.5 SOL permanent ops reserve, NEVER traded; reported here only, never inside any desk stack |
| `funding_moves[]` | `funding_rotation_*` events in SOL/HAPPY logs | move #1, 2026-11-26: HAPPY → SOL, 0.0071 SOL / $0.506, tx null (desk-state only) |
| `odds` | `odds-sharpening-calibration-2026-11-26.json` | per-desk check rows + executed band-trade counts; 4 independent episodes ever — too few to calibrate |
| `reserve` | `sol-usdc-trading/position-reserve.json` | $15.00 (0.208505 SOL) earmarked from the 0.5 SOL pool 2026-11-27, available to activate new positions when requested; ledger earmark only, no on-chain transfer; pool remaining 0.291495 SOL |
| `top_picks` | — | `status: "unavailable"` — top-picks scan lives in the portal server only |

`notes[]` inside the file records the extensions, the seed labelling, the
price-freshness rule, and the known data caveats (below).

## Rules enforced by the writer

- Any section whose source is down reports `status: "unavailable"` — never a
  stale number as live.
- Exact figures from the state files, never rounded.
- No keys, credentials, or key material anywhere in the script or the output
  (verified: no `api-key`/`hsurr`/`secret` strings in `desks.json`).
- The writer never reads the portal's `app.db` directly.

## Gaps / flags (things the contract assumes that the live sources do not support)

1. **Assigned desks have no live local source.** TRUMP / JUP / crypto /
   SHAREWARE / WBTC live only in the portal server (`app.db`). The feed
   carries their 2026-11-26 seed values, labelled `seed`. If the apps need
   live assigned state, the portal must export it (or the feed must read it
   through a portal action — not direct DB access).
2. **No nightly-review record file — YET.** Cron `trading-nightly-review`
   now writes `feed/nightly-review.json` each run (first file tonight
   2026-11-27 21:04 MST); the writer picks it up as `nightly_review`.
3. **No stock-market-watch data file — YET.** Cron
   `trading-stock-market-watch` now writes `feed/market.json` each weekday
   run (next Fri 2026-11-27 15:07 MST); the writer picks it up as `market`.
4. **No top-picks file.** The scan lives in the portal server only.
5. **SOL whale lane still `no_data`.** Helius refuses
   `getTokenLargestAccounts` for wSOL (-32600); Alchemy key still fails auth
   (separate open thread). Bundle verdict for SOL is NOT_APPLICABLE by rule,
   not by data.
6. **`reference_set_at` is stale on re-referenced desks — FIXED IN THE
   FEED (2026-11-27).** The writer now derives it from each desk's latest
   `TRADE_EXECUTED` (feed-only; the bots' `state.json` files are untouched).
   Desks with no trades yet fall back to `state.json`'s value, and the
   source is named in `reference_set_at_source`.
7. **HAPPY ledger overstatement, unfixed** (audit BLOCKER-adjacent): the
   desk ledger overstates the on-chain stack by 44.764142 HAPPY (~$0.01).
   The feed carries ledger figures, as the bots hold them.
8. **PENGU trigger last digit**: state.json reads 0.0046203 / 0.0037802;
   the Lovable prompt seed carries 0.00462027 / 0.00378022. State.json wins.
9. **Backtest `live_earned` is not carried**: the shuffle file's HAPPY
   `live_earned` (16,745.44) overstates the live desk (audit BLOCKER 1).
   Only p-values and run counts are fed.

## First snapshot

`desks.json`, generated 2026-11-27T13:50:48Z: 5 desks (all live prices fresh
from Jupiter, ≤4 min old), 8 trades, 5 decisions, 4 shadow portfolios,
3 open paper loans, 0 near-misses, whale live on HAPPY/WIF/RAY/PENGU
(bundle: RAY FLAGGED, HAPPY/WIF/PENGU CAUTION, SOL NOT_APPLICABLE),
backtest SOL p=0.145 / HAPPY p=0.195.
