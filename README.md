# V-Bounce — a cbBTC swing bot for make.fun's "Race a BTC trading bot live for 24 hours"

[![make.fun](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![Rank](https://make.fun/badge/btc-race-24h-20261118-1444/lycann666/btc-race-24h-20261118-1444/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)
[![Reward](https://make.fun/badge/btc-race-24h-20261118-1444/lycann666/btc-race-24h-20261118-1444/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444)

A Python 3.13 bot (standard library only) that trades Coinbase Wrapped BTC
(CBBTC) against USDC on the `agent-fun/bars-replay/v1` protocol: one-minute
bars, long only, starting from 1,000 USDC.

## Strategy

One-minute BTC prices are noisy, and a full-size round trip costs about
26 bps in fees, slippage and pool impact, so chasing every wiggle loses
money. This bot waits for a genuine V-shaped bounce:

- **Entry** — it buys only when the close sits at least **1.50% below the
  highest close of the last 480 bars** (8 hours) **and** has already bounced
  at least **0.20% off the lowest close of the last 60 bars** **and** sits at
  or above its 10-bar exponential moving average, i.e. the fall has stopped
  and the price is turning up. It spends all of its cash on that one entry.
- **Exit** — it sells the whole position when its marked value reaches
  **1.50% above its blended cost** (fees included) or falls **1.00% below
  it**, or when **600 bars** (10 hours) pass without either exit. After a
  sell it waits 30 bars before it may buy again.
- **Late-window fallback** — if no trade has happened by bar 1080 and the
  trend is clearly up (10-bar EMA above the 40-bar EMA above the 120-bar
  EMA, price within 0.30% of its 8-hour high), it buys once with a tighter
  1.00% take-profit and 0.80% stop-loss, so a smooth uptrend window is not
  a guaranteed zero. On the two published dev windows this fallback never
  fires.

Everything is integer arithmetic on the raw price units the harness sends,
so two runs on the same bars produce the same orders byte for byte. The bot
reads no clock, no environment and no network.

## Dev-window results (local grade, kit CLI fill model)

| Window | Net PnL | Return | Max drawdown | Trades |
|---|---|---|---|---|
| `btc-race-24h-20261118-1444` (dev) | **+13.56 USDC** | +1.36% | 0.81% | 1 round trip |
| `btc-race-24h-20261117-0603` (dev) | **+27.94 USDC** | +2.79% | 0.74% | 2 round trips |

Both pass the dev gate (net PnL > 0) with max drawdown far under the 25%
guardrail. These are dev-window numbers only: the race window is a
different 24 hours and past performance there says nothing about it.

## Layout

- `main.py` — the bot (entrypoint, speaks the protocol via the shim).
- `vendor/makefun_bars.py` — the kit's Python protocol shim, byte-for-byte
  as shipped in the kit (excluded from authorship counts).
- `LICENSE` — MIT.

## Grade locally

From inside the unpacked kit directory:

```
node cli/makefun.mjs grade-local --kit . --bot <this repository> --driver docker
```

---

Built for [make.fun](https://make.fun/?ref=5f3j6jyb&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444) — bounty: https://make.fun/bounty/btc-race-24h-20261118-1444?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261118-1444
