#!/usr/bin/env python3
"""Build desks.json — the MUSE TRIAD feed (Scout / Skeptic / Judge).

Reads ONLY local, read-only trading-lane sources and assembles one JSON file
the three Lovable sites poll every 5 minutes.

Sources (per lovable-triad-feed-contract.md):
  desks       <- the five desk state.json files (+ latest price/decision from
                 each desk's trades.log "desk" events; state.json last_price
                 is NOT used — it goes stale, e.g. HAPPY's is 2026-11-26)
  whale       <- happy-usdc-trading/whale-watch/whale-state-<lane>.json
  bundle      <- Stage 1 verdicts COMPUTED here from the whale figures with
                 the portal's own thresholds (computeBundleVerdict):
                 FLAGGED top10>=50 or largest>=20; CAUTION >=30 / >=10;
                 CLEAN when live and below; UNAVAILABLE when not live;
                 SOL is NOT_APPLICABLE (WSOL proxy holders are wrappers)
  cross_pair  <- sol-usdc-trading/cross-pair-watch/cross-pair-state.json
  shadow      <- sol-usdc-trading/shadow-state.json (earned_pct computed
                 exactly as shadow.mjs does: token + usdc/last price vs
                 seed_token + seed_usdc/seed_reference)
  backtest    <- sol-usdc-trading/backtest-shuffle.json (p-values + runs only)
  trades      <- TRADE_EXECUTED events from all five trades.log files
  decisions   <- latest "desk" event per desk (manager reason, verbatim)
  funding_moves <- funding_rotation_in/out events in the SOL/HAPPY logs
  odds        <- cross-pair-watch/odds-sharpening-calibration-2026-11-26.json

NOT sourced here (no local live file exists; the writer never reads the
portal's app.db directly):
  assigned    <- seed-labelled entries only (last-known values from the
                 Lovable prompt seed, 2026-11-26); live source is the
                 portal server
  top_picks   <- unavailable (portal server only)
  nightly_review <- feed/nightly-review.json once the nightly cron has
                 written it (first file lands 2026-11-27 21:04 MST);
                 unavailable until then
  market      <- feed/market.json once the stock-market watch has written
                 it (next weekday run); unavailable until then
  reserve     <- sol-usdc-trading/position-reserve.json (the $15 position
                 reserve earmarked from the 0.5 SOL pool, 2026-11-27);
                 published verbatim

Rules (contract):
  * Any section whose source is down reports status "unavailable" — never a
    stale number presented as live.
  * Exact figures from the state files, never rounded.
  * The 0.5 SOL pool is a permanent ops reserve, never traded — it is
    reported in the "wallet" section only, never inside any desk stack.
  * live_price freshness: a price older than 15 minutes at generation time
    becomes null with price_source "unavailable".
  * reference_set_at is DERIVED per desk from its latest TRADE_EXECUTED
    in trades.log (a trade re-references the desk); desks with no trades
    yet fall back to state.json's value. The state files still carry the
    stale value — the correction lives in the feed only.
  * No keys, credentials, or key material anywhere in this file or script.

Usage: python3 build-desks-json.py [--out PATH]
Default output: <this dir>/desks.json
"""

import json
import os
import sys
from datetime import datetime, timezone

WS = os.path.expanduser("~/workspace")
FEED_DIR = os.path.dirname(os.path.abspath(__file__))

WALLET = "FE7DrfLDUV6868MFK2YEDVMNtj4X7G92bUFsbdS7frnX"
POOL_SOL = 0.5

# Position reserve (2026-11-27): $15 earmarked from the 0.5 SOL ops pool,
# available to activate new positions when requested. Ledger earmark only
# — no on-chain transfer, no desk stacks changed. The fallback figures
# below are used ONLY if position-reserve.json cannot be read; the file
# is the source of truth.
RESERVE_FALLBACK = {
    "source": "0.5 SOL ops pool (FE7)",
    "reserve_sol": 0.208505,
    "reserve_usd": 15.00,
    "sol_price_usd": 71.9407,
    "price_source": "Jupiter lite-api",
    "pool_sol_before": 0.5,
    "pool_sol_remaining": 0.291495,
    "purpose": "available to activate new positions when requested",
}

