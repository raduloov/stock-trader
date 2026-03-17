"""
Temporary test: buy S&P 500 CFD, wait 10 seconds, sell it.
Usage: python -m stock_trader.test_trade
"""
import os
import sys
import time
from pathlib import Path


def _load_env() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def main():
    _load_env()

    from stock_trader.capital_com import CapitalComClient

    client = CapitalComClient(
        api_key=os.environ["CAPITAL_API_KEY"],
        email=os.environ["CAPITAL_EMAIL"],
        password=os.environ["CAPITAL_PASSWORD"],
        demo=True,
    )

    print("Connecting to Capital.com demo...")
    client.connect()

    # Get account balance
    accounts = client.get_accounts()
    for acc in accounts:
        print(f"  Account: {acc.get('accountId')} | Balance: {acc.get('balance', {}).get('balance')} {acc.get('currency')}")

    # Get current S&P 500 price
    prices = client.get_prices("US500", resolution="MINUTE", max_bars=1)
    if prices:
        price = prices[0]["closePrice"]["bid"]
        print(f"\nUS500 (S&P 500) current price: {price}")

    # Open BUY position — minimum size (1 contract)
    print("\n--- BUYING US500 (1 contract) ---")
    try:
        result = client.open_position(epic="US500", direction="BUY", size=1)
        deal_ref = result.get("dealReference", "unknown")
        print(f"  Deal reference: {deal_ref}")

        # Confirm the deal
        time.sleep(1)
        confirm = client.confirm_deal(deal_ref)
        deal_id = confirm.get("dealId")
        deal_status = confirm.get("dealStatus")
        print(f"  Deal ID: {deal_id}")
        print(f"  Status: {deal_status}")
        print(f"  Direction: {confirm.get('direction')}")
        print(f"  Size: {confirm.get('size')}")
        print(f"  Level: {confirm.get('level')}")

        if deal_status != "ACCEPTED":
            print(f"  Reason: {confirm.get('reason')}")
            client.disconnect()
            return

        # Show open positions
        positions = client.get_positions()
        print(f"\n  Open positions: {len(positions)}")
        for pos in positions:
            p = pos.get("position", {})
            m = pos.get("market", {})
            print(f"    {m.get('instrumentName')}: {p.get('direction')} {p.get('size')} @ {p.get('level')}")

        # Wait 10 seconds
        print("\n  Waiting 10 seconds...")
        for i in range(10, 0, -1):
            print(f"    {i}...", end=" ", flush=True)
            time.sleep(1)
        print()

        # Get updated price
        prices2 = client.get_prices("US500", resolution="MINUTE", max_bars=1)
        if prices2:
            new_price = prices2[0]["closePrice"]["bid"]
            pnl = new_price - price
            print(f"\n  Price now: {new_price} (change: {pnl:+.2f})")

        # Get the actual position deal ID from the positions list
        positions_before_close = client.get_positions()
        actual_deal_id = None
        for pos in positions_before_close:
            p = pos.get("position", {})
            if p.get("dealId"):
                actual_deal_id = p["dealId"]
                print(f"\n  Position dealId from list: {actual_deal_id}")
                break

        close_id = actual_deal_id or deal_id
        print(f"  Using dealId for close: {close_id}")

        # Close the position
        print("\n--- CLOSING POSITION ---")
        close_result = client.close_position(close_id)
        close_ref = close_result.get("dealReference", "unknown")
        print(f"  Close reference: {close_ref}")

        time.sleep(1)
        close_confirm = client.confirm_deal(close_ref)
        print(f"  Close status: {close_confirm.get('dealStatus')}")
        print(f"  Close level: {close_confirm.get('level')}")

        # Final positions
        final_positions = client.get_positions()
        print(f"\n  Open positions after close: {len(final_positions)}")

    except Exception as e:
        print(f"  Error: {e}")

    # Final account balance
    accounts = client.get_accounts()
    for acc in accounts:
        print(f"\n  Final balance: {acc.get('balance', {}).get('balance')} {acc.get('currency')}")

    client.disconnect()
    print("\nDone!")


if __name__ == "__main__":
    main()
