"""V-bounce swing bot for cbBTC (CBBTC/USDC) on the bars-replay/v1 harness.

Strategy, in plain terms: one-minute BTC prices are noisy, and a full-size
round trip costs about 26 bps in fees, slippage and pool impact, so chasing
every wiggle loses money. This bot waits for a genuine V-shaped bounce
instead: it buys only when the close sits at least 1.50% below the highest
close of the last 480 bars (8 hours) AND has already bounced at least 0.20%
off the lowest close of the last 60 bars AND sits at or above its 10-bar
exponential moving average, i.e. the fall has stopped and the price is
turning up. It spends all of its cash on that one entry. It sells the whole
position when its marked value reaches 1.50% above its blended cost (fees
included) or falls 1.00% below it, or when 600 bars (10 hours) pass without
either exit, then waits 30 bars before it may buy again, so it cannot
re-buy straight into the same falling dip it just stopped out of.

A late-window fallback covers a window that never offers a 1.50% dip at
all: if no trade has happened by bar 1080 and the trend is clearly up (the
10-bar EMA above the 40-bar EMA above the 120-bar EMA, price within 0.30%
of its 8-hour high), it buys once with a tighter 1.00% take-profit and
0.80% stop-loss. On the two published dev windows this fallback never
fires; it exists only so a smooth uptrend window is not a guaranteed zero.

Everything is integer arithmetic on the raw price units the harness sends
(price_scale 5), so two runs on the same bars produce the same orders byte
for byte. The bot reads no clock, no environment and no network; the only
inputs are the hello message, each batch of bars, and the account the
harness reports. It trades one symbol, CBBTC, long only, and never holds
more than one open position.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# The reference high is the highest close of the last 480 bars (8 hours),
# the bounce low the lowest close of the last 60 bars (1 hour).
HIGH_BARS = 480
LOW_BARS = 60
# No signal is taken until 120 closes have been seen, so the EMAs and the
# rolling low are real.
MIN_HISTORY = 120

# Entry: 1.50% below the 480-bar high, bounced 0.20% off the 60-bar low,
# close at or above the 10-bar EMA. Full cash, one order.
DIP_BPS = 150
BOUNCE_BPS = 20

# Exit when the position is worth 1.50% over its blended cost, or 1.00%
# under it.
EXIT_UP_BPS = 150
EXIT_DOWN_BPS = 100

# Bars to wait after a sell before a new entry may be taken.
COOLDOWN_BARS = 30

# A position that has not reached either exit for 10 hours (600 bars) is
# sold at the next bar, so stale capital is freed for the next dip. The
# entry bar is read off the account, not off the order that was sent, so a
# rejected buy cannot start the clock.
MAX_HOLD_BARS = 600

# Late-window fallback: first entry only from bar 1080, clear uptrend,
# price within 0.30% of its 8-hour high, tighter exits.
LATE_BAR = 1080
LATE_NEAR_HIGH_BPS = 30
LATE_UP_BPS = 100
LATE_DOWN_BPS = 80
LATE_MAX_HOLD_BARS = 300

# 1% past the close the order was decided on: a fill further away is
# refused rather than chased, and the bot simply retries on the next bar.
MAX_SLIPPAGE_BPS = 100

BPS = 10_000

# Rolling closes (raw price units), oldest first, at most HIGH_BARS long.
closes = []
# Exponential moving averages of the closes, integer fixed point.
ema10 = None
ema40 = None
ema120 = None
# Bars remaining in the post-exit cooldown; 0 means entries are allowed.
cooldown = 0
# Seq of the batch on which the current position first appeared, or None.
entry_seq = None
# "base" or "late": which entry rule opened the current position.
entry_mode = None
# Which rule the outstanding buy order (if any) was sent under.
pending_mode = None
# True once any position has ever been held in this run.
ever_traded = False


def _ema_update(prev, close, n):
    """One EMA step in integers: prev + (close - prev) * 2 / (n + 1)."""
    if prev is None:
        return close
    return prev + (close - prev) * 2 // (n + 1)


def on_batch(state, batch):
    global cooldown, entry_seq, entry_mode, pending_mode, ever_traded
    global ema10, ema40, ema120
    for bar in batch["bars"]:
        if bar["symbol"] == SYMBOL:
            c = int(bar["c"])
            closes.append(c)
            if len(closes) > HIGH_BARS:
                del closes[: len(closes) - HIGH_BARS]
            ema10 = _ema_update(ema10, c, 10)
            ema40 = _ema_update(ema40, c, 40)
            ema120 = _ema_update(ema120, c, 120)
    if cooldown > 0:
        cooldown -= 1
    if state.warming_up:
        return []
    close = state.close(SYMBOL)
    if close is None or len(closes) < MIN_HISTORY:
        return []
    high = max(closes)
    low60 = min(closes[-LOW_BARS:])
    held = state.positions.get(SYMBOL)

    if held is None:
        entry_seq = None
        entry_mode = None
        if cooldown > 0:
            return []
        # Base entry: deep dip, confirmed bounce, fast average turning up.
        dip = close * BPS <= high * (BPS - DIP_BPS)
        bounce = close * BPS >= low60 * (BPS + BOUNCE_BPS)
        fast_up = ema10 is not None and close >= ema10
        if dip and bounce and fast_up:
            pending_mode = "base"
            return [{
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": state.cash,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        # Late-window fallback: no trade yet, clear uptrend near the high.
        if (not ever_traded and state.seq >= LATE_BAR
                and ema10 is not None and ema40 is not None and ema120 is not None
                and ema10 > ema40 > ema120
                and close * BPS >= high * (BPS - LATE_NEAR_HIGH_BPS)):
            pending_mode = "late"
            return [{
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": state.cash,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        return []

    # Holding: remember the entry so the clock and the exit rule are stable.
    if entry_seq is None:
        entry_seq = state.seq
        ever_traded = True
        entry_mode = pending_mode if pending_mode is not None else "base"
        pending_mode = None
    value = state.value(SYMBOL, held.qty)
    cost = held.cost
    if entry_mode == "late":
        up_bps = LATE_UP_BPS
        down_bps = LATE_DOWN_BPS
        max_hold = LATE_MAX_HOLD_BARS
    else:
        up_bps = EXIT_UP_BPS
        down_bps = EXIT_DOWN_BPS
        max_hold = MAX_HOLD_BARS
    stale = state.seq - entry_seq >= max_hold
    if cost > 0:
        if (value * BPS >= cost * (BPS + up_bps)
                or value * BPS <= cost * (BPS - down_bps)
                or stale):
            cooldown = COOLDOWN_BARS
            entry_seq = None
            entry_mode = None
            return [{
                "side": "sell",
                "symbol": SYMBOL,
                "qty": held.qty,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
    return []


makefun_bars.run(on_batch)
