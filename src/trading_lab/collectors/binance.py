# © 2026 aiaiaiai · aiaiaiai.org
# SPDX-License-Identifier: MIT

"""Read-only Binance Spot ticker collector with append-only JSONL output."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

MARKET_DATA_URL = "wss://data-stream.binance.vision/stream?streams="
SYMBOL_PATTERN = re.compile(r"[A-Z0-9]{5,20}\Z")
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT")


def validated_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    """Validate the allowlisted market symbols before constructing a stream URL."""
    if not symbols or len(symbols) > 10:
        raise ValueError("specify between 1 and 10 symbols")
    normalized = tuple(symbol.upper() for symbol in symbols)
    if any(SYMBOL_PATTERN.fullmatch(symbol) is None for symbol in normalized):
        raise ValueError("symbols must contain 5-20 ASCII letters or digits")
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate market symbol")
    return normalized


def stream_url(symbols: Sequence[str]) -> str:
    validated = validated_symbols(symbols)
    names = "/".join(f"{symbol.lower()}@ticker" for symbol in validated)
    return MARKET_DATA_URL + names


def _positive_string(value: object, field: str, *, allow_zero: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a decimal string")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal string") from exc
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise ValueError(f"{field} must be finite and positive")
    return value


def _source_time(value: object) -> str:
    if type(value) is not int or value <= 0:
        raise ValueError("Binance event time must be a positive integer in milliseconds")
    try:
        timestamp = datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("Binance event time out of range") from exc
    return timestamp.isoformat(timespec="milliseconds")


def normalize_ticker(
    message: str | bytes | Mapping[str, object],
    *,
    received_at: datetime,
    symbols: Sequence[str],
) -> dict[str, object] | None:
    """Decode one ticker frame, preserving original evidence and collector time.

    Returns None for Binance's graceful serverShutdown control event.
    Does not use exchange event time as the causal received_at timestamp.
    """
    allowed = set(validated_symbols(symbols))
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("collector received_at must include a timezone")

    payload = json.loads(message) if isinstance(message, (str, bytes)) else message
    if not isinstance(payload, Mapping):
        raise ValueError("WebSocket frame must contain an object")
    data = payload.get("data")
    stream = payload.get("stream")
    if not isinstance(data, Mapping) or not isinstance(stream, str):
        raise ValueError("expected Binance combined stream envelope")
    if data.get("e") == "serverShutdown":
        return None
    if data.get("e") != "24hrTicker":
        raise ValueError("unexpected Binance event type")
    symbol = data.get("s")
    if not isinstance(symbol, str) or symbol not in allowed:
        raise ValueError("unexpected Binance market symbol")
    if stream != f"{symbol.lower()}@ticker":
        raise ValueError("Binance stream and market symbol disagree")

    price = _positive_string(data.get("c"), "last_price")
    bid = _positive_string(data.get("b"), "bid")
    ask = _positive_string(data.get("a"), "ask")
    if Decimal(bid) > Decimal(ask):
        raise ValueError("bid exceeds ask")
    volume = _positive_string(data.get("v"), "base_volume_24h", allow_zero=True)
    quote_volume = _positive_string(
        data.get("q"), "quote_volume_24h", allow_zero=True
    )

    return {
        "kind": "tick",
        "symbol": symbol,
        "price": price,
        "received_at": received_at.astimezone(UTC).isoformat(),
        "source": "binance.spot.ticker",
        "exchange_event_at": _source_time(data.get("E")),
        "bid": bid,
        "ask": ask,
        "base_volume_24h": volume,
        "quote_volume_24h": quote_volume,
        "raw": dict(data),
    }


async def collect(
    *,
    symbols: Sequence[str] = DEFAULT_SYMBOLS,
    output: Path,
    max_events: int | None = None,
) -> int:
    """Append market observations; reconnects can leave unfilled data gaps."""
    symbols = validated_symbols(symbols)
    if max_events is not None and (type(max_events) is not int or max_events <= 0):
        raise ValueError("max_events must be a positive integer")
    try:
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed
    except ImportError as exc:
        raise RuntimeError("Install market support: pip install -e '.[market]'") from exc

    output.parent.mkdir(parents=True, exist_ok=True)
    url = stream_url(symbols)
    count = 0
    previous: datetime | None = None
    with output.open("a", encoding="utf-8", buffering=1) as handle:
        async for websocket in connect(url, ping_interval=20, ping_timeout=30):
            print("Connected to read-only Binance Spot market data", file=sys.stderr)
            try:
                async for message in websocket:
                    observed = datetime.now(UTC)
                    if previous is not None and observed < previous:
                        raise RuntimeError("collector clock moved backwards")
                    tick = normalize_ticker(
                        message,
                        received_at=observed,
                        symbols=symbols,
                    )
                    if tick is None:
                        continue
                    handle.write(json.dumps(tick, separators=(",", ":")) + "\n")
                    handle.flush()
                    previous = observed
                    count += 1
                    if max_events is not None and count >= max_events:
                        return count
            except ConnectionClosed as exc:
                print(f"Market stream closed ({exc}); possible data gap", file=sys.stderr)
            finally:
                await websocket.close()
            print("Reconnecting: prior interval may contain missing ticks", file=sys.stderr)
            await asyncio.sleep(1)

    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Binance Spot data collector")
    parser.add_argument(
        "--symbol",
        action="append",
        dest="symbols",
        help="Spot pair (repeat to track up to 10); defaults BTCUSDT, ETHUSDT",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/binance-spot-tickers.jsonl"),
        help="Append-only local JSONL destination",
    )
    parser.add_argument("--max-events", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        return_code = asyncio.run(
            collect(
                symbols=args.symbols or DEFAULT_SYMBOLS,
                output=args.output,
                max_events=args.max_events,
            )
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"collector error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Collector stopped", file=sys.stderr)
        return 130
    print(f"Saved {return_code} market events to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
