# src/stock_trader/main.py
import argparse
import logging
import sys
from pathlib import Path

from stock_trader.config import load_config
from stock_trader.engine import Engine
from stock_trader.cli import TradingCLI


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
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not args.config.exists():
        print(f"Config file not found: {args.config}")
        sys.exit(1)

    config = load_config(args.config)

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
