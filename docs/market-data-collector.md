# Market Data Collector v0

## Scope

An optional **read-only** Binance Spot market-data adapter. The adapter uses
the Binance market-data-only WebSocket host:
`wss://data-stream.binance.vision`.

This implementation subscribes to the `<symbol>@ticker` stream, which provides
approximately one snapshot per second per symbol, **not** every trade or full
order-book depth. The `c` field is the exchange-reported last trade price,
while `b` and `a` are the best bid and ask at that source's update.
The existing paper-broker replay still uses the last price plus configured
slippage; collecting bid/ask does **not** yet improve fill execution logic.

No API key, exchange account, trading endpoint, real order or market-core wallet
is used.

## Install and run (explicit local action)

```sh
python3.13 -m pip install -e ".[market]"
trading-lab-market --max-events 10
trading-lab-market --symbol BTCUSDT --symbol ETHUSDT --output data/ticks.jsonl
```

The output is **append-only**, UTF-8 JSONL, ignored by Git; starting the second
command opens a long-running live connection until stopped. No GitHub CI action
connects to exchanges. The first command is a bounded 10-event live capture,
not an offline smoke test.

## Output and provenance

Each record contains the existing paper replay contract (`kind=tick`,
`symbol`, `price`, `received_at`) plus the market source identifier, Binance
`exchange_event_at`, `bid`, `ask`, reported rolling 24-hour volumes,
and the unmodified decoded source event in `raw`.

`received_at` is the collector's local, UTC-aware receipt time. It is **not**
replaced with Binance's exchange event time; doing so could silently create
lookahead in later signal simulations. The adapter checks that its local clock
never moves backwards during a capture session.

This is a **collection adapter**, not a high-fidelity execution simulator.
Quotes are indicative and may be stale, delayed or lost. WebSocket reconnects
can leave gaps; the collector warns on disconnect but does not backfill.
It does not currently guarantee a gapless continuous time series, cross-run
ordering, or production-grade persistence. Until coverage, gaps and clocks
are independently assessed, do not make claims about the accuracy of returns.

## Telegram Signal Collector (next independent PR)

A separate Telegram adapter will ingest channels to which an authorized bot
or client legitimately has access, including message edits, original text,
source/channel ID, message ID, publish time and local receipt time.

Separate these layers:

1. **Raw source report**: immutable raw message and all edits/revisions.
2. **Signal candidate**: parsed symbol, direction, entry, stops/targets,
   extraction method, confidence and uncertainty.
3. **Validated signal**: deterministic eligibility rules for strategy input.
4. **Paper execution**: use a price observed *after* the signal was received.

A broad market opinion is not automatically a BUY/SELL order. A single signal
may launch multiple independent experiments with isolated balances, while a
source score is computed only from verified out-of-sample performance.

© 2026 aiaiaiai · aiaiaiai.org
