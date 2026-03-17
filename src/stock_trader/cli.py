import sys
import tty
import termios
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
        self.signals: dict[str, Signal] = {}
        self._running = False
        self._input_mode = False
        self._input_buffer = ""
        self._input_prompt = ""
        self._status_message = ""
        self._is_ai = getattr(engine, 'strategy_mode', 'classic') == 'ai'

        self.engine.on_signal = self._on_signal
        self.engine.on_trade = self._on_trade

    def _on_signal(self, signal: Signal) -> None:
        self.signals[signal.ticker] = signal

    def _on_trade(self, trade: Trade) -> None:
        self._status_message = f"Trade: {trade.action} {trade.ticker} {trade.quantity}x @ {trade.price:.2f}"

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
        table.add_column("Dir", justify="center")
        table.add_column("Qty", justify="right")
        table.add_column("Entry", justify="right")
        table.add_column("Current", justify="right")
        table.add_column("P/L", justify="right")

        for ticker, pos in self.engine.execution.positions.items():
            bars = self.engine.market_data.get_bars(ticker)
            current = bars[-1].close if bars else pos.entry_price
            pnl = pos.unrealized_pnl(current)
            pnl_style = "green" if pnl >= 0 else "red"
            dir_str = "[green]LONG[/green]" if pos.direction == "LONG" else "[red]SHORT[/red]"

            table.add_row(
                ticker,
                dir_str,
                str(pos.quantity),
                f"{pos.entry_price:.2f}",
                f"{current:.2f}",
                f"[{pnl_style}]{pnl:+.2f}[/{pnl_style}]",
            )

        if not self.engine.execution.positions:
            table.add_row("[dim]No open positions[/dim]", "", "", "", "", "")

        return table

    def _build_trades_table(self) -> Table:
        table = Table(title="Trade Log", expand=True)
        table.add_column("Time")
        table.add_column("Action", justify="center")
        table.add_column("Ticker")
        table.add_column("Qty", justify="right")
        table.add_column("Price", justify="right")
        table.add_column("Reason")

        for trade in self.engine.execution.trades[-10:]:
            action_style = "green" if trade.action == "BUY" else "red"
            table.add_row(
                trade.timestamp.strftime("%H:%M:%S"),
                f"[{action_style}]{trade.action}[/{action_style}]",
                trade.ticker,
                str(trade.quantity),
                f"{trade.price:.2f}",
                trade.reason[:50],
            )

        if not self.engine.execution.trades:
            table.add_row("[dim]No trades yet[/dim]", "", "", "", "", "")

        return table

    def _build_ai_panel(self) -> Table:
        """Show latest AI reasoning for each ticker."""
        table = Table(title="AI Analysis", expand=True)
        table.add_column("Ticker", style="bold", width=8)
        table.add_column("Signal", justify="center", width=12)
        table.add_column("Reasoning")

        for ticker in self.engine.config.watchlist:
            signal = self.signals.get(ticker)
            if signal and signal.reason.startswith("AI:"):
                reason = signal.reason[4:]  # strip "AI: " prefix
                if signal.action == "BUY":
                    sig_str = f"[bold green]BUY {signal.confidence:.0%}[/bold green]"
                elif signal.action == "SELL":
                    sig_str = f"[bold red]SELL {signal.confidence:.0%}[/bold red]"
                else:
                    sig_str = f"[dim]HOLD {signal.confidence:.0%}[/dim]"
                table.add_row(ticker, sig_str, reason[:80])
            elif signal:
                table.add_row(ticker, "[dim]---[/dim]", f"[dim]{signal.reason[:80]}[/dim]")
            else:
                table.add_row(ticker, "[dim]---[/dim]", "[dim]Waiting for data...[/dim]")

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

        text = Text()
        text.append("  P/L: ", style="bold")
        text.append(f"${pnl:+.2f}", style=pnl_color)
        text.append(f"  |  Trades: {trade_count}")
        text.append(f"  |  Loss limit: {limit_used:.0f}%")
        text.append("  |  ")
        text.append(status, style=status_color)

        if self._is_ai:
            text.append("  |  ")
            text.append("AI", style="bold magenta")

        is_backtest = hasattr(self.engine, '_replay_done')
        if is_backtest:
            if self.engine._replay_done:
                text.append("  |  ", style="bold")
                text.append("REPLAY COMPLETE", style="bold green")
            else:
                progress = self.engine._bar_count
                total = self.engine._total_bars
                pct = (progress / total * 100) if total > 0 else 0
                text.append(f"  |  Bar {progress}/{total} ({pct:.0f}%)")
                for ticker in self.engine.config.watchlist:
                    bars = self.engine.market_data.get_bars(ticker)
                    if bars:
                        text.append(f"  |  {bars[-1].timestamp:%H:%M}")
                        break
        else:
            try:
                connected = self.engine.market_data.ib.isConnected()
                conn_str = "[green]Connected[/green]" if connected else "[red]Disconnected[/red]"
            except Exception:
                conn_str = "[dim]N/A[/dim]"
            # Detect broker type
            from stock_trader.capital_com import CapitalComClient
            is_capital = isinstance(self.engine.market_data.ib, CapitalComClient)
            broker_name = "Capital.com" if is_capital else "IBKR"
            text.append(f"  |  {broker_name}: ")
            text.append_text(Text.from_markup(conn_str))

        return text

    def _build_help_bar(self) -> Text:
        if self._input_mode:
            text = Text()
            text.append(f"  {self._input_prompt}", style="bold yellow")
            text.append(self._input_buffer, style="bold white")
            text.append("_", style="blink bold white")
            return text

        if self._status_message:
            text = Text()
            text.append(f"  {self._status_message}", style="bold cyan")
            return text

        text = Text()
        text.append("  [a]", style="bold green")
        text.append("dd  ")
        text.append("[r]", style="bold red")
        text.append("emove  ")
        text.append("[p]", style="bold yellow")
        text.append("ause  ")
        text.append("[u]", style="bold yellow")
        text.append("npause  ")
        text.append("[q]", style="bold")
        text.append("uit")
        return text

    def _build_display(self) -> Layout:
        layout = Layout()

        if self._is_ai:
            # AI mode: show analysis panel instead of larger trade log
            layout.split_column(
                Layout(Panel(self._build_watchlist_table()), name="watchlist", ratio=2),
                Layout(Panel(self._build_ai_panel()), name="ai", ratio=3),
                Layout(name="middle", ratio=2),
                Layout(Panel(self._build_trades_table()), name="trades", ratio=2),
                Layout(Panel(self._build_status_bar()), name="status", size=3),
                Layout(Panel(self._build_help_bar()), name="help", size=3),
            )
            layout["middle"].split_row(
                Layout(Panel(self._build_positions_table()), name="positions"),
            )
        else:
            layout.split_column(
                Layout(Panel(self._build_watchlist_table()), name="watchlist", ratio=3),
                Layout(Panel(self._build_positions_table()), name="positions", ratio=2),
                Layout(Panel(self._build_trades_table()), name="trades", ratio=3),
                Layout(Panel(self._build_status_bar()), name="status", size=3),
                Layout(Panel(self._build_help_bar()), name="help", size=3),
            )

        return layout

    def _read_key(self) -> str | None:
        """Read a single keypress without blocking (non-blocking)."""
        import select
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1)
        return None

    def _handle_key(self, key: str) -> None:
        if self._input_mode:
            if key == "\n" or key == "\r":
                ticker = self._input_buffer.strip().upper()
                if ticker:
                    if self._input_prompt.startswith("Add"):
                        self.engine.add_ticker(ticker)
                        self._status_message = f"Added {ticker}"
                    elif self._input_prompt.startswith("Remove"):
                        self.engine.remove_ticker(ticker)
                        self._status_message = f"Removed {ticker}"
                self._input_mode = False
                self._input_buffer = ""
                self._input_prompt = ""
            elif key == "\x1b":  # Escape
                self._input_mode = False
                self._input_buffer = ""
                self._input_prompt = ""
            elif key == "\x7f" or key == "\b":  # Backspace
                self._input_buffer = self._input_buffer[:-1]
            elif key.isalnum():
                self._input_buffer += key
            return

        self._status_message = ""

        if key == "a":
            self._input_mode = True
            self._input_prompt = "Add ticker: "
        elif key == "r":
            self._input_mode = True
            self._input_prompt = "Remove ticker: "
        elif key == "p":
            self.engine.pause()
            self._status_message = "Trading paused"
        elif key == "u":
            self.engine.resume()
            self._status_message = "Trading resumed"
        elif key == "q":
            self._running = False

    def run(self) -> None:
        self._running = True

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())

            # Cache the display and only update Live when content actually changes
            last_display = None
            with Live(self._build_display(), refresh_per_second=1, console=self.console, screen=True) as live:
                update_counter = 0
                while self._running:
                    try:
                        self.engine.sleep(0.2)
                    except (ConnectionError, OSError):
                        self._running = False
                        break

                    key = self._read_key()
                    if key:
                        self._handle_key(key)

                    # Only rebuild display every 5 ticks (~1s)
                    update_counter += 1
                    if update_counter >= 5 or key:
                        update_counter = 0
                        display = self._build_display()
                        live.update(display)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
