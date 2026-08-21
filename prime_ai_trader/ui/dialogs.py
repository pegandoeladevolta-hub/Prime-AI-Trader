from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from ..backtest.engine import BacktestResult
from ..core.models import HealthStatus
from ..radar.engine import RadarItem
from .theme import COLORS


def centered_window(parent, title: str, size: str) -> tk.Toplevel:
    window = tk.Toplevel(parent)
    window.title(title)
    window.geometry(size)
    window.configure(bg=COLORS["bg"])
    window.transient(parent)
    window.grab_set()
    return window


class ApiSettingsDialog:
    FIELDS = [
        ("twelve_data_key", "Twelve Data API Key", "Opcional. Melhora o Forex; o plano gratuito oferece 8 créditos/minuto e 800 por dia."),
        ("alpha_vantage_key", "Alpha Vantage API Key", "Opcional. Fonte gratuita extra de Forex quando a chave estiver disponível."),
        ("finnhub_key", "Finnhub API Key", "Opcional. Complementa o calendário econômico público sem bloquear o aplicativo."),
    ]

    def __init__(self, parent, values: dict[str, str], on_save) -> None:
        self.window = centered_window(parent, "Configurações de APIs", "650x540")
        panel = ttk.Frame(self.window, style="Panel.TFrame", padding=22)
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        ttk.Label(panel, text="CHAVES DE API", style="Panel.TLabel", font=("Segoe UI Semibold", 14)).pack(anchor="w")
        ttk.Label(panel, text="As chaves são protegidas pelo Windows DPAPI e nunca ficam no código-fonte.", style="Muted.TLabel", wraplength=520).pack(anchor="w", pady=(4, 18))
        ttk.Label(panel, text="Binance, Coinbase, Kraken, Forex público, notícias e calendário funcionam sem chave. As chaves abaixo são opcionais.", style="Muted.TLabel", wraplength=565).pack(anchor="w", pady=(0, 8))
        self.variables = {}
        for key, label, help_text in self.FIELDS:
            ttk.Label(panel, text=label, style="Panel.TLabel").pack(anchor="w", pady=(7, 3))
            variable = tk.StringVar(value=values.get(key, ""))
            entry = ttk.Entry(panel, textvariable=variable, show="•", width=64)
            entry.pack(fill="x")
            ttk.Label(panel, text=help_text, style="Muted.TLabel", wraplength=535).pack(anchor="w", pady=(3, 4))
            self.variables[key] = variable
        buttons = ttk.Frame(panel, style="Panel.TFrame")
        buttons.pack(fill="x", pady=(20, 0))
        ttk.Button(buttons, text="CRIAR CHAVE GRÁTIS", command=lambda: webbrowser.open("https://twelvedata.com/pricing")).pack(side="left")
        ttk.Button(buttons, text="CANCELAR", command=self.window.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="SALVAR CHAVES", style="Accent.TButton", command=lambda: self._save(on_save)).pack(side="right")

    def _save(self, on_save) -> None:
        on_save({key: variable.get().strip() for key, variable in self.variables.items()})
        messagebox.showinfo("APIs", "Chaves salvas com proteção local.", parent=self.window)
        self.window.destroy()