# Token identities (immutable; from the Lovable prompt seed — not live data).
DESKS = [
    {"id": "sol", "token": "SOL", "symbol": "SOL",
     "mint": "So11111111111111111111111111111111111111112",
     "state": "sol-usdc-trading/state.json",
     "log": "sol-usdc-trading/trades.log",
     "stack_key": "stack_SOL", "initial_key": "initial_stack_SOL",
     "earned_key": "earned_sol_equiv"},
    {"id": "happy", "token": "$HAPPY", "symbol": "$HAPPY",
     "mint": "68fn2tLABKmS7VA9Eaz3n6RfoXM3iBWUACckT9dwpump",
     "state": "happy-usdc-trading/state.json",
     "log": "happy-usdc-trading/trades.log",
     "stack_key": "stack_HAPPY", "initial_key": "initial_stack_HAPPY",
     "earned_key": "earned_happy_equiv"},
    {"id": "wif", "token": "WIF", "symbol": "WIF",
     "mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
     "state": "wif-usdc-trading/state.json",
     "log": "wif-usdc-trading/trades.log",
     "stack_key": "stack_WIF", "initial_key": "initial_stack_WIF",
     "earned_key": "earned_wif_equiv"},
    {"id": "ray", "token": "RAY", "symbol": "RAY",
     "mint": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",
     "state": "ray-usdc-trading/state.json",
     "log": "ray-usdc-trading/trades.log",
     "stack_key": "stack_RAY", "initial_key": "initial_stack_RAY",
     "earned_key": "earned_ray_equiv"},
    {"id": "pengu", "token": "PENGU", "symbol": "PENGU",
     "mint": "2zMMhcVQEXDtdE6vsFS7S7D5oUodfJHE8vd1gnBouauv",
     "state": "pengu-usdc-trading/state.json",
     "log": "pengu-usdc-trading/trades.log",
     "stack_key": "stack_PENGU", "initial_key": "initial_stack_PENGU",
     "earned_key": "earned_pengu_equiv"},
]

# Assigned tabs: SEED values only (Lovable prompt seed, 2026-11-26).
# No live local source exists — live state is the portal server (app.db),
# which this writer deliberately does not read.
ASSIGNED_SEED = [
    {"id": "trump", "name": "TRUMP",
     "mint": "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN",
     "status": "awaiting_funding", "ref": 0.876563932497214,
     "sell": 0.9642203257469356, "buy": 0.7889075392474926,
     "stack_token": 0, "stack_usdc": 0},
    {"id": "jup", "name": "JUP",
     "mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
     "status": "awaiting_funding", "ref": 0.2331316379425564,
     "sell": 0.25644480173681206, "buy": 0.20981847414830077,
     "stack_token": 0, "stack_usdc": 0},
    {"id": "crypto", "name": "Cryptocurrency Coin",
     "mint": "4ikwYoNvoGEwtMbziUyYBTz1zRM6nmxspsfw9G7Bpump",
     "status": "awaiting_funding", "ref": 0.00218538,
     "sell": None, "buy": None, "stack_token": 0, "stack_usdc": 0},
    {"id": "shareware", "name": "SHAREWARE",
     "mint": "C3LfnHv7ivuwCwPBtNpW922nWZ73qb95KnzzFBBvpump",
     "status": "no_pool", "ref": None, "sell": None, "buy": None,
     "stack_token": 0, "stack_usdc": 0},
    {"id": "wbtc", "name": "WBTC",
     "mint": "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",
     "status": "awaiting_funding", "ref": 60827.2506,
     "sell": None, "buy": None, "stack_token": 0, "stack_usdc": 0},
]

PRICE_FRESH_SECONDS = 15 * 60


def load_json(path):
    with open(os.path.join(WS, path)) as f:
        return json.load(f)


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def latest_log_events(log_path):
    """Return (latest desk event, TRADE_EXECUTED list, funding events)."""
    latest_desk = None
    trades = []
    funding = []
    with open(os.path.join(WS, log_path)) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = e.get("event")
            if ev == "desk":
                latest_desk = e
            elif ev == "TRADE_EXECUTED":
                trades.append(e)
            elif ev in ("funding_rotation_in", "funding_rotation_out"):
                funding.append(e)
    return latest_desk, trades, funding


