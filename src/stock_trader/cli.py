# src/stock_trader/cli.py
import threading
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from stock_trader.engine import Engine
from stock_trader.models import Signal, Trade


class TradingCLI:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.console = Console()
        self.signals: dict[str, Signal] = {}  # latest signal per ticker
        self._running = False

        # Register callbacks
        self.engine.on_signal = self._on_signal
        self.engine.on_trade = self._on_trade

    def _on_signal(self, signal: Signal) -> None:
        self.signals[signal.ticker] = signal

    def _on_trade(self, trade: Trade) -> None:
        pass  # Trades are tracked in engine.execution.trades

    def _build_watchlist_table(self) -> Table:
        table = Table(title="Watchlist", expand=True)
        table.add_column("Ticker", style="bold")
        table.add_column("Price", justify="right")
        table.add_column("Change", justify="right")
        table.add_column("RSI", justify="right")
        table.add_column("MACD", justify="center")
        table.add_column("Signal", justify="center")

        for ticker in self.engine.config.watchlist:
            bars = self.engine.market_data.get_bars(ticker)
            price = f"{bars[-1].close:.2f}" if bars else "---"

            # Calculate price change from previous bar
            change_str = "---"
            if bars and len(bars) >= 2:
                prev = bars[-2].close
                curr = bars[-1].close
                pct = (curr - prev) / prev * 100
                color = "green" if pct >= 0 else "red"
                change_str = f"[{color}]{pct:+.1f}%[/{color}]"

            signal = self.signals.get(ticker)
            rsi_str = "---"
            macd_str = "---"
            signal_str = "---"

            if signal:
                # Get RSI from latest analysis
                from stock_trader.analysis import compute_indicators
                indicators = compute_indicators(
                    ticker, bars, self.engine.config.analysis
                ) if bars else None

                if indicators and indicators.rsi is not None:
                    rsi_val = indicators.rsi
                    rsi_str = f"{rsi_val:.0f}"
                    if rsi_val < 30:
                        rsi_str = f"[red]{rsi_str}[/red]"
                    elif rsi_val > 70:
                        rsi_str = f"[green]{rsi_str}[/green]"

                if indicators and indicators.macd_hist is not None:
                    macd_str = "[green]▲[/green]" if indicators.macd_hist > 0 else "[red]▼[/red]"

                if signal.action == "BUY":
                    signal_str = f"[bold green]BUY ({signal.confidence:.0%})[/bold green]"
                elif signal.action == "SELL":
                    signal_str = f"[bold red]SELL ({signal.confidence:.0%})[/bold red]"
                else:
                    signal_str = "[dim]HOLD[/dim]"

            table.add_row(ticker, price, change_str, rsi_str, macd_str, signal_str)

        return table

    def _build_positions_table(self) -> Table:
        table = Table(title="Positions", expand=True)
        table.add_column("Ticker", style="bold")
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("P/L", justify="right")

        for ticker, pos in self.engine.execution.positions.items():
            bars = self.engine.market_data.get_bars(ticker)
            current = bars[-1].close if bars else pos.entry_price
            pnl = pos.unrealized_pnl(current)
            pnl_style = "green" if pnl >= 0 else "red"

            table.add_row(
                ticker,
                str(pos.quantity),
                f"{pos.entry_price:.2f}",
                f"{current:.2f}",
                f"[{pnl_style}]{pnl:+.2f}[/{pnl_style}]",
            )

        if not self.engine.execution.positions:
            table.add_row("[dim]No open positions[/dim]", "", "", "", "")

        return table

    def _build_trades_table(self) -> Table:
        table = Table(title="Trade Log", expand=True)
        table.add_column("Time")
        table.add_column("Action", justify="center")
        table.add_column("Ticker")
        table.add_column("Qty", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Reason")

        # Show last 10 trades
        for trade in self.engine.execution.trades[-10:]:
            action_style = "green" if trade.action == "BUY" else "red"
            table.add_row(
                trade.timestamp.strftime("%H:%M:%S"),
                f"[{action_style}]{trade.action}[/{action_style}]",
                trade.ticker,
                str(trade.quantity),
                f"{trade.price:.2f}",
                trade.reason[:40],
            )

        if not self.engine.execution.trades:
            table.add_row("[dim]No trades yet[/dim]", "", "", "", "", "")

        return table

    def _build_status_bar(self) -> Text:
        exec_mgr = self.engine.execution
        pnl = exec_mgr.daily_pnl
        pnl_color = "green" if pnl >= 0 else "red"
        trade_count = len(exec_mgr.trades)
        limit = self.engine.config.risk.daily_loss_limit
        limit_used = abs(min(pnl, 0) / abs(limit) * 100) if limit != 0 else 0

        status = "HALTED" if exec_mgr.is_halted else "PAUSED" if exec_mgr.is_paused else "ACTIVE"
        status_color = "red" if exec_mgr.is_halted else "yellow" if exec_mgr.is_paused else "green"
        connected = self.engine.market_data.ib.isConnected()
        conn_str = "[green]Connected[/green]" if connected else "[red]Disconnected[/red]"

        text = Text()
        text.append(f"  Daily P/L: ", style="bold")
        text.append(f"${pnl:+.2f}", style=pnl_color)
        text.append(f"  |  Trades: {trade_count}")
        text.append(f"  |  Loss limit: {limit_used:.0f}%")
        text.append(f"  |  Status: ")
        text.append(status, style=status_color)
        text.append(f"  |  IBKR: ")
        text.append_text(Text.from_markup(conn_str))
        return text

    def _build_display(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(Panel(self._build_watchlist_table()), name="watchlist", ratio=3),
            Layout(Panel(self._build_positions_table()), name="positions", ratio=2),
            Layout(Panel(self._build_trades_table()), name="trades", ratio=3),
            Layout(Panel(self._build_status_bar()), name="status", size=3),
        )
        return layout

    def _input_loop(self) -> None:
        """Handle user commands in a background thread."""
        while self._running:
            try:
                cmd = input().strip().lower()
            except EOFError:
                break

            parts = cmd.split()
            if not parts:
                continue

            command = parts[0]

            if command == "quit":
                self._running = False
                self.engine.stop()
                break
            elif command == "add" and len(parts) == 2:
                self.engine.add_ticker(parts[1].upper())
            elif command == "remove" and len(parts) == 2:
                self.engine.remove_ticker(parts[1].upper())
            elif command == "pause":
                self.engine.pause()
            elif command == "resume":
                self.engine.resume()
            elif command == "status":
                self.console.print(f"Connected: {self.engine.market_data.ib.isConnected()}")
            elif command == "trades":
                for t in self.engine.execution.trades:
                    self.console.print(
                        f"{t.timestamp:%H:%M:%S} {t.action} {t.ticker} "
                        f"{t.quantity}x @ {t.price:.2f} ({t.reason})"
                    )

    def run(self) -> None:
        self._running = True

        # Start command input in background thread
        input_thread = threading.Thread(target=self._input_loop, daemon=True)
        input_thread.start()

        with Live(self._build_display(), refresh_per_second=2, console=self.console) as live:
            while self._running:
                self.engine.sleep(0.5)
                live.update(self._build_display())
