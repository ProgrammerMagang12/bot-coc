"""CLI entrypoint for coc-lab — original automation prototype (testing only)."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from coclab.config import ConfigError, load_config
from coclab.loop import RunSummary, run as run_loop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coc-lab",
        description="Automation prototype for personal testing. Observe by default; --live for real taps.",
    )
    parser.add_argument("--config", default="config.json", help="path to config.json")
    parser.add_argument(
        "--live",
        action="store_true",
        help="execute real taps (default: observe, no physical actions)",
    )
    parser.add_argument("--cycles", type=int, default=1, help="number of full cycles")
    parser.add_argument("--device", default=None, help="override device_address from config")
    return parser


def _run_loop(config, mode: str, cycles: int) -> RunSummary:
    """Thin wrapper around loop.run so tests can monkeypatch it."""
    return run_loop(config, mode, cycles)


def _setup_logging() -> None:
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(logs_dir / f"run-{stamp}.log", encoding="utf-8"),
        ],
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    if args.device:
        config.device_address = args.device
    mode = "live" if args.live else "observe"

    _setup_logging()
    try:
        summary = _run_loop(config, mode, args.cycles)
    except KeyboardInterrupt:
        print("interrupted by user", file=sys.stderr)
        return 130

    if summary.ok:
        print(f"OK: {summary.cycles_done} cycle(s) completed (mode: {mode})")
        return 0
    print(f"FAILED after {summary.cycles_done} cycle(s): {summary.reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
