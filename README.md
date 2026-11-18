# Washout + Trend-Ride cbBTC Bot — btc-race-24h-20261118-1444

Long-only 1-minute cbBTC/USDC trader for make.fun's 24h race
(`agent-fun/bars-replay/v1`, Python 3.13, stdlib only, $1,000 paper).
Entrypoint: `main.py`. The SDK shim is vendored byte-for-byte under
`vendor/makefun_bars.py` (kit copy, excluded from authorship counts).

## Why this is not a straight port

The previous iteration of this design **failed the dev gate on this
kit's window** (−$1.60, 2 trades): it waited for 121 bars of history
before trading at all, and this window's only washout-grade drop
(−2.31% over 60 minutes, bars 65–70) happened before bar 121, so its
washout never fired. Its one trade was a trend ride on a slow grind
that faded (buy $64,437.00, sell $64,282.16). A straight port would
not race. Three changes fix it, each validated on **two different 24h
windows** (this kit's dev window and the previous race's dev window):

1. **Trade earlier.** The 60-minute washout leg and the trend leg arm
   at bar 61 (they need 61 and 31 bars of history); only the
   120-minute leg still waits for 121 bars. This catches the early
   drop: buy filled at $63,646.15 (bar 67), sold at $64,588.30
   (bar 472).
2. **Stronger trend filter.** Trend needs a 30-minute return of
   ≥ +1.0% (was +0.8%) with EMA(8) above EMA(21). The +0.8% level
   fired on the slow grind that lost −$1.60 here and on a weak early
   rally on the previous window (bar 107, −$2.18). At +1.0% both
   losing rides disappear; only the strong rally (previous window,
   bars 509–537, 30-minute returns up to +2.22%) still rides.
3. **Wider washout take-profit.** TP is +1.5% over the blended entry
   (was +1.2%). On this window the first bounce leg topped at +1.01%
   and the second at +1.43% over entry, so +1.2% exits on the second
   leg; +1.5% waits for the later, higher leg (block 2 topped +2.39%
   over entry). On the previous window the washout bounce topped at
   +1.97%, so +1.5% clears it with margin — while +2.0% would NOT
   have (that variant collapses to +$3.85 there). +1.5% sits
   mid-range in a neighbourhood (TP +1.3% to +1.9%, trend +1.0% to
   +1.2%) that is positive on both windows; it is not tuned to either
   bounce's exact top. The −2.0% washout level is load-bearing: at
   −2.2% the previous window's washout (−2.06%) is missed and that
   window goes negative (−$0.76).

## Strategy

1. **Washout (core edge).** Buy 100% of equity when the 60-min return
   is ≤ −2.0% and the latest bar closed up, or the 120-min return is
   ≤ −3.0% outright. Exit at +1.5% over the blended entry (take
   profit) or −2.0% under it (stop).
2. **Trend ride (rally insurance).** Buy 50% of equity when the
   30-min return is ≥ +1.0% with EMA(8) above EMA(21). Exit on a
   0.4% trailing stop from the peak, a −0.4% stop from the blended
   entry, or EMA(8) crossing back below EMA(21). In chop this costs
   a few dollars, which the washout trade pays for; in a strongly
   trending race window it keeps the bot invested instead of sitting
   in cash. While riding a trend, a washout trigger spends the
   remaining cash and switches the position to washout exits.
3. **Late participation.** If nothing has filled by bar 1200, the
   thresholds relax (washout −1.2% / trend +0.3%) so the bot still
   meets the ≥ 1 trade guardrail. Dormant on both backtested
   windows — it never fired there.

Risk: one position, long only, no leverage. Worst backtested drawdown
1.50% (guardrail: 25%) — the washout position is held through a drift
after its first bounce leg (equity peaks at $1,010.07 at bar 80, then
retraces to $996.21 at bar 133 before the second leg pays). A
trailing-stop washout exit was tested and rejected: it cuts the
drawdown to 0.65% but also cuts the profit by two-thirds (+$4.77 /
+$6.36), because it exits on the first leg's pullback. Net PnL is the
rank key, so the wider take-profit wins. No new entries in the final
10 bars — an order there would fill at the next open and be flattened
at the last close before any take-profit can hit.

## What was tried and dropped (honest record)

A full-size round trip costs ~26 bps and a $250–500 trade ~15–17 bps,
so a signal must clear that bar after the 1-bar fill latency. The
rows below were tested in the previous iteration on its two windows
(17 Nov dev / 13 Nov prev) and dropped there; the trailing-stop and
buy-and-hold rows were re-tested on this iteration's two windows
(18 Nov dev / 17 Nov prev):

