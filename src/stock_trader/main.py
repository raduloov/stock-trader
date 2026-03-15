import argparse
import logging
import os
import sys
from pathlib import Path

from stock_trader.config import load_config


def _load_env() -> None:
    """Load environment variables from .env file if it exists."""
    env_path = Path(".env")
    if not env_path.exists():
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    _load_env()
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
    parser.add_argument(
        "--strategy",
        type=str,
        choices=["classic", "ai"],
        default="classic",
        help="Strategy to use: 'classic' (indicator rules) or 'ai' (Claude-powered). Default: classic",
    )
    args = parser.parse_args()

    # Log to file so screen=True doesn't hide errors
    log_handlers = [logging.FileHandler("stock-trader.log", mode="w")]
    if args.verbose:
        log_handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=log_handlers,
    )

    if not args.config.exists():
        print(f"Config file not found: {args.config}")
        sys.exit(1)

    if args.strategy == "ai":
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Error: ANTHROPIC_API_KEY environment variable is required for AI strategy.")
            print("Set it with: export ANTHROPIC_API_KEY=your-key-here")
            sys.exit(1)

    config = load_config(args.config)

    if args.backtest:
        if args.aggressive and args.strategy == "classic":
            config.strategy.rsi_oversold = 45
            config.strategy.rsi_overbought = 55
            config.strategy.confidence_threshold = 0.3
        _run_backtest(config, args.backtest, args.speed, args.strategy)
    else:
        _run_live(config, args.strategy)


def _run_backtest(config, date: str, speed: float, strategy: str) -> None:
    from stock_trader.backtest import BacktestEngine
    from stock_trader.cli import TradingCLI

    print(f"Stock Day Trader v0.1.0 — BACKTEST MODE")
    print(f"Replaying {date} | Speed: {speed}s/bar | Strategy: {strategy}")
    print(f"Watchlist: {', '.join(config.watchlist)}")
    print()

    engine = BacktestEngine(config, date=date, speed=speed, strategy=strategy)
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


def _run_live(config, strategy: str) -> None:
    from stock_trader.engine import Engine
    from stock_trader.cli import TradingCLI

    print(f"Stock Day Trader v0.1.0")
    print(f"Connecting to IBKR at {config.ibkr.host}:{config.ibkr.port} (paper trading)")
    print(f"Strategy: {strategy} | Watchlist: {', '.join(config.watchlist)}")
    print()

    engine = Engine(config, strategy=strategy)
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
