# © 2026 aiaiaiai · aiaiaiai.org
# SPDX-License-Identifier: MIT

"""Causal replay and paper-broker regression tests."""

import unittest
from decimal import Decimal

from trading_lab.engine import replay


def signal(signal_id, time, side="buy", symbol="BTCUSDT", source="channel"):
    return {
        "kind": "signal",
        "id": signal_id,
        "source": source,
        "symbol": symbol,
        "side": side,
        "received_at": time,
    }


def tick(time, price="100", symbol="BTCUSDT"):
    return {"kind": "tick", "symbol": symbol, "price": price, "received_at": time}


T0 = "2026-10-23T10:00:00+00:00"
T1 = "2026-10-23T10:00:01+00:00"
T2 = "2026-10-23T10:00:02+00:00"


class ReplayTests(unittest.TestCase):
    def test_round_trip_realized_pnl(self):
        result = replay(
            [signal("a", T0), tick(T1), signal("b", T1, "sell"), tick(T2, "110")],
            fee_bps="0",
            slippage_bps="0",
        )
        self.assertEqual(Decimal(result["net_pnl"]), Decimal(10))
        self.assertEqual(Decimal(result["realized_pnl"]), Decimal(10))
        self.assertEqual(len(result["fills"]), 2)
        self.assertEqual(result["open_positions"], {})

    def test_no_lookahead_fill(self):
        result = replay([tick(T0), signal("a", T1)])
        self.assertEqual(result["fills"], [])
        self.assertEqual(result["pending_signals"], 1)

    def test_stale_quote_rejected(self):
        result = replay(
            [signal("a", T0), tick("2026-10-23T10:00:31+00:00")]
        )
        self.assertEqual(result["fills"], [])
        self.assertEqual(result["rejections"][0]["reason"], "stale_quote")

    def test_duplicate_source_message_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate signal"):
            replay([signal("a", T0), signal("a", T1)])

    def test_same_id_other_source_is_allowed(self):
        result = replay(
            [signal("a", T0), signal("a", T1, source="other"), tick(T2)]
        )
        self.assertEqual(len(result["fills"]), 1)
        self.assertEqual(result["rejections"][0]["reason"], "already_open")

    def test_sell_without_position_cannot_short(self):
        result = replay([signal("a", T0, "sell"), tick(T1)])
        self.assertEqual(result["fills"], [])
        self.assertEqual(result["rejections"][0]["reason"], "no_position")

    def test_trade_notional_limited(self):
        result = replay(
            [signal("a", T0), tick(T1)], starting_cash="100", trade_notional="100"
        )
        self.assertEqual(result["rejections"][0]["reason"], "risk_limit")

    def test_no_backwards_timestamps(self):
        with self.assertRaisesRegex(ValueError, "out of collection order"):
            replay([tick(T2), signal("a", T1)])

    def test_timezone_required(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            replay([signal("a", "2026-10-23T10:00:00")])

    def test_non_finite_prices_fail(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            replay([tick(T0, "NaN")])

    def test_fee_and_slippage_reduce_profit(self):
        events = [signal("a", T0), tick(T1), signal("b", T1, "sell"), tick(T2, "110")]
        without_cost = replay(events, fee_bps="0", slippage_bps="0")
        with_cost = replay(events, fee_bps="10", slippage_bps="5")
        self.assertLess(
            Decimal(with_cost["net_pnl"]), Decimal(without_cost["net_pnl"])
        )

    def test_invalid_fee_configuration(self):
        with self.assertRaises(ValueError):
            replay([], fee_bps="-1")


if __name__ == "__main__":
    unittest.main()