| Idea | 17 Nov window | 13 Nov window |
| --- | --- | --- |
| Dip scalper (buy 15-min ≤ −0.3…−0.5%, TP +0.3…0.6%) | −$7…−$8, 12–16 trades | −$12…−$13, 22–28 trades |
| Momentum (5/15/30-min breakouts, TP/SL) | best −$1.22…−$2.15 | best −$3.58…−$4.47 |
| 1-min momentum scalper (25% size) | −$7.47, 36 trades | −$8.68, 40 trades |
| EMA-cross / Donchian breakout + trailing stop | −$2.15…−$2.29 | −$3.74…−$4.47 |

| Idea | Dev window (18 Nov) | Prev window (17 Nov) |
| --- | --- | --- |
| Washout trailing-stop exit (arm +0.6–1.0%, trail 0.3–0.5%) | +$3.14…+$5.22 | +$2.50…+$6.36 (worse than fixed TP) |
| Buy-and-hold (reference) | −$31.63 | +$1.07 |

The lesson of the previous race (our washout-only bot: +$11.87 dev,
4 trades, −$10.44 live, rank 354/1,292) was **not** that the washout
signal is wrong — it is the only signal that made money on both
windows — but that a bot with a single rare signal has no answer when
the race window offers no washout. This bot keeps the washout core
and adds the near-breakeven trend rider for trade count and rally
exposure. No design tested here reproduces the previous winners'
profile (30–48 trades, +6%, ~0.45% drawdown) on the known windows;
that profile needs a strongly trending window, which the trend rider
is built to catch if one appears. The race window is unseen: if it
offers no washout and no +1.0% rally, this bot will sit mostly in
cash and finish near $0 — the late-participation rule at bar 1200 is
the only backstop, and it is untested in anger.

## Backtest results (protocol replay, kit fill rules)

Fill model: orders fill at the next bar's open, 4 bps fee, 2 bps
slippage, constant-product impact vs the bar's open depth, final
flatten at the last close. Quantities/cash/cost tracked as integers,
as the real harness does (a float replay mis-states cost after a
sell and produces phantom stop-outs — found and fixed during
verification).

| Window | Net PnL | Trades | Max drawdown | Sharpe (per bar) |
| --- | --- | --- | --- | --- |
| Dev, 18 Nov kit (1440 bars, $65,083 → $63,261, −2.80%) | **+$13.99** | 2 | 1.50% | 0.02 |
| Prev dev, 17 Nov kit (1440 bars, $64,461 → $64,776, +0.49%) | **+$12.95** | 6 | 0.62% | 0.03 |

Dev-window fills (18 Nov kit): washout buy $63,646.15 → sell
$64,588.30 (TP). Per-6h-block equity on the dev window: $1,000.00 →
$1,004.13 → $1,014.13 → $1,013.99 → $1,013.99. Previous window
fills: trend buy $64,877.96 → sell $65,155.74; trend buy $65,169.23
→ sell $64,896.49; washout buy $64,202.84 → sell $65,135.62 (TP).
Previous-window blocks: +$0.00 / +$7.37 / +$5.04 / +$0.00.
Dev gate: **PASS on both windows** (PnL > $0). The old bot scored
−$1.60 on this window; this retune scores +$13.99 on it and +$12.95
on the previous window (old bot: +$9.23 there).

Neighbour robustness (trend thr +1.0–1.2%, washout TP +1.3–1.9%):
every combination positive on both windows (+$11.88…+$17.34 dev,
+$10.79…+$16.82 prev). TP +2.0% fails the previous window (+$3.85)
because that bounce topped out below it, so TP is kept at +1.5%.

## Verification

- Two protocol-replay runs on each window produce **byte-identical
  action logs** (deterministic: no clock, no network, no files, no
  randomness; all decisions are integer comparisons on closes plus
  deterministic float EMAs).
- `grade-local --driver docker` is unavailable on this machine
  (Docker not installed); `--driver process` runs Node bots only.
  The replay above is the fallback evidence, implementing the kit's
  fill rules exactly (verified: it reproduces the old bot's published
  numbers — +$9.23, 8 trades, 0.57% DD — to the cent on the previous
  window).
- Bot answers every batch with at most 1 order (cap 16),
  `max_slippage_bps` 500, never trades during warm-up, skips batches
  with no CBBTC bar.

## Files

- `main.py` — the bot (hand-written)
- `vendor/makefun_bars.py` — kit SDK shim, byte-for-byte copy
- `LICENSE` — MIT
