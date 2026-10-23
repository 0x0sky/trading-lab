# © 2026 aiaiaiai · aiaiaiai.org
# SPDX-License-Identifier: MIT

"""Offline tests for Binance market data ingestion and replay compatibility."""

import json
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from trading_lab.collectors.binance import (
    normalize_ticker,
    stream_url,
    validated_symbols,
)
from trading_lab.engine import replay

RECEIVED = datetime(2026, 10, 23, 9, 7, 0, tzinfo=UTC)
FRAME = {
    "stream": "btcusdt@ticker",
    "data": {
        "e": "24hrTicker",
        "E": 1792746420000,
        "s": "BTCUSDT",
        "c": "65123.450000",
        "b": "65123.440000",
        "a": "65123.460000",
        "v": "123.45",
        "q": "8100000.12",
    },
}


def tick(frame=None):
    return normalize_ticker(
        json.dumps(FRAME if frame is None else frame),
        received_at=RECEIVED,
        symbols=("BTCUSDT", "ETHUSDT"),
    )


class BinanceTickerTests(unittest.TestCase):
    def test_default_combined_endpoint_is_market_only(self):
        url = stream_url(("BTCUSDT", "ETHUSDT"))
        self.assertEqual(
            url,
            "wss://data-stream.binance.vision/stream?"
            "streams=btcusdt@ticker/ethusdt@ticker",
        )

    def test_lowercase_symbol_normalized(self):
        self.assertEqual(validated_symbols(["btcusdt"]), ("BTCUSDT",))

    def test_invalid_symbols_cannot_change_host_or_path(self):
        with self.assertRaises(ValueError):
            stream_url(["BTCUSDT/../../wallet"])

    def test_duplicate_symbols_rejected(self):
        with self.assertRaises(ValueError):
            validated_symbols(["BTCUSDT", "btcusdt"])

    def test_event_retains_provenance_and_causal_time(self):
        event = tick()
        self.assertEqual(event["kind"], "tick")
        self.assertEqual(event["source"], "binance.spot.ticker")
        self.assertEqual(event["price"], "65123.450000")
        self.assertEqual(event["bid"], "65123.440000")
        self.assertEqual(event["ask"], "65123.460000")
        self.assertEqual(event["received_at"], RECEIVED.isoformat())
        self.assertEqual(event["raw"], FRAME["data"])
        self.assertTrue(event["exchange_event_at"].endswith("+00:00"))
        self.assertNotEqual(event["exchange_event_at"], event["received_at"])

    def test_does_not_backdate_collection_time(self):
        event = tick()
        self.assertEqual(event["received_at"], RECEIVED.isoformat())
        self.assertEqual(event["exchange_event_at"][:4], "2026")

    def test_unknown_market_rejected(self):
        frame = json.loads(json.dumps(FRAME))
        frame["data"]["s"] = "SOLUSDT"
        with self.assertRaisesRegex(ValueError, "market symbol"):
            tick(frame)

    def test_stream_symbol_mismatch_rejected(self):
        frame = json.loads(json.dumps(FRAME))
        frame["stream"] = "ethusdt@ticker"
        with self.assertRaisesRegex(ValueError, "disagree"):
            tick(frame)

    def test_nonnumeric_prices_rejected(self):
        frame = json.loads(json.dumps(FRAME))
        frame["data"]["c"] = "NaN"
        with self.assertRaisesRegex(ValueError, "finite"):
            tick(frame)

    def test_bid_must_not_exceed_ask(self):
        frame = json.loads(json.dumps(FRAME))
        frame["data"]["b"] = "999999"
        with self.assertRaisesRegex(ValueError, "bid exceeds ask"):
            tick(frame)

    def test_requires_aware_received_time(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            normalize_ticker(FRAME, received_at=datetime(2026, 10, 23), symbols=["BTCUSDT"])

    def test_rejects_forged_exchange_time(self):
        frame = json.loads(json.dumps(FRAME))
        frame["data"]["E"] = "bad"
        with self.assertRaisesRegex(ValueError, "milliseconds"):
            tick(frame)

    def test_shutdown_control_event_is_ignored(self):
        frame = {"stream": "!serverShutdown", "data": {"e": "serverShutdown"}}
        self.assertIsNone(tick(frame))

    def test_future_tick_is_compatible_with_paper_replay(self):
        signal = {
            "kind": "signal",
            "id": "signal-1",
            "source": "synthetic-channel",
            "symbol": "BTCUSDT",
            "side": "buy",
            "received_at": (RECEIVED - timedelta(seconds=1)).isoformat(),
        }
        result = replay([signal, tick()])
        self.assertEqual(len(result["fills"]), 1)
        self.assertEqual(result["fills"][0]["symbol"], "BTCUSDT")
        self.assertEqual(Decimal(result["realized_pnl"]), Decimal(0))

    def test_no_signal_cannot_open_trade(self):
        self.assertEqual(replay([tick()])["fills"], [])


if __name__ == "__main__":
    unittest.main()
