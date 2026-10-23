# © 2026 aiaiaiai · aiaiaiai.org
# SPDX-License-Identifier: MIT

"""CLI for deterministic offline event replay."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

from .engine import replay


def _records(path: Path) -> Iterator[Mapping[str, object]]:
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {number}: invalid JSON") from exc
            if not isinstance(event, dict):
                raise TypeError(f"line {number}: expected a JSON object")
            yield event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="0xda-market offline trading lab")
    sub = parser.add_subparsers(dest="command", required=True)
    replay_parser = sub.add_parser("replay", help="Replay a chronological JSONL stream")
    replay_parser.add_argument("path", type=Path)
    replay_parser.add_argument("--starting-cash", default="1000")
    replay_parser.add_argument("--trade-notional", default="100")
    replay_parser.add_argument("--fee-bps", default="10")
    replay_parser.add_argument("--slippage-bps", default="5")
    replay_parser.add_argument("--max-allocation", default="0.25")
    replay_parser.add_argument("--max-delay-seconds", type=int, default=30)
    args = parser.parse_args(argv)

    try:
        result = replay(
            _records(args.path),
            starting_cash=args.starting_cash,
            trade_notional=args.trade_notional,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            max_allocation=args.max_allocation,
            max_delay_seconds=args.max_delay_seconds,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"replay error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2))
    return 0
