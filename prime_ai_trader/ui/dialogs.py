from __future__ import annotations

import json
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

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
            ("RESULTADO LÍQUIDO", f"R$ {result.net_profit:,.2f}"),
            ("PROFIT FACTOR", f"{result.profit_factor:.4f}" if result.profit_factor is not None else "—"),
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


class ManualResultDialog:
    """Registro explícito do desfecho visto pelo usuário na plataforma."""

    def __init__(self, parent, rows: list[dict], on_save,
                 default_payout: int, default_stake: float) -> None:
        self.window = centered_window(parent, "Resultado observado", "790x570")
        outer = ttk.Frame(self.window, style="Panel.TFrame", padding=18)
        outer.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(outer, text="REGISTRAR RESULTADO DA PLATAFORMA", style="Panel.TLabel",
                  font=("Segoe UI Semibold", 14)).pack(anchor="w")
        ttk.Label(
            outer,
            text="Selecione o sinal e informe o resultado realmente observado. "
                 "Isso substitui qualquer resultado apenas inferido pelo gráfico público.",
            style="Muted.TLabel", wraplength=700,
        ).pack(anchor="w", pady=(4, 12))
        tree = ttk.Treeview(
            outer, columns=("id", "time", "platform", "asset", "direction", "result", "source"),
            show="headings", height=12,
        )
        for key, label, width in (
            ("id", "ID", 45), ("time", "HORÁRIO", 130), ("platform", "PLATAFORMA", 90),
            ("asset", "ATIVO", 100), ("direction", "DIREÇÃO", 80),
            ("result", "RESULTADO", 80), ("source", "FONTE", 80),
        ):
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor="center")
        tree.pack(fill="both", expand=True)
        for row in rows:
            tree.insert("", "end", iid=str(row["id"]), values=(
                row["id"], str(row.get("created_at", ""))[:19].replace("T", " "),
                row.get("platform") or "MANUAL", row.get("symbol") or "—",
                row.get("direction") or "—", row.get("result") or "PENDENTE",
                row.get("result_source") or "—",
            ))
        if rows:
            tree.selection_set(str(rows[0]["id"]))

        fields = ttk.Frame(outer, style="Panel.TFrame")
        fields.pack(fill="x", pady=(12, 8))
        payout_var = tk.StringVar(value=str(default_payout))
        stake_var = tk.StringVar(value=f"{default_stake:.2f}")
        ttk.Label(fields, text="Payout (%)", style="Panel.TLabel").pack(side="left")
        ttk.Entry(fields, textvariable=payout_var, width=8).pack(side="left", padx=(6, 20))
        ttk.Label(fields, text="Entrada (R$)", style="Panel.TLabel").pack(side="left")
        ttk.Entry(fields, textvariable=stake_var, width=12).pack(side="left", padx=6)

        def register(result: str) -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Resultado", "Selecione um sinal.", parent=self.window)
                return
            try:
                payout = int(payout_var.get())
                stake = float(stake_var.get().replace(",", "."))
                if not 1 <= payout <= 200 or stake <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Resultado", "Payout ou valor da entrada inválido.", parent=self.window)
                return
            on_save(int(selected[0]), result, payout, stake)
            messagebox.showinfo("Resultado", f"{result} registrado como resultado observado.", parent=self.window)
            self.window.destroy()

        buttons = ttk.Frame(outer, style="Panel.TFrame")
        buttons.pack(fill="x")
        ttk.Button(buttons, text="WIN", style="Accent.TButton", command=lambda: register("WIN")).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(buttons, text="LOSS", style="Danger.TButton", command=lambda: register("LOSS")).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(buttons, text="DRAW", command=lambda: register("DRAW")).pack(side="left", fill="x", expand=True, padx=(4, 0))


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
                f"Cobertura direcional: {coverage * 100:.2f}%\n"
                f"Lucro bruto: R$ {stats.get('gross_profit', 0):,.2f}   "
                f"Perda bruta: R$ {stats.get('gross_loss', 0):,.2f}\n"
                f"Resultado líquido: R$ {stats.get('net_profit', 0):,.2f}\n"
                f"Profit factor financeiro: {profit_factor}   •   "
                f"Expectativa/operação: R$ {(stats.get('expectancy_per_operation') or 0):,.2f}\n"
                f"Resultados observados: {stats.get('manual_results') or 0}   •   "
                f"Inferidos: {stats.get('inferred_results') or 0}"
            )
        ttk.Label(outer, text=summary, style="Panel.TLabel", font=("Segoe UI", 12), justify="left").pack(anchor="w", pady=(14, 20))
        if total:
            ttk.Label(outer, text=f"Maior sequência WIN: {stats.get('longest_win_streak', 0)}   •   Maior sequência LOSS: {stats.get('longest_loss_streak', 0)}", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        tree = ttk.Treeview(outer, columns=("platform", "symbol", "timeframe", "strategy", "total", "accuracy"), show="headings")
        for key, label, width in (("platform", "PLATAFORMA", 85), ("symbol", "ATIVO", 100), ("timeframe", "TF", 50), ("strategy", "ESTRATÉGIA", 150), ("total", "TOTAL", 60), ("accuracy", "ACERTO", 80)):
            tree.heading(key, text=label); tree.column(key, width=width, anchor="center")
        tree.pack(fill="both", expand=True)
        for group in stats.get("groups", []):
            directional = (group.get("wins") or 0) + (group.get("losses") or 0)
            rate = (group.get("wins") or 0) / directional if directional else 0
            tree.insert("", "end", values=(group.get("platform", "MANUAL"), group["symbol"], group["timeframe"], group.get("strategy") or group["mode"], group["total"], f"{rate * 100:.2f}%" if directional else "—"))
        ttk.Button(outer, text="FECHAR", command=self.window.destroy).pack(anchor="e", pady=(10, 0))


class DecisionHistoryDialog:
    """Exibe sinais, esperas, configuração e a justificativa completa da IA."""

    def __init__(self, parent, repository, rows: list[dict]) -> None:
        self.parent = parent
        self.repository = repository
        self.rows = rows
        self.window = centered_window(parent, "Histórico operacional completo", "1320x780")
        self.window.minsize(1030, 650)
        outer = ttk.Frame(self.window, style="Panel.TFrame", padding=16)
        outer.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(outer, text="HISTÓRICO OPERACIONAL E DECISÕES DA IA",
                  style="Panel.TLabel", font=("Segoe UI Semibold", 15)).pack(anchor="w")
        ttk.Label(
            outer,
            text="Registra análises, espera, configuração, compra/venda, pullbacks, "
                 "payout, entradas, indicadores e resultados observados ou inferidos.",
            style="Muted.TLabel", wraplength=1170,
        ).pack(anchor="w", pady=(4, 10))

        filters = ttk.Frame(outer, style="Panel.TFrame")
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="Ativo", style="Panel.TLabel").pack(side="left")
        self.symbol_var = tk.StringVar(value="TODOS")
        self.symbol_combo = ttk.Combobox(filters, textvariable=self.symbol_var,
                                         state="readonly", width=17)
        self.symbol_combo.pack(side="left", padx=(6, 14))
        self.symbol_combo.bind("<<ComboboxSelected>>", lambda _: self._populate())
        ttk.Label(filters, text="Evento", style="Panel.TLabel").pack(side="left")
        self.event_var = tk.StringVar(value="TODOS")
        self.event_combo = ttk.Combobox(filters, textvariable=self.event_var,
                                        state="readonly", width=26)
        self.event_combo.pack(side="left", padx=(6, 14))
        self.event_combo.bind("<<ComboboxSelected>>", lambda _: self._populate())
        self.counter_var = tk.StringVar(value="")
        ttk.Label(filters, textvariable=self.counter_var, style="Muted.TLabel").pack(side="right")

        frame = ttk.Frame(outer, style="Panel.TFrame")
        frame.pack(fill="both", expand=True)
        columns = ("time", "event", "asset", "timeframe", "profile", "mode", "direction",
                   "result", "score", "pullback", "payout", "stake")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=13)
        definitions = (
            ("time", "HORÁRIO", 150), ("event", "EVENTO", 160), ("asset", "ATIVO", 104),
            ("timeframe", "TF/EXP.", 75), ("profile", "PERFIL", 94), ("mode", "MODO", 108),
            ("direction", "DIREÇÃO", 78), ("result", "RESULTADO", 88),
            ("score", "SCORE", 60), ("pullback", "PULLBACK / FASE", 250),
            ("payout", "PAYOUT", 70), ("stake", "ENTRADA", 80),
        )
        for key, title, width in definitions:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=55, anchor="center",
                             stretch=key in {"event", "pullback"})
        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._show_detail)

        ttk.Label(outer, text="DETALHES DA DECISÃO SELECIONADA", style="Panel.TLabel",
                  font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(12, 4))
        details = ttk.Frame(outer, style="Panel.TFrame")
        details.pack(fill="both", expand=True)
        self.detail = tk.Text(details, height=10, bg=COLORS["card_alt"], fg=COLORS["text"],
                              insertbackground=COLORS["text"], relief="flat", wrap="word",
                              font=("Consolas", 9), padx=10, pady=8)
        detail_scroll = ttk.Scrollbar(details, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

        actions = ttk.Frame(outer, style="Panel.TFrame")
        actions.pack(fill="x", pady=(10, 0))
        self.refresh_button = ttk.Button(actions, text="ATUALIZAR HISTÓRICO", command=self.refresh)
        self.refresh_button.pack(side="left")
        self.export_button = ttk.Button(actions, text="EXPORTAR EXCEL (.XLSX)",
                                        style="Accent.TButton", command=self.export)
        self.export_button.pack(side="left", padx=8)
        ttk.Button(actions, text="FECHAR", command=self.window.destroy).pack(side="right")
        self._update_filters()
        self._populate()

    def _update_filters(self) -> None:
        assets = sorted({str(row.get("symbol")) for row in self.rows if row.get("symbol")})
        events = sorted({str(row.get("event_type")) for row in self.rows if row.get("event_type")})
        self.symbol_combo.configure(values=["TODOS", *assets])
        self.event_combo.configure(values=["TODOS", *events])
        if self.symbol_var.get() not in {"TODOS", *assets}:
            self.symbol_var.set("TODOS")
        if self.event_var.get() not in {"TODOS", *events}:
            self.event_var.set("TODOS")

    def _populate(self) -> None:
        self.tree.delete(*self.tree.get_children())
        visible = [row for row in self.rows
                   if (self.symbol_var.get() == "TODOS" or row.get("symbol") == self.symbol_var.get())
                   and (self.event_var.get() == "TODOS" or row.get("event_type") == self.event_var.get())]
        for row in visible:
            try:
                when = datetime.fromisoformat(str(row.get("created_at", "")).replace("Z", "+00:00"))
                stamp = when.astimezone().strftime("%d/%m %H:%M:%S") if when.tzinfo else when.strftime("%d/%m %H:%M:%S")
            except (TypeError, ValueError):
                stamp = str(row.get("created_at") or "—")[:19]
            self.tree.insert("", "end", iid=str(row["id"]), values=(
                stamp, row.get("event_type"), row.get("symbol"),
                f"{row.get('timeframe', '')}/{row.get('horizon_minutes', '')}m",
                row.get("sensitivity") or "—", row.get("mode") or "—",
                row.get("direction") or "—", row.get("result") or "—",
                row.get("score") or 0, row.get("pullback_state") or row.get("reason_summary") or "—",
                f"{row.get('payout_percent') or 0}%", f"R$ {float(row.get('stake_amount') or 0):.2f}",
            ))
        self.counter_var.set(f"{len(visible)} eventos exibidos • {len(self.rows)} carregados")
        if visible:
            self.tree.selection_set(str(visible[0]["id"]))
            self._show_detail()
        else:
            self._set_detail("Nenhuma decisão disponível para os filtros selecionados.")

    def _set_detail(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("end", text)
        self.detail.configure(state="disabled")

    def _show_detail(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        row = next((item for item in self.rows if int(item["id"]) == int(selected[0])), None)
        if row is None:
            return
        try:
            payload = json.loads(row.get("snapshot_json") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        signal = payload.get("signal", {})
        settings = payload.get("settings", {})
        summary = [
            f"EVENTO: {row.get('event_type')}   ATIVO: {row.get('symbol')}   RESULTADO: {row.get('result') or '—'}",
            f"CONFIGURAÇÃO: {row.get('timeframe')} / expiração {row.get('horizon_minutes')} min / "
            f"{row.get('sensitivity')} / {row.get('mode')} / payout {row.get('payout_percent')}% / "
            f"entrada R$ {float(row.get('stake_amount') or 0):.2f}",
            f"DIREÇÃO FINAL: {row.get('direction')}   SCORE COMPRA: {signal.get('buy_score', '—')}   "
            f"SCORE VENDA: {signal.get('sell_score', '—')}   TÉCNICO: {signal.get('technical_score', '—')}",
            f"PULLBACK: tendência {signal.get('pullback_primary_direction') or '—'} / "
            f"correção {signal.get('pullback_correction_direction') or '—'} / "
            f"fase {signal.get('pullback_phase') or '—'}",
            f"MOTIVOS COMPRA: {' | '.join(signal.get('buy_reasons', [])) or '—'}",
            f"MOTIVOS VENDA: {' | '.join(signal.get('sell_reasons', [])) or '—'}",
            f"AGUARDAR/BLOQUEIOS: {' | '.join((signal.get('all_waiting_reasons') or signal.get('waiting_reasons', [])) + signal.get('blockers', [])) or '—'}",
            f"RISCO REVERSÃO: {' | '.join(signal.get('reversal_reasons', [])) or '—'}",
            f"CONFIGURAÇÕES COMPLETAS: {json.dumps(settings, ensure_ascii=False, sort_keys=True)}",
            "\nREGISTRO TÉCNICO COMPLETO:\n" + json.dumps(payload, ensure_ascii=False, indent=2),
        ]
        self._set_detail("\n".join(summary))

    def refresh(self) -> None:
        self.refresh_button.configure(state="disabled")

        def worker() -> None:
            try:
                rows = self.repository.decision_history(1000)
                self.parent._post_ui(self._refresh_ready, rows, None)
            except Exception as exc:
                self.parent._post_ui(self._refresh_ready, None, str(exc))

        threading.Thread(target=worker, daemon=True, name="prime-history-refresh").start()

    def _refresh_ready(self, rows: list[dict] | None, error: str | None) -> None:
        if not self.window.winfo_exists():
            return
        self.refresh_button.configure(state="normal")
        if error:
            messagebox.showerror("Histórico", error, parent=self.window)
            return
        self.rows = rows or []
        self._update_filters()
        self._populate()

    def export(self) -> None:
        destination = filedialog.asksaveasfilename(
            parent=self.window, title="Exportar histórico operacional",
            defaultextension=".xlsx", filetypes=[("Planilha Excel", "*.xlsx")],
            initialfile=f"PrimeAITrader-Historico-{datetime.now():%Y-%m-%d_%H-%M}.xlsx",
        )
        if not destination:
            return
        self.export_button.configure(state="disabled", text="EXPORTANDO EXCEL…")

        def worker() -> None:
            try:
                from ..history.export import export_operation_history
                output = export_operation_history(self.repository, destination)
                self.parent._post_ui(self._export_ready, str(output), None)
            except Exception as exc:
                self.parent._post_ui(self._export_ready, None, str(exc))

        threading.Thread(target=worker, daemon=True, name="prime-history-excel").start()

    def _export_ready(self, output: str | None, error: str | None) -> None:
        if not self.window.winfo_exists():
            return
        self.export_button.configure(state="normal", text="EXPORTAR EXCEL (.XLSX)")
        if error:
            messagebox.showerror("Exportar Excel", error, parent=self.window)
            return
        self.parent.status_var.set("Histórico operacional exportado com sucesso")
        messagebox.showinfo(
            "Excel exportado",
            "Arquivo Excel criado com as abas Resumo, Operações, Decisões da IA, "
            f"Indicadores e features, Configurações, Velas e pullbacks e Notícias e eventos.\n\n{output}",
            parent=self.window,
        )


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