class BacktestDialog:
    def __init__(self, parent, result: BacktestResult) -> None:
        self.window = centered_window(parent, "Backtest walk-forward", "780x650")
        outer = ttk.Frame(self.window, style="Panel.TFrame", padding=20)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(outer, text="BACKTEST PROFISSIONAL", style="Panel.TLabel", font=("Segoe UI Semibold", 15)).pack(anchor="w")
        ttk.Label(outer, text="Resultados fora da amostra. ACERTO DIRECIONAL exclui DRAW e não mascara movimentos neutros.", style="Muted.TLabel").pack(anchor="w", pady=(3, 15))
        metrics = ttk.Frame(outer, style="Panel.TFrame")
        metrics.pack(fill="x")
        values = [
            ("OPERAÇÕES", str(result.operations)), ("WIN", str(result.wins)), ("LOSS", str(result.losses)),
            ("DRAW", str(result.draws)), ("ACERTO DIRECIONAL", f"{result.accuracy * 100:.2f}%" if result.directional_operations else "SEM AMOSTRA"),
            ("QUALIDADE", result.quality), ("PONTO DE EQUILÍBRIO", f"{result.break_even_rate * 100:.2f}%"),
            ("OP. DIRECIONAIS", str(result.directional_operations)), ("EXPECTATIVA", f"{result.expected_value * 100:+.2f}%"),
        ]
        for index, (label, value) in enumerate(values):
            card = ttk.Frame(metrics, style="Card.TFrame", padding=12)
            card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=4, pady=4)
            metrics.columnconfigure(index % 3, weight=1)
            ttk.Label(card, text=label, style="Card.TLabel", foreground=COLORS["muted"], font=("Segoe UI", 8)).pack(anchor="w")
            ttk.Label(card, text=value, style="Card.TLabel", font=("Segoe UI Semibold", 14)).pack(anchor="w", pady=(3, 0))
        detail = tk.Text(outer, bg=COLORS["card_alt"], fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat", height=14, font=("Consolas", 10), padx=12, pady=12)
        detail.pack(fill="both", expand=True, pady=(14, 8))
        matrix = result.confusion
        detail.insert("end", "MATRIZ DE CONFUSÃO (real → previsto)\n")
        detail.insert("end", "             VENDA  AGUARDAR  COMPRA\n")
        for label, row in zip(("VENDA", "AGUARDAR", "COMPRA"), matrix):
            detail.insert("end", f"{label:<10} {row[0]:>6} {row[1]:>9} {row[2]:>7}\n")
        detail.insert("end", f"\nSeparação temporal\nTRAIN: {result.train_samples} amostras\nVALIDATION: {result.validation_samples} amostras\nTEST: {result.test_samples} amostras\n")
        detail.insert("end", f"\nDRAW: {result.draw_rate * 100:.2f}% das operações • sequência WIN {result.longest_win_streak} • sequência LOSS {result.longest_loss_streak}\n")
        detail.insert(
            "end",
            f"PAYOUT: {result.payout_percent}% • equilíbrio: {result.break_even_rate * 100:.2f}% "
            f"• intervalo de confiança: {result.confidence_low * 100:.1f}% a {result.confidence_high * 100:.1f}%\n",
        )
        if result.quality in {"FRACA", "AMOSTRA INSUFICIENT", "AMOSTRA EM FORMAÇÃO"}:
            if result.quality in {"AMOSTRA INSUFICIENT", "AMOSTRA EM FORMAÇÃO"}:
                detail.insert(
                    "end",
                    f"AMOSTRA EM COLETA: existem {result.directional_operations} operações direcionais; "
                    "o mínimo para avaliar é 20. Isto não é erro e não bloqueia a análise.\n",
                )
            else:
                detail.insert("end", "AVISO DE QUALIDADE: resultado fraco fora da amostra. O app não bloqueia a análise, mas recomenda cautela.\n")
        if result.by_hour:
            detail.insert("end", "\nDesempenho por horário\n")
            for hour, item in result.by_hour.items():
                detail.insert("end", f"{hour:02d}:00  sinais={int(item['signals']):>4}  draw={int(item.get('draws', 0)):>3}  acerto dir.={item['accuracy'] * 100:>6.2f}%\n")
        detail.configure(state="disabled")
        ttk.Button(outer, text="FECHAR", command=self.window.destroy).pack(anchor="e")


class RadarDialog:
    def __init__(self, parent, items: list[RadarItem], on_analyze) -> None:
        self.window = centered_window(parent, "Radar de mercado", "720x560")
        outer = ttk.Frame(self.window, style="Panel.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(outer, text="RADAR DE MERCADO", style="Panel.TLabel", font=("Segoe UI Semibold", 15)).pack(anchor="w")
        ttk.Label(outer, text="O score indica interesse para análise; não é garantia nem sinal de operação.", style="Muted.TLabel").pack(anchor="w", pady=(3, 14))
        tree = ttk.Treeview(outer, columns=("rank", "symbol", "score", "reason"), show="headings")
        tree.heading("rank", text="#"); tree.heading("symbol", text="ATIVO"); tree.heading("score", text="SCORE"); tree.heading("reason", text="MOTIVO")
        tree.column("rank", width=40, anchor="center"); tree.column("symbol", width=110); tree.column("score", width=80, anchor="center"); tree.column("reason", width=420)
        tree.pack(fill="both", expand=True)
        for rank, item in enumerate(items, 1):
            tree.insert("", "end", values=(rank, item.symbol, item.score, item.reason))
        def select() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Radar", "Selecione um ativo.", parent=self.window)
                return
            symbol = tree.item(selected[0], "values")[1]
            self.window.destroy()
            on_analyze(symbol)
        tree.bind("<Double-1>", lambda _: select())
        ttk.Button(outer, text="ANALISAR ATIVO", style="Accent.TButton", command=select).pack(anchor="e", pady=(12, 0))


class PerformanceDialog:
    def __init__(self, parent, stats: dict) -> None:
        self.window = centered_window(parent, "Desempenho", "680x520")
        outer = ttk.Frame(self.window, style="Panel.TFrame", padding=20)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(outer, text="DESEMPENHO REAL", style="Panel.TLabel", font=("Segoe UI Semibold", 15)).pack(anchor="w")
        total = stats.get("total") or 0
        accuracy = stats.get("accuracy")
        if accuracy is None:
            summary = "Nenhuma operação direcional concluída. As estatísticas aparecerão após resultados reais serem registrados."
        else:
            directional_total = stats.get("directional_total") or 0
            coverage = directional_total / total if total else 0.0
            profit_factor = f"{stats['profit_factor']:.2f}" if stats.get("profit_factor") is not None else "não aplicável"
            summary = (
                f"Sinais concluídos: {total}\n"
                f"WIN: {stats.get('wins') or 0}   LOSS: {stats.get('losses') or 0}   DRAW: {stats.get('draws') or 0}\n"
                f"Acerto direcional: {accuracy * 100:.2f}% em {directional_total} operações\n"
                f"Cobertura direcional: {coverage * 100:.2f}%\nProfit factor: {profit_factor}"
            )
        ttk.Label(outer, text=summary, style="Panel.TLabel", font=("Segoe UI", 12), justify="left").pack(anchor="w", pady=(14, 20))
        if total:
            ttk.Label(outer, text=f"Maior sequência WIN: {stats.get('longest_win_streak', 0)}   •   Maior sequência LOSS: {stats.get('longest_loss_streak', 0)}", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        tree = ttk.Treeview(outer, columns=("symbol", "timeframe", "mode", "total", "accuracy"), show="headings")
        for key, label, width in (("symbol", "ATIVO", 120), ("timeframe", "TF", 60), ("mode", "MODO", 130), ("total", "TOTAL", 70), ("accuracy", "ACERTO", 90)):
            tree.heading(key, text=label); tree.column(key, width=width, anchor="center")
        tree.pack(fill="both", expand=True)
        for group in stats.get("groups", []):
            directional = (group.get("wins") or 0) + (group.get("losses") or 0)
            rate = (group.get("wins") or 0) / directional if directional else 0
            tree.insert("", "end", values=(group["symbol"], group["timeframe"], group["mode"], group["total"], f"{rate * 100:.2f}%" if directional else "—"))
        ttk.Button(outer, text="FECHAR", command=self.window.destroy).pack(anchor="e", pady=(10, 0))


class HealthDialog:
    def __init__(self, parent, statuses: list[HealthStatus]) -> None:
        self.window = centered_window(parent, "Monitor de saúde", "650x500")
        outer = ttk.Frame(self.window, style="Panel.TFrame", padding=20)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(outer, text="MONITOR DE SAÚDE", style="Panel.TLabel", font=("Segoe UI Semibold", 15)).pack(anchor="w")
        ttk.Label(outer, text="Diagnóstico medido agora. Serviços opcionais sem chave aparecem em amarelo.", style="Muted.TLabel").pack(anchor="w", pady=(3, 14))
        for status in statuses:
            row = ttk.Frame(outer, style="Card.TFrame", padding=10)
            row.pack(fill="x", pady=3)
            optional = not status.online and ("CHAVE NÃO CONFIGURADA" in status.detail.upper() or "RETREINAR" in status.detail.upper())
            color = COLORS["green"] if status.online else COLORS["amber"] if optional else COLORS["red"]
            ttk.Label(row, text=f"● {status.name}", style="Card.TLabel", foreground=color, font=("Segoe UI Semibold", 10), width=14).pack(side="left")
            detail = status.detail
            if status.latency_ms is not None:
                detail += f" • {status.latency_ms:.0f} ms"
            ttk.Label(row, text=detail, style="Card.TLabel", foreground=COLORS["muted"], wraplength=430).pack(side="left", fill="x", expand=True)
        ttk.Button(outer, text="FECHAR", command=self.window.destroy).pack(anchor="e", pady=(10, 0))
