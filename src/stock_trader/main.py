import argparse
import logging
import sys
from pathlib import Path

from stock_trader.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Day Trader")
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--backtest",
        type=str,
        metavar="DATE",
        help="Run backtest for a date (e.g., 2026-03-14). Requires IBKR connection to fetch data.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0.1,
        help="Backtest replay speed in seconds per bar (default: 0.1)",
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="Use looser strategy thresholds (RSI<45 buy, RSI>55 sell) to see more trades in backtest",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.config.exists():
        print(f"Config file not found: {args.config}")
        sys.exit(1)

    config = load_config(args.config)

    if args.backtest:
        if args.aggressive:
            config.strategy.rsi_oversold = 45
            config.strategy.rsi_overbought = 55
            config.strategy.confidence_threshold = 0.3
        _run_backtest(config, args.backtest, args.speed, aggressive=args.aggressive)
    else:
        _run_live(config)


def _run_backtest(config, date: str, speed: float, aggressive: bool = False) -> None:
    from stock_trader.backtest import BacktestEngine
    from stock_trader.cli import TradingCLI

    mode = "AGGRESSIVE" if aggressive else "NORMAL"
    print(f"Stock Day Trader v0.1.0 — BACKTEST MODE ({mode})")
    print(f"Replaying {date} | Speed: {speed}s/bar")
    print(f"Watchlist: {', '.join(config.watchlist)}")
    print()

    engine = BacktestEngine(config, date=date, speed=speed)
    cli = TradingCLI(engine)

    try:
        engine.start()
        cli.run()
    except KeyboardInterrupt:
        print("\nBacktest stopped.")
    except ConnectionRefusedError:
        print(f"\nCould not connect to IBKR at {config.ibkr.host}:{config.ibkr.port}")
        print("IBKR connection is needed to fetch historical data for backtest.")
        sys.exit(1)
    finally:
        engine.stop()


def _run_live(config) -> None:
    from stock_trader.engine import Engine
    from stock_trader.cli import TradingCLI

    print(f"Stock Day Trader v0.1.0")
    print(f"Connecting to IBKR at {config.ibkr.host}:{config.ibkr.port} (paper trading)")
    print(f"Watchlist: {', '.join(config.watchlist)}")
    print()

    engine = Engine(config)
    cli = TradingCLI(engine)

    try:
        engine.start()
        cli.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except ConnectionRefusedError:
        print(f"\nCould not connect to IBKR at {config.ibkr.host}:{config.ibkr.port}")
        print("Make sure TWS or IB Gateway is running with API connections enabled.")
        sys.exit(1)
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