def bundle_verdict(lane_id, top10, largest, data_status):
    """Portal computeBundleVerdict thresholds (Stage 1, concentration only)."""
    if lane_id == "sol":
        return ("NOT_APPLICABLE",
                "SOL holders are measured through the WSOL proxy — top "
                "holders are wrapping contracts and bridges, not a token "
                "holder base")
    if data_status != "live" or top10 is None or largest is None:
        return ("UNAVAILABLE",
                "holder feed down — no live top-holder data")
    if top10 >= 50 or largest >= 20:
        trig = ("top-10 holds %.4f%% of supply" % top10
                if top10 >= 50 else
                "largest holder holds %.4f%% of supply" % largest)
        return ("FLAGGED", trig)
    if top10 >= 30 or largest >= 10:
        trig = ("top-10 holds %.4f%% of supply" % top10
                if top10 >= 30 else
                "largest holder holds %.4f%% of supply" % largest)
        return ("CAUTION", trig)
    return ("CLEAN", "below both caution lines")


def build(now):
    out = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "seed": False,
        "wallet": {
            "address": WALLET,
            "pool_sol": POOL_SOL,
            "pool_note": "0.5 SOL permanent ops reserve, NEVER traded — "
                         "not part of any desk stack",
        },
    }

    # ---- desks ------------------------------------------------------
    desks_out = []
    decisions_out = []
    trades_out = []
    funding_out = []
    for d in DESKS:
        s = load_json(d["state"])
        desk_block = s.get("desk", {})
        scanner = desk_block.get("scanner", {})
        manager = desk_block.get("manager", {})
        guard = desk_block.get("guard", {})
        exit_block = desk_block.get("exit", {})
        ref = s["reference_price"]
        sell = exit_block.get("sell_trigger")
        buy = exit_block.get("buy_trigger")
        band_pct = round((sell / ref - 1) * 100) if ref and sell else None

        latest_desk, log_trades, log_funding = latest_log_events(d["log"])
        # Live price: latest desk event's scanner price, freshness-gated.
        live_price, price_at, price_source = None, None, "unavailable"
        if latest_desk:
            sc = (latest_desk.get("desk") or {}).get("scanner") or {}
            p, at = sc.get("price"), latest_desk.get("at")
            pts = parse_ts(at)
            if p is not None and pts is not None and \
                    (now - pts).total_seconds() <= PRICE_FRESH_SECONDS:
                live_price, price_at, price_source = p, at, "jupiter"
            elif p is not None:
                price_at = at  # kept only as a timestamp, never as live

        # reference_set_at: state.json's value goes stale on re-reference
        # (every trade resets the reference). Derive from the latest
        # TRADE_EXECUTED in the desk's log; fall back to state.json for
        # desks that have never traded. Feed-only correction — the bots'
        # state files are never touched.
        ref_set_at = s.get("reference_set_at")
        ref_set_source = "state.json (desk has no trades yet)"
        if log_trades:
            last_trade = log_trades[-1]
            if last_trade.get("at"):
                ref_set_at = last_trade["at"]
                ref_set_source = ("derived from latest TRADE_EXECUTED "
                                  "(%s, tx %s)"
                                  % (last_trade.get("side"),
                                     last_trade.get("tx") or "null"))

        desks_out.append({
            "id": d["id"],
            "token": d["token"],
            "mint": d["mint"],
            "ref": ref,
            "sell": sell,
            "buy": buy,
            "band_pct": band_pct,
            "stack_token": s[d["stack_key"]],
            "stack_usdc": s["stack_USDC"],
            "baseline": s[d["initial_key"]],
            "earned_token_equiv": manager.get(d["earned_key"]),
            "guard_drawdown_from_peak_pct":
                guard.get("drawdown_from_peak_pct"),
            "guard_status": guard.get("status"),
            "halted": s.get("halted", False),
            "live_price": live_price,
            "price_at": price_at,
            "price_source": price_source,
            "change_pct_vs_ref": scanner.get("change_pct"),
            "reference_set_at": ref_set_at,
            "reference_set_at_source": ref_set_source,
        })

        if latest_desk:
            reason = latest_desk.get("reason") or ""
            decision = "hold"
            low = reason.lower()
            if low.startswith("sell"):
                decision = "sell"
            elif low.startswith("buy"):
                decision = "buy"
            decisions_out.append({
                "at": latest_desk.get("at"),
                "desk": d["id"],
                "decision": decision,
                "reason": reason,
            })

        token_key = {"sol": "sol", "happy": "happy", "wif": "wif",
                     "ray": "ray", "pengu": "pengu"}[d["id"]]
        for e in log_trades:
            # Buys record the expected amount under "<token>_expected";
            # sells/splits record it under the bare token key.
            amount = e.get(token_key)
            if amount is None:
                amount = e.get(token_key + "_expected")
            entry = {
                "desk": d["id"],
                "side": e.get("side"),
                "amount_token": amount,
                "amount_usdc": e.get("usdc", e.get("usdc_expected")),
                "price": e.get("price"),
                "tx": e.get("tx"),
                "solscan": e.get("solscan"),
                "at": e.get("at"),
                "earned_token_equiv_after": e.get(d["earned_key"]),
            }
            if e.get("note"):
                entry["note"] = e["note"]
            trades_out.append(entry)
        for e in log_funding:
            funding_out.append({
                "at": e.get("at"),
                "event": e.get("event"),
                "move_id": e.get("move_id"),
                "source": e.get("source"),
                "dest": e.get("dest"),
                "amount_sol": e.get("amount_sol"),
                "amount_usd": e.get("amount_usd"),
                "tx": e.get("tx"),
                "note": e.get("note"),
            })

    out["desks"] = desks_out
    out["decisions"] = sorted(decisions_out, key=lambda x: x["at"] or "")
    out["trades"] = sorted(trades_out, key=lambda x: x["at"] or "")
    out["funding_moves"] = sorted(funding_out, key=lambda x: x["at"] or "")

    # ---- position reserve (Alex's $15 earmark, 2026-11-27) ------------
    try:
        reserve = load_json("sol-usdc-trading/position-reserve.json")
    except (FileNotFoundError, json.JSONDecodeError):
        reserve = dict(RESERVE_FALLBACK)
        reserve["note"] = ("position-reserve.json unreadable — fallback "
                           "figures from the 2026-11-27 earmark")
    # Running balance: remaining_sol is maintained by
    # execute-assigned-funding.mjs on every reserve draw (absent until
    # the first draw, it equals reserve_sol); draws[] is the draw history.
    # Both ride the feed so the Treasury record stays complete.
    if reserve.get("remaining_sol") is None:
        reserve["remaining_sol"] = reserve.get("reserve_sol")
    if reserve.get("draws") is None:
        reserve["draws"] = []
    out["reserve"] = reserve

    # ---- assigned (seed only — no live local source) ----------------
    out["assigned"] = [
        dict(a, live=False, seed=True, seed_as_of="2026-11-26",
             seed_note="last-known values from the Lovable prompt seed; "
                       "live state is the portal server")
        for a in ASSIGNED_SEED
    ]

    # ---- whale + bundle ---------------------------------------------
    whale_out, bundle_out = {}, {}
    for d in DESKS:
        lane = d["id"]
        try:
            w = load_json(
                f"happy-usdc-trading/whale-watch/whale-state-{lane}.json")
        except (FileNotFoundError, json.JSONDecodeError):
            w = None
        if w is None:
            whale_out[lane] = {"status": "unavailable", "top10_pct": None,
                               "largest_pct": None, "as_of": None,
                               "top10": None,
                               "top10_note": "wallet list unavailable — "
                                             "whale state file unreadable",
                               "thresholds": "FLAGGED top10>=50 or "
                                             "largest>=20; CAUTION "
                                             "top10>=30 or largest>=10"}
            bundle_out[lane] = {"verdict": "UNAVAILABLE", "top10_pct": None,
                                "largest_pct": None, "reason":
                                "whale state file unreadable"}
            continue
        m = w.get("metrics") or {}
        lh = m.get("largest_holder") or {}
        top10 = m.get("top10_pct")
        largest = lh.get("pct_of_supply") if isinstance(lh, dict) else None
        status = w.get("data_status")
        # Top-10 wallet list behind the concentration figures — the same
        # live snapshot the percentages come from. SOL has no list
        # (no live snapshot); report unavailable, never invent.
        holders = w.get("top_holders") or []
        top10_list, top10_note = None, None
        if status == "live" and len(holders) >= 10:
            top10_list = [{
                "rank": h.get("rank"),
                "address": h.get("address"),
                "amount": h.get("amount"),
                "pct_of_supply": h.get("pct_of_supply"),
            } for h in holders[:10]]
        elif status == "live":
            top10_note = ("wallet list unavailable — live snapshot holds "
                          "fewer than 10 holders")
        else:
            top10_note = ("wallet list unavailable — no live holder "
                          "snapshot for this lane")
        whale_out[lane] = {
            "status": "live" if status == "live" else "no_data",
            "top10_pct": top10,
            "largest_pct": largest,
            "top20_pct": m.get("top20_pct"),
            "holders_tracked": m.get("holders_tracked"),
            "as_of": w.get("last_live_snapshot_at"),
            "runs": w.get("runs"),
            "top10": top10_list,
            "top10_note": top10_note,
            "thresholds": "FLAGGED top10>=50 or largest>=20; "
                          "CAUTION top10>=30 or largest>=10",
        }
        verdict, reason = bundle_verdict(lane, top10, largest, status)
        bundle_out[lane] = {
            "verdict": verdict,
            "top10_pct": top10,
            "largest_pct": largest,
            "reason": reason,
            "checked_at": w.get("updated"),
            "thresholds": "FLAGGED top10>=50 or largest>=20; "
                          "CAUTION top10>=30 or largest>=10",
        }
    out["whale"] = whale_out
    out["bundle"] = bundle_out

    # ---- cross-pair ---------------------------------------------------
    try:
        cp = load_json("sol-usdc-trading/cross-pair-watch/cross-pair-state.json")
    except (FileNotFoundError, json.JSONDecodeError):
        cp = {}
    turnover = (cp.get("turnover") or {})
    candidates = turnover.get("candidates") or []
    ranking = []
    for c in candidates:
        t = c.get("turnover") or {}
        ranking.append({
            "kind": c.get("kind"),
            "id": c.get("id"),
            "source": c.get("source"),
            "dest": c.get("dest"),
            "amount_usdc": c.get("amount_usdc"),
            "dest_dist_to_buy_pp": c.get("dest_dist_to_buy_pp"),
            "score_pct_per_day": t.get("score_pct_per_day"),
            "net_gain_usd": t.get("net_gain_usd"),
            "net_return_pct": t.get("net_return_pct"),
            "hold_hours_rw": t.get("hold_hours_rw"),
        })
    ranking.sort(key=lambda r: (r["score_pct_per_day"] is None,
                                -(r["score_pct_per_day"] or 0)))
    # Near-miss = a destination within 1.5pp of its buy trigger (the
    # watcher's own reporting line). Nothing is within it right now.
    near_miss = [r for r in ranking
                 if r["kind"] == "prospective"
                 and r["dest_dist_to_buy_pp"] is not None
                 and r["dest_dist_to_buy_pp"] <= 1.5]
    loans = []
    for loan in (cp.get("paper_loans") or []):
        if loan.get("status") != "open":
            continue
        t = loan.get("turnover_remaining") or {}
        loans.append({
            "id": loan.get("id"),
            "source": loan.get("source"),
            "dest": loan.get("dest"),
            "amount_usdc": loan.get("amount_usdc"),
            "dest_buy_price": loan.get("dest_buy_price"),
            "dest_sell_trigger": loan.get("dest_sell_trigger"),
            "at": loan.get("at"),
            "mark_to_market_usd": loan.get("mark_to_market_usd"),
            "score_pct_per_day": t.get("score_pct_per_day"),
            "net_gain_usd": t.get("net_gain_usd"),
        })
    out["cross_pair"] = {
        "near_miss": near_miss,
        "last_near_miss_signals": (cp.get("last_signals") or {}).get("w4", {}),
        "turnover_ranking": ranking,
        "turnover_at": turnover.get("at"),
        "open_paper_loans": loans,
        "arb_scans": cp.get("arb_scans") or {},
        "runs": cp.get("runs"),
        "note": "PAPER ONLY — rotation is paper until Alex approves a "
                "real move naming source, destination and amount",
    }

    # ---- shadow -------------------------------------------------------
    try:
        sh = load_json("sol-usdc-trading/shadow-state.json")
    except (FileNotFoundError, json.JSONDecodeError):
        sh = {}
    shadow_out = []
    last_processed = sh.get("last_processed") or {}
    for pid, p in (sh.get("portfolios") or {}).items():
        desk_id = p.get("desk")
        lp = (last_processed.get(desk_id) or {})
        lp_price = lp.get("price")
        seed_ref = p.get("seed_reference")
        earned_pct = None
        if lp_price and seed_ref:
            equiv = p["token"] + p["usdc"] / lp_price
            seed_equiv = p["seed_token"] + p["seed_usdc"] / seed_ref
            earned_pct = (equiv - seed_equiv) / seed_equiv * 100
        shadow_out.append({
            "id": pid,
            "desk": desk_id,
            "variant": p.get("variant"),
            "token": p.get("token"),
            "usdc": p.get("usdc"),
            "reference": p.get("reference"),
            "trailing_armed": p.get("trailing_armed"),
            "trades": p.get("trades"),
            "fees_token": p.get("fees_token"),
            "earned_pct": earned_pct,
            "last_processed_price": lp_price,
            "last_processed_at": lp.get("at"),
            "seeded_at": sh.get("seeded_at"),
        })
    out["shadow"] = shadow_out

    # ---- backtest -----------------------------------------------------
    try:
        bt = load_json("sol-usdc-trading/backtest-shuffle.json")
    except (FileNotFoundError, json.JSONDecodeError):
        bt = {}
    backtest_out = {"generated_at": bt.get("generated_at"), "runs": bt.get("runs")}
    for row in (bt.get("desks") or []):
        key = "happy" if row.get("desk") == "$HAPPY" else row.get("desk", "").lower()
        backtest_out[key] = {
            "p": row.get("empirical_p"),
            "runs": row.get("runs"),
            "live_trades": row.get("live_trades"),
            "window_start": row.get("window_start"),
            "window_end": row.get("window_end"),
        }
    backtest_out["note"] = (
        "Shuffle robustness only — neither p is significant, no edge "
        "proven. Audit flag (2026-11-26): the shuffle file's HAPPY "
        "live_earned (16,745.44) overstates the live desk; only p/runs "
        "are carried here, never live_earned.")
    out["backtest"] = backtest_out

    # ---- odds (extension: calibration dataset) ------------------------
    try:
        oc = load_json(
            "sol-usdc-trading/cross-pair-watch/"
            "odds-sharpening-calibration-2026-11-26.json")
    except (FileNotFoundError, json.JSONDecodeError):
        oc = {}
    odds_out = {"generated_at": oc.get("generated_at_utc"), "desks": {}}
    for name, row in (oc.get("desks") or {}).items():
        odds_out["desks"][name.lower().replace("$", "")] = {
            "check_rows": row.get("check_rows"),
            "first": row.get("first"),
            "last": row.get("last"),
            "exec_band_trades": len(row.get("exec_band_trades") or []),
        }
    odds_out["note"] = ("Calibration dataset only (2026-11-26): 4 independent "
                        "trigger episodes ever — too few to calibrate; "
                        "portal odds formula stays the fallback.")
    out["odds"] = odds_out

    # ---- nightly review (record file written by the nightly cron) -----
    try:
        nr = load_json("sol-usdc-trading/feed/nightly-review.json")
        out["nightly_review"] = dict(nr)
        out["nightly_review"]["status"] = "live"
    except (FileNotFoundError, json.JSONDecodeError):
        out["nightly_review"] = {
            "status": "unavailable",
            "note": "No nightly-review record file yet — cron "
                    "trading-nightly-review writes "
                    "feed/nightly-review.json each run (daily 21:04 MST); "
                    "first file lands tonight 2026-11-27.",
        }
    # Old key kept as a pointer so earlier consumers do not break.
    out["nightly"] = {"status": out["nightly_review"]["status"],
                      "note": "see nightly_review"}

    # ---- market (record file written by the stock-market watch) -------
    try:
        mk = load_json("sol-usdc-trading/feed/market.json")
        out["market"] = dict(mk)
        out["market"]["status"] = "live"
    except (FileNotFoundError, json.JSONDecodeError):
        out["market"] = {
            "status": "unavailable",
            "note": "No market record file yet — cron "
                    "trading-stock-market-watch writes feed/market.json "
                    "each weekday run (~15:07 MST); next run Fri "
                    "2026-11-27 15:07 MST.",
        }
    out["top_picks"] = {
        "status": "unavailable",
        "note": "THE SYSTEM'S TOP PICKS live in the portal server only; "
                "this writer does not read the portal database.",
    }

    out["notes"] = [
        "Contract sections: desks, assigned, whale, bundle, cross_pair, "
        "shadow, backtest, trades, decisions, nightly_review, market.",
        "Extension sections (not in the contract's printed schema): "
        "wallet, funding_moves, odds, reserve, top_picks.",
        "assigned entries are SEED-labelled (live=false) — no live local "
        "source; live assigned state is the portal server.",
        "Bundle verdicts are computed here from the whale-state files with "
        "the portal's own thresholds; they are concentration only (Stage 1), "
        "not cluster detection.",
        "Prices come from the bots' own Jupiter quotes in trades.log; a "
        "price older than 15 minutes at generation time is reported "
        "unavailable, never as live.",
        "Known data caveat (audit 2026-11-26, unfixed): the HAPPY desk "
        "ledger overstates the on-chain stack by 44.764142 HAPPY (the "
        "2026-11-25 buy recorded Jupiter's quote expectedOut instead of "
        "the actual received 116203.107076). Figures here are the ledger "
        "figures, as the bots hold them.",
        "reference_set_at is DERIVED in this feed from each desk's latest "
        "TRADE_EXECUTED (a trade re-references the desk); desks with no "
        "trades yet fall back to state.json's value, and the source is "
        "named in reference_set_at_source. The bots' state.json files "
        "still carry the stale value — the correction lives in the feed "
        "only.",
        "reserve: $15.00 (0.208505 SOL) earmarked from the 0.5 SOL ops "
        "pool (FE7) on 2026-11-27, available to activate new positions "
        "when requested; ledger earmark only — no on-chain transfer, no "
        "desk stacks changed. Pool remaining after the earmark: 0.291495 "
        "SOL.",
        "whale.top10 carries the top-10 wallet list (address + share) "
        "behind each lane's concentration figures, from the same live "
        "snapshot; SOL has no list (no live snapshot).",
        "PENGU triggers in state.json read 0.0046203 / 0.0037802; the "
        "Lovable prompt seed carries 0.00462027 / 0.00378022 (last-digit "
        "rounding). State.json wins here.",
    ]
    return out


def main():
    out_path = None
    args = sys.argv[1:]
    if "--out" in args:
        out_path = args[args.index("--out") + 1]
    if not out_path:
        out_path = os.path.join(FEED_DIR, "desks.json")
    now = datetime.now(timezone.utc)
    data = build(now)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"wrote {out_path}")
    print(f"  generated_at: {data['generated_at']}")
    print(f"  desks: {len(data['desks'])}, trades: {len(data['trades'])}, "
          f"decisions: {len(data['decisions'])}, "
          f"shadow: {len(data['shadow'])}, "
          f"open paper loans: {len(data['cross_pair']['open_paper_loans'])}, "
          f"near-miss: {len(data['cross_pair']['near_miss'])}")
    print(f"  reserve: ${data['reserve'].get('reserve_usd')} "
          f"({data['reserve'].get('reserve_sol')} SOL); "
          f"nightly_review: {data['nightly_review'].get('status')}; "
          f"market: {data['market'].get('status')}; "
          f"whale top10 lists: "
          f"{sum(1 for v in data['whale'].values() if v.get('top10'))}/5")


if __name__ == "__main__":
    main()
