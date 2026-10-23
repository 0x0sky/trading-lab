# © 2026 aiaiaiai · aiaiaiai.org
# SPDX-License-Identifier: MIT

"""Deterministic, spot-only replay with causal fill timing."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

BPS = Decimal(10000)


@dataclass(frozen=True)
class Signal:
    signal_id: str
    source: str
    symbol: str
    side: str
    received_at: datetime


@dataclass(frozen=True)
class Position:
    quantity: Decimal
    cost: Decimal


def _decimal(value: object, field: str, *, allow_zero: bool = False) -> Decimal:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be a decimal number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise ValueError(f"{field} must be finite and positive")
    return number


def _text(event: Mapping[str, object], field: str) -> str:
    value = event.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def _timestamp(event: Mapping[str, object]) -> datetime:
    raw = _text(event, "received_at")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("received_at must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("received_at must include a timezone")
    return parsed.astimezone(UTC)


def replay(
    events: Iterable[Mapping[str, object]],
    *,
    starting_cash: object = "1000",
    trade_notional: object = "100",
    fee_bps: object = "10",
    slippage_bps: object = "5",
    max_allocation: object = "0.25",
    max_delay_seconds: int = 30,
) -> dict[str, object]:
    """Replay events in collection order without future-price fills.

    Rejects invalid data instead of silently repairing an event timeline.
    Quotes are considered executable after receipt, not before.
    """
    initial = _decimal(starting_cash, "starting_cash")
    notional = _decimal(trade_notional, "trade_notional")
    fee_rate = _decimal(fee_bps, "fee_bps", allow_zero=True) / BPS
    slip_rate = _decimal(slippage_bps, "slippage_bps", allow_zero=True) / BPS
    allocation = _decimal(max_allocation, "max_allocation")
    if fee_rate >= 1 or slip_rate >= 1 or allocation > 1:
        raise ValueError("fee/slippage must be below 100%; allocation at most 1")
    if type(max_delay_seconds) is not int or max_delay_seconds < 0:
        raise ValueError("max_delay_seconds must be a nonnegative integer")

    cash = initial
    realized = Decimal(0)
    positions: dict[str, Position] = {}
    latest: dict[str, Decimal] = {}
    pending: dict[str, list[Signal]] = {}
    seen: set[tuple[str, str]] = set()
    fills: list[dict[str, str]] = []
    rejections: list[dict[str, str]] = []
    previous_time: datetime | None = None

    for index, event in enumerate(events, start=1):
        if not isinstance(event, Mapping):
            raise TypeError(f"event {index} must be an object")
        received = _timestamp(event)
        if previous_time is not None and received < previous_time:
            raise ValueError(f"event {index} is out of collection order")
        previous_time = received
        kind = _text(event, "kind")
        symbol = _text(event, "symbol").upper()
        if kind == "signal":
            source = _text(event, "source")
            signal_id = _text(event, "id")
            side = _text(event, "side").lower()
            if side not in {"buy", "sell"}:
                raise ValueError(f"unsupported side: {side}")
            key = (source, signal_id)
            if key in seen:
                raise ValueError(f"duplicate signal: {source}/{signal_id}")
            seen.add(key)
            pending.setdefault(symbol, []).append(
                Signal(signal_id, source, symbol, side, received)
            )
            continue
        if kind != "tick":
            raise ValueError(f"unsupported event kind: {kind}")

        mid = _decimal(event.get("price"), "price")
        latest[symbol] = mid
        signals = pending.pop(symbol, [])
        for signal in signals:
            if received - signal.received_at > timedelta(seconds=max_delay_seconds):
                rejections.append({"id": signal.signal_id, "reason": "stale_quote"})
                continue
            execution_price = mid * (
                1 + slip_rate if signal.side == "buy" else 1 - slip_rate
            )
            if signal.side == "buy":
                if symbol in positions:
                    rejections.append({"id": signal.signal_id, "reason": "already_open"})
                    continue
                fee = notional * fee_rate
                outlay = notional + fee
                if notional > cash * allocation or outlay > cash:
                    rejections.append({"id": signal.signal_id, "reason": "risk_limit"})
                    continue
                quantity = notional / execution_price
                cash -= outlay
                positions[symbol] = Position(quantity, outlay)
                pnl = Decimal(0)
            else:
                position = positions.pop(symbol, None)
                if position is None:
                    rejections.append({"id": signal.signal_id, "reason": "no_position"})
                    continue
                quantity = position.quantity
                gross = quantity * execution_price
                fee = gross * fee_rate
                proceeds = gross - fee
                cash += proceeds
                pnl = proceeds - position.cost
                realized += pnl

            fills.append(
                {
                    "id": signal.signal_id,
                    "source": signal.source,
                    "symbol": symbol,
                    "side": signal.side,
                    "received_at": received.isoformat(),
                    "price": str(execution_price),
                    "quantity": str(quantity),
                    "fee": str(fee),
                    "realized_pnl": str(pnl),
                }
            )

    equity = cash + sum(
        (position.quantity * latest[symbol] for symbol, position in positions.items()),
        Decimal(0),
    )
    return {
        "initial_cash": str(initial),
        "ending_cash": str(cash),
        "equity": str(equity),
        "net_pnl": str(equity - initial),
        "realized_pnl": str(realized),
        "fills": fills,
        "rejections": rejections,
        "pending_signals": sum(len(queue) for queue in pending.values()),
        "open_positions": {
            symbol: str(position.quantity) for symbol, position in positions.items()
        },
    }
