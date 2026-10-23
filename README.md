# 0xda-market Trading Lab

An isolated research workspace for reproducible crypto-market signal evaluation and paper trading.

**Status:** offline, deterministic prototype. No Telegram access, exchange connectivity, credentials, live orders, real funds, or deployment are implemented.

## Why Python?

Python 3.13 gives the lab a practical foundation for event ingestion, research, simulation, and statistics. The core replay loop is standard-library-only so results are portable and easy to audit. Optimize or isolate hot paths only after profiling.

## Quick start

```sh
python3.13 -m pip install -e ".[dev]"
python -m trading_lab replay examples/demo.jsonl
python -m unittest discover -s tests -v
ruff check .
```

The example is **synthetic**; it is not evidence of historical returns.

## Data contract

Read a UTF-8 JSONL stream in **collection order**, using UTC-aware ISO-8601 `received_at`:

```json
{"kind":"signal","id":"post-123","source":"channel-name","symbol":"BTCUSDT","side":"buy","received_at":"2026-10-23T10:00:00+00:00"}
{"kind":"tick","symbol":"BTCUSDT","price":"65000","received_at":"2026-10-23T10:00:01+00:00"}
```

A signal executes only on the **first subsequent tick**, never at a prior price. Missing quotes remain pending; prices arriving more than 30 seconds later reject the signal. Duplicate (source, id) pairs and out-of-order event timestamps fail fast.

## v0 simulation rules

- One long spot position per symbol; `buy` opens and `sell` closes the full position.
- Fixed USDT trade notional, by default 100, and maximum 25% of remaining cash per new entry.
- Configurable fee and adverse slippage in basis points, default 10 bps and 5 bps.
- No borrowing, leverage, shorting, funding, fill depth, latency model, or liquidation.
- Realized PnL includes execution costs. Open-position equity uses the most recent observed mid quote and **does not** include future closing costs.
- This is research infrastructure, not investment advice or a predictive model.

## Architecture boundary

```text
future read-only Telegram / exchange adapters
                |
         immutable event log
                |
        replay + paper broker
                |
       research / risk metrics
                |
      future bot / web dashboard
```

Adapters must never be allowed to place real orders in this repository's research runtime. Raw source events, timestamp provenance, and replay configuration will be persisted before any production-grade performance claims.

## Live market collection (opt-in, read-only)

The optional [Binance Spot market data collector](docs/market-data-collector.md)
subscribes to BTC/USDT and ETH/USDT public ticker streams, appending source-
attributed observations to local JSONL. It never authenticates or places orders.

```sh
python3.13 -m pip install -e ".[market]"
trading-lab-market --max-events 10
```

Use `--symbol BTCUSDT --symbol ETHUSDT` to choose explicit pairs. The process
connects to live public market data **only when launched locally**. Ticker
snapshots are not guaranteed fills, nor historical tick-by-tick records.

## Next milestones

1. Store immutable, source-attributed Telegram signals and collected market ticks in PostgreSQL with collector/clock metadata and gap tracking.
2. Implement controlled, read-only Telegram and exchange adapters, plus backfill with explicit historical-data limitations.
3. Compare multiple isolated strategies with walk-forward evaluation, portfolio drawdown, benchmark returns, execution costs, and sensitivity analysis.

This package does not depend on `0xda-market/core` or access market payments, orders, and credentials.

© 2026 aiaiaiai · aiaiaiai.org
