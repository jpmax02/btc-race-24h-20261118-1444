"""cbBTC 24h race bot — washout + trend ride, retuned for the 18 Nov window
(Python 3.13, stdlib only).

This is the second iteration of the "Washout + Trend Ride" design. The
previous iteration FAILED the dev gate on this kit's window (-$1.60, 2
trades): its washout never fired, because it waited for 121 bars of
history before trading at all, and this window's only washout-grade drop
(-2.31% over 60 minutes, bars 65-70) happened before bar 121. Two changes
fix that, and both were validated on TWO different 24h windows:

1. TRADE EARLIER. The 60-minute washout leg and the trend leg only need
   61 and 31 bars of history, so they arm at bar 61 instead of bar 121
   (the 120-minute leg still needs 121 bars). On this window that catches
   the early drop: buy filled at $63,646.15, sold at +1.5% for +$11.88
   net. On the previous window it also arms one extra early trend trade
   (bar 107, -$2.18) — which change 2 removes.
2. STRONGER TREND FILTER. The trend leg now needs a 30-minute return of
   >= +1.0% (was +0.8%) with EMA(8) above EMA(21). The +0.8% level fired
   on a slow grind that faded (this window, bars 400-412: -$1.60) and on
   a weak early rally (previous window, bar 107: -$2.18). At +1.0% both
   losing rides disappear and only the strong rally (previous window,
   bars 509-537, 30-minute returns up to +2.22%) still rides.
3. WIDER WASHOUT TAKE-PROFIT. TP is +1.5% over the blended entry (was
   +1.2%). On this window the first bounce leg topped at +1.01% and the
   second leg at +1.43% over entry, so +1.2% exits on the second leg
   anyway; +1.5% waits for the later, higher leg (the window's block 2
   topped +2.39% over entry) and earns +$13.99 instead of +$11.88. On
   the previous window the washout bounce topped at +1.97%, so +1.5%
   clears it with margin while +2.0% would NOT have (it topped below
   +2.0% and that variant collapses to +$3.85 there) — +1.5% sits
   mid-range in a neighbourhood (TP +1.3% to +1.9%) that is positive on
   both windows; it is not tuned to either bounce's exact top.

Signals (each earned its place in backtest on both windows; dip-scalping,
1-minute momentum scalping, RSI/Bollinger mean reversion and plain
EMA-cross entries were all tested and dropped because they lost money
net of the ~15-26 bps round-trip cost on both windows):

1. WASHOUT (the core edge): 60-min return <= -2.0% with the latest bar
   closing up, or 120-min return <= -3.0% outright. Buy 100% of equity.
   Exit at +1.5% over the blended entry (take profit) or -2.0% under it
   (stop). The -2.0% level is load-bearing: at -2.2% the previous
   window's washout (-2.06%) is missed and that window goes negative.
2. TREND RIDE: 30-min return >= +1.0% with EMA(8) above EMA(21).
   Buy 50% of equity. Exit on a 0.4% trailing stop from the peak, a
   -0.4% stop from the blended entry, or EMA(8) crossing back below
   EMA(21). This is the rally insurance: in a strongly trending race
   window it keeps the bot invested; in chop it costs a few dollars,
   which the washout trade pays for.
3. SCALE-IN: while riding a trend (50% invested), a washout trigger
   spends the remaining cash and switches the position to washout exits.
4. LATE PARTICIPATION: if nothing has filled by bar 1200, thresholds
   relax (washout -1.2% / trend +0.3%) so the bot still meets the >= 1
   trade guardrail. Dormant on both backtested windows.

Risk: one position, long only, no leverage. Worst backtested drawdown
1.50% (vs the 25% guardrail) — the washout position is held through a
drift after its first bounce leg, peaking at +1.01% then retracing to
-0.38% before the second leg pays. A trailing-stop exit was tested and
rejected: it cuts the drawdown to 0.65% but also cuts the profit by
two-thirds (+$4.77 / +$6.36), because it exits on the first leg's
pullback. Net PnL is the rank key, so the wider take-profit wins.
No wall clock, no network, no files, no randomness — every decision is
a pure function of the bars seen, so two runs produce byte-identical
action logs.

Protocol: agent-fun/bars-replay/v1, spoken through the kit SDK shim
vendored under vendor/ (byte-for-byte copy of the kit's makefun_bars.py).
Orders decided on bar t fill at bar t+1's open; max_slippage_bps 500.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- washout parameters (integer per-mille comparisons) ---
WASH_R60_NUM = 980      # 60-min return <= -2.0%: close * 1000 <= close60 * 980
WASH_R120_NUM = 970     # 120-min return <= -3.0%: close * 1000 <= close120 * 970
WASH_TP_NUM = 1015      # take profit +1.5%: close * 1000 >= entry * 1015
WASH_TP_DEN = 1000
WASH_SL_NUM = 98        # stop -2.0%: close * 100 <= entry * 98
WASH_LATE_R60_NUM = 988  # late (no fills by bar 1200): -1.2% over 60 min

# --- trend parameters ---
TREND_R30_NUM = 1010    # 30-min return >= +1.0%
TREND_LATE_R30_NUM = 1003  # late: +0.3%
TREND_SIZE_NUM = 1      # buy 50% of equity
TREND_SIZE_DEN = 2
TREND_SL_NUM = 996      # stop -0.4% from blended entry
TREND_TRAIL_NUM = 996   # trailing stop 0.4% below the peak

LATE_BAR = 1200
HISTORY = 200
# The 60-minute washout leg needs 61 closes and the trend leg 31, so
# they arm at bar 61; the 120-minute leg needs 121 closes. Waiting for
# 121 bars for everything cost the previous bot this window's only
# washout (bars 65-70), so the legs arm as soon as each has its data.
MIN_BARS_60 = 61
MIN_BARS_120 = 121
# No NEW entries in the final minutes: an order decided on the last
# batches fills at the next open and is flattened at the last close
# before any take-profit can realistically hit, so it only pays fees.
# Exits stay allowed. The window is 1,440 bars; the cutoff costs
# nothing on either backtested window (latest entry there: bar 1313
# on the previous window, bar 408 on this one).
NO_ENTRY_AFTER_BAR = 1430


class Bot:
    def __init__(self):
        self.closes = []       # closes as ints (price units, 1e-5 USDC)
        self.ema8 = None       # float EMAs on closes; deterministic
        self.ema21 = None
        self.peak = None       # int peak close while holding
        self.mode = None       # "wash" | "trend" | None
        self.fills = 0         # filled orders seen so far
        self.batches = 0       # batches answered

    def entry_price(self, state):
        """Blended entry price (price units) from cost/qty, or None.

        The harness keeps cost and qty as integers and resets cost when
        the position empties, so cost/qty is the exact volume-weighted
        fill price of the current position (a hair above it, because
        cost counts the buy notional including the 4 bps fee). Do not
        substitute a float reconstruction of the fills: float qty
        dust (a few 1e-9 BTC) makes a locally replayed cost look stale
        and produces phantom stop-outs. The bot never tracks fills
        itself; it trusts the account the batch carries.
        """
        holding = state.positions.get(SYMBOL)
        if holding is None or holding.qty <= 0:
            return None
        # value = qty * price * 10^quote_scale / 10^(qty_scale+price_scale)
        # price = cost * 10^(qty+price-quote) / qty = cost * 10^7 / qty
        return holding.cost * 10 ** 7 // holding.qty

    def on_batch(self, state, batch):
        self.batches += 1
        for fill in batch.get("fills", []):
            if fill.get("status") == "filled":
                self.fills += 1
        if state.warming_up:
            return []
        bar = None
        for b in batch.get("bars", []):
            if b.get("symbol") == SYMBOL:
                bar = b
                break
        if bar is None:
            return []  # no new bar for our symbol this minute
        close = int(bar["c"])
        self.closes.append(close)
        if len(self.closes) > HISTORY:
            del self.closes[0]
        k8 = 2.0 / 9.0
        k21 = 2.0 / 22.0
        self.ema8 = float(close) if self.ema8 is None else close * k8 + self.ema8 * (1.0 - k8)
        self.ema21 = float(close) if self.ema21 is None else close * k21 + self.ema21 * (1.0 - k21)

        n = len(self.closes)
        if n < MIN_BARS_60:
            return []
        holding = state.positions.get(SYMBOL)
        qty = holding.qty if holding is not None else 0
        late = self.fills == 0 and self.batches >= LATE_BAR

        r60_num = WASH_LATE_R60_NUM if late else WASH_R60_NUM
        washout = (close * 1000 <= self.closes[-61] * r60_num
                   and close > self.closes[-2])
        if n >= MIN_BARS_120:
            washout = washout or \
                (close * 1000 <= self.closes[-121] * WASH_R120_NUM)
        trend_thr = TREND_LATE_R30_NUM if late else TREND_R30_NUM
        trend = close * 1000 >= self.closes[-31] * trend_thr and self.ema8 > self.ema21

        if qty > 0:
            entry = self.entry_price(state)
            if entry is None:
                return []
            if self.peak is None:
                self.peak = close
            elif close > self.peak:
                self.peak = close
            if self.mode == "wash":
                if close * WASH_TP_DEN >= entry * WASH_TP_NUM:
                    return self._sell_all(state)
                if close * 100 <= entry * WASH_SL_NUM:
                    return self._sell_all(state)
                return []
            # trend mode: washout scale-in takes over first (not in the
            # final minutes — a scale-in there is a new entry too)
            if washout and self.batches < NO_ENTRY_AFTER_BAR \
                    and state.cash >= 1_000_000:
                self.mode = "wash"
                self.peak = close
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": state.cash,
                         "max_slippage_bps": 500}]
            if close * 1000 <= entry * TREND_SL_NUM:
                return self._sell_all(state)
            if close * 1000 <= self.peak * TREND_TRAIL_NUM:
                return self._sell_all(state)
            if self.ema8 < self.ema21:
                return self._sell_all(state)
            return []

        # flat: no new entries in the final minutes (see NO_ENTRY_AFTER_BAR)
        self.peak = None
        self.mode = None
        if self.batches >= NO_ENTRY_AFTER_BAR:
            return []
        if washout:
            self.mode = "wash"
            notional = state.cash
            if notional >= 1_000_000:
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": notional,
                         "max_slippage_bps": 500}]
            return []
        if trend:
            self.mode = "trend"
            notional = state.equity * TREND_SIZE_NUM // TREND_SIZE_DEN
            notional = min(notional, state.cash)
            if notional >= 1_000_000:
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": notional,
                         "max_slippage_bps": 500}]
            return []
        return []

    def _sell_all(self, state):
        # Do NOT clear mode/peak here: the sell may be rejected, and the
        # position then keeps its exit rules. Mode/peak are cleared when
        # the position is actually gone (the flat branch above).
        holding = state.positions.get(SYMBOL)
        if holding is None or holding.qty <= 0:
            return []
        return [{"side": "sell", "symbol": SYMBOL,
                 "qty": holding.qty, "max_slippage_bps": 500}]


def main():
    bot = Bot()
    makefun_bars.run(bot.on_batch)


if __name__ == "__main__":
    main()
