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
    parser.add_argument(
        "--bulk-test",
        action="store_true",
        help="Run bulk backtests comparing multiple strategies across a date range",
    )
    parser.add_argument(
        "--from",
        type=str,
        dest="from_date",
        metavar="DATE",
        help="Start date for bulk test (e.g., 2026-02-14)",
    )
    parser.add_argument(
        "--to",
        type=str,
        dest="to_date",
        metavar="DATE",
        help="End date for bulk test (e.g., 2026-03-14)",
    )
    parser.add_argument(
        "--strategies",
        type=str,
        metavar="NAMES",
        help="Comma-separated strategy names for bulk test (e.g., Conservative,Aggressive)",
    )
    parser.add_argument(
        "--broker",
        type=str,
        choices=["ibkr", "capital"],
        default="ibkr",
        help="Broker to use: 'ibkr' (Interactive Brokers) or 'capital' (Capital.com CFDs). Default: ibkr",
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
        if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("ANTHROPIC_API_KEY"):
            print("Error: AI strategy requires GEMINI_API_KEY or ANTHROPIC_API_KEY.")
            print("  Gemini (free): https://aistudio.google.com/apikey")
            print("  Claude (paid): https://console.anthropic.com/settings/keys")
            sys.exit(1)
        provider = "Gemini" if os.environ.get("GEMINI_API_KEY") else "Claude"
        print(f"AI provider: {provider}")

    config = load_config(args.config)

    if args.bulk_test:
        if not args.from_date or not args.to_date:
            print("Error: --bulk-test requires --from and --to dates")
            print("Example: stock-trader --bulk-test --from 2026-02-14 --to 2026-03-14")
            sys.exit(1)
        strategy_filter = args.strategies.split(",") if args.strategies else None
        _run_bulk_test(config, args.from_date, args.to_date, strategy_filter)
    elif args.backtest:
        if args.aggressive and args.strategy == "classic":
            config.strategy.rsi_oversold = 45
            config.strategy.rsi_overbought = 55
            config.strategy.confidence_threshold = 0.3
        _run_backtest(config, args.backtest, args.speed, args.strategy)
    elif args.broker == "capital":
        _run_capital(config, args.strategy)
    else:
        _run_live(config, args.strategy)


def _run_bulk_test(config, from_date: str, to_date: str, strategy_filter: list[str] | None = None) -> None:
    from stock_trader.bulk_backtest import run_bulk_backtest, print_results

    try:
        results = run_bulk_backtest(config, from_date, to_date, strategy_filter)
        print_results(results)
    except ConnectionRefusedError:
        print(f"\nCould not connect to IBKR at {config.ibkr.host}:{config.ibkr.port}")
        print("IBKR connection is needed to fetch historical data.")
        sys.exit(1)


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


def _run_capital(config, strategy: str) -> None:
    from stock_trader.capital_com import CapitalComClient
    from stock_trader.engine_capital import CapitalEngine
    from stock_trader.cli import TradingCLI

    api_key = os.environ.get("CAPITAL_API_KEY")
    email = os.environ.get("CAPITAL_EMAIL")
    password = os.environ.get("CAPITAL_PASSWORD")

    if not all([api_key, email, password]):
        print("Error: Capital.com requires these environment variables in .env:")
        print("  CAPITAL_API_KEY=your-api-key")
        print("  CAPITAL_EMAIL=your-email")
        print("  CAPITAL_PASSWORD=your-password")
        sys.exit(1)

    print(f"Stock Day Trader v0.1.0 — Capital.com (demo)")
    print(f"Strategy: {strategy} | Watchlist: {', '.join(config.watchlist)}")
    print()

    client = CapitalComClient(api_key=api_key, email=email, password=password, demo=True)
    engine = CapitalEngine(config, client=client, strategy=strategy)
    cli = TradingCLI(engine)

    try:
        engine.start()
        cli.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"\nError: {e}")
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
