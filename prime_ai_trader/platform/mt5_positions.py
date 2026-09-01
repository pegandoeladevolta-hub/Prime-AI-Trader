from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from .mt5 import MT5ExecutionError, MT5OrderResult, MT5UnavailableError
from .mt5_robust import MT5Bridge as RobustMT5Bridge


class MT5Bridge(RobustMT5Bridge):
    """Ponte robusta com suporte a múltiplos terminais e corretoras MT5.

    Quando existem vários MetaTrader 5 no mesmo Windows, o pacote oficial
    ``MetaTrader5`` pode tentar anexar ao terminal errado. Esta ponte procura
    terminais de corretora instalados e dá prioridade ao Clear Investimentos MT5
    quando ele existe, sem armazenar login ou senha da conta.
    """

    CLEAR_FOLDER_HINTS = (
        "clear investimentos mt5 terminal",
        "clear investimentos metatrader 5",
        "clear investimentos mt5",
        "clear mt5",
    )
    TERMINAL_EXES = ("terminal64.exe", "terminal.exe")

    @staticmethod
    def _path_key(path: str | Path) -> str:
        try:
            return str(Path(path).resolve()).lower()
        except Exception:
            return str(path).lower()

    @classmethod
    def _registry_terminal_paths(cls) -> list[Path]:
        if os.name != "nt":
            return []
        try:
            import winreg  # type: ignore
        except ImportError:
            return []

        results: list[Path] = []
        roots = (
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        )
        for hive, key_name in roots:
            try:
                root = winreg.OpenKey(hive, key_name)
            except OSError:
                continue
            try:
                count = winreg.QueryInfoKey(root)[0]
                for index in range(count):
                    try:
                        sub_name = winreg.EnumKey(root, index)
                        sub = winreg.OpenKey(root, sub_name)
                        try:
                            display = str(winreg.QueryValueEx(sub, "DisplayName")[0] or "")
                        except OSError:
                            display = ""
                        if not any(token in display.lower() for token in ("clear", "metatrader", "mt5")):
                            sub.Close()
                            continue
                        try:
                            location = str(winreg.QueryValueEx(sub, "InstallLocation")[0] or "").strip()
                        except OSError:
                            location = ""
                        sub.Close()
                        if not location:
                            continue
                        folder = Path(location)
                        for exe in cls.TERMINAL_EXES:
                            candidate = folder / exe
                            if candidate.exists():
                                results.append(candidate)
                    except OSError:
                        continue
            finally:
                root.Close()
        return results

    @classmethod
    def discover_terminal_paths(cls, configured: str | Path | None = None) -> list[Path]:
        """Descobre terminais reais instalados sem depender do último MT5 usado."""
        candidates: list[Path] = []
        if configured:
            configured_path = Path(str(configured))
            if configured_path.exists():
                candidates.append(configured_path)

        roots: list[Path] = []
        for name in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            value = os.environ.get(name)
            if value:
                roots.append(Path(value))

        direct_folders = (
            "Clear Investimentos MT5 Terminal",
            "Clear Investimentos MetaTrader 5",
            "Clear Investimentos MT5",
            "Clear MT5",
            "MetaTrader 5",
        )
        for root in roots:
            for folder_name in direct_folders:
                folder = root / folder_name
                for exe in cls.TERMINAL_EXES:
                    candidate = folder / exe
                    if candidate.exists():
                        candidates.append(candidate)
            # Corretoras costumam instalar terminal64.exe em uma pasta diretamente
            # abaixo de Program Files. Fazemos apenas um nível para não varrer o disco.
            try:
                children = list(root.iterdir()) if root.exists() else []
            except OSError:
                children = []
            for child in children:
                if not child.is_dir():
                    continue
                lowered = child.name.lower()
                if not any(token in lowered for token in ("clear", "metatrader", "mt5")):
                    continue
                for exe in cls.TERMINAL_EXES:
                    candidate = child / exe
                    if candidate.exists():
                        candidates.append(candidate)

        candidates.extend(cls._registry_terminal_paths())
        unique: dict[str, Path] = {}
        for candidate in candidates:
            unique.setdefault(cls._path_key(candidate), candidate)

        configured_key = cls._path_key(configured) if configured else ""

        def score(path: Path) -> tuple[int, str]:
            text = str(path).lower()
            value = 0
            if "clear" in text:
                value += 1000
            if configured_key and cls._path_key(path) == configured_key:
                value += 600
                # Um caminho legado do MetaQuotes não deve ganhar do terminal Clear
                # recém-instalado só porque ficou salvo de uma sessão anterior.
                if "metaquotes" in text and "clear" not in text:
                    value -= 800
            if "metaquotes" in text and "clear" not in text:
                value -= 100
            if path.name.lower() == "terminal64.exe":
                value += 20
            return (-value, text)

        ordered = sorted(unique.values(), key=score)
        # Se existe um terminal Clear instalado, não fazemos fallback silencioso
        # para um MetaQuotes-Demo antigo: isso poderia operar na conta errada.
        clear = [path for path in ordered if "clear" in str(path).lower()]
        return clear if clear else ordered

    def _session_allowed(self, info: object) -> bool:
        """Permite que subclasses restrinjam a corretora da sessão encontrada."""
        return True

    def _session_rejection_reason(self, info: object) -> str:
        server = str(getattr(info, "server", "") or "não informado")
        login = int(getattr(info, "login", 0) or 0)
        return f"conta {login} do servidor {server} não pertence à corretora esperada"

    def _adopt_reported_terminal_path(self, mt5: object) -> None:
        """Guarda o executável informado pela sessão anexada, quando disponível."""
        try:
            terminal_info = mt5.terminal_info()  # type: ignore[attr-defined]
        except Exception:
            return
        raw = str(getattr(terminal_info, "path", "") or "").strip()
        if not raw:
            return
        reported = Path(raw)
        if reported.name.lower() in self.TERMINAL_EXES:
            self.terminal_path = str(reported)
            return
        for executable in self.TERMINAL_EXES:
            candidate = reported / executable
            if candidate.exists():
                self.terminal_path = str(candidate)
                return

    def connect(self):
        """Anexa primeiro à sessão aberta e só depois tenta um executável específico."""
        mt5 = self._module()
        candidates = self.discover_terminal_paths(self.terminal_path)
        attempts: list[str] = []
        authorization_failed = False

        def error_code(error: object) -> int:
            try:
                return int(error[0])  # type: ignore[index]
            except Exception:
                return 0

        def try_connection(
            kwargs: dict[str, Any], label: str, candidate: Path | None = None,
        ):
            nonlocal authorization_failed
            initialized = bool(mt5.initialize(**kwargs))
            error = mt5.last_error()
            if not initialized:
                if error_code(error) == -6:
                    authorization_failed = True
                attempts.append(f"{label}: {error}")
                return None

            info = mt5.account_info()
            if info is None:
                attempts.append(f"{label}: terminal acessível, mas sem conta ativa")
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                return None

            if not self._session_allowed(info):
                attempts.append(f"{label}: {self._session_rejection_reason(info)}")
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                return None

            self.connected = True
            if candidate is not None:
                self.terminal_path = str(candidate)
            else:
                self._adopt_reported_terminal_path(mt5)
            return self._account_snapshot(info)

        # A sessão que já está aberta deve vir primeiro. Forçar ``path=`` pode
        # iniciar outro contexto do mesmo terminal e devolver autorização -6,
        # mesmo quando a interface visível já está autenticada.
        try:
            mt5.shutdown()
        except Exception:
            pass
        account = try_connection({}, "ETAPA 1 • sessão MT5 já aberta")
        if account is not None:
            return account

        # Somente depois tentamos cada terminal instalado. Cada caminho é usado
        # uma única vez: repetir a mesma chamada após -6 não muda a autenticação.
        for candidate in candidates:
            try:
                mt5.shutdown()
            except Exception:
                pass
            account = try_connection(
                {"path": str(candidate)},
                f"ETAPA 2 • terminal selecionado {candidate}",
                candidate,
            )
            if account is not None:
                return account

        self.connected = False
        details = "\n".join(attempts[-3:]) if attempts else str(mt5.last_error())
        if authorization_failed or any("sem conta ativa" in item for item in attempts):
            raise MT5UnavailableError(
                "Não foi possível anexar à sessão ativa do MT5 da Clear.\n\n"
                "Confirme a conta ativa na barra de título do MetaTrader 5 e aguarde "
                "as cotações aparecerem. A lista do Navegador mostra contas cadastradas, "
                "mas não confirma qual delas está conectada.\n\n"
                "O Prime Trader não precisa e não armazena sua senha.\n\n"
                f"Diagnóstico por etapa:\n{details}"
            )
        raise MT5UnavailableError(
            "Não foi possível conectar a nenhum terminal MetaTrader 5 instalado.\n\n"
            "Use SELECIONAR TERMINAL MT5 e escolha o arquivo terminal64.exe da sua corretora.\n\n"
            f"Diagnóstico por etapa:\n{details}"
        )

    async def stream_candles(self, symbol: str, timeframe: str, callback, stop_event) -> None:
        """Entrega tanto o candle em formação quanto o fechamento real ao motor."""
        last_current_open = None
        last_current_signature = None
        last_closed_emitted = None

        while not stop_event.is_set():
            try:
                candles = self.fetch_candles(symbol, timeframe, limit=3)
                if candles:
                    current = candles[-1]
                    if last_current_open is not None and current.open_time != last_current_open:
                        previous = next(
                            (candle for candle in reversed(candles[:-1]) if candle.open_time == last_current_open),
                            None,
                        )
                        if previous is not None and previous.closed and previous.open_time != last_closed_emitted:
                            callback(previous)
                            last_closed_emitted = previous.open_time

                    signature = (
                        current.open_time, current.open, current.high, current.low,
                        current.close, current.volume, current.closed,
                    )
                    if signature != last_current_signature:
                        callback(current)
                        last_current_signature = signature
                        if current.closed:
                            last_closed_emitted = current.open_time
                    last_current_open = current.open_time

                await asyncio.sleep(0.50)
            except Exception:
                await asyncio.sleep(1.25)

    @staticmethod
    def _is_prime_position(row: dict[str, Any], magic: int) -> bool:
        try:
            row_magic = int(row.get("magic", 0) or 0)
        except (TypeError, ValueError):
            row_magic = 0
        comment = str(row.get("comment") or "").strip().lower()
        return row_magic == int(magic) or comment.startswith("prime trader")

    def prime_positions(self) -> list[dict[str, Any]]:
        return [row for row in self.positions() if self._is_prime_position(row, self.MAGIC)]

    def has_prime_position(self) -> bool:
        return bool(self.prime_positions())

    def modify_position_protection(
        self, ticket: int, *, sl: float, tp: float, armed: bool = False,
    ) -> MT5OrderResult:
        if not armed:
            raise MT5ExecutionError("Execução real desarmada.")
        self._ensure_connected()
        mt5 = self._module()
        rows = mt5.positions_get(ticket=int(ticket)) or ()
        if not rows:
            raise MT5ExecutionError(f"Posição {ticket} não encontrada.")
        position = rows[0]
        symbol = str(position.symbol)
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if info is None or tick is None:
            raise MT5ExecutionError(f"Sem dados atuais de {symbol} para ajustar SL/TP.")

        digits = int(getattr(info, "digits", 0) or 0)
        point = float(getattr(info, "point", 0.0) or 0.0)
        stops_level = int(getattr(info, "trade_stops_level", 0) or 0)
        freeze_level = int(getattr(info, "trade_freeze_level", 0) or 0)
        minimum_points = max(stops_level, freeze_level)
        is_buy = int(position.type) == int(mt5.POSITION_TYPE_BUY)
        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        reference = bid if is_buy else ask
        if reference <= 0 or point <= 0:
            raise MT5ExecutionError(f"Cotação inválida de {symbol} para ajustar proteção.")

        sl = round(float(sl or 0.0), digits) if sl else 0.0
        tp = round(float(tp or 0.0), digits) if tp else 0.0
        minimum_distance = minimum_points * point

        if is_buy:
            if sl and sl >= reference:
                raise MT5ExecutionError("Em uma compra, o Stop Loss precisa ficar abaixo do preço atual.")
            if tp and tp <= reference:
                raise MT5ExecutionError("Em uma compra, o Take Profit precisa ficar acima do preço atual.")
            if sl and minimum_distance and reference - sl < minimum_distance:
                raise MT5ExecutionError(f"Stop Loss muito próximo. O servidor exige ao menos {minimum_points} pontos.")
            if tp and minimum_distance and tp - reference < minimum_distance:
                raise MT5ExecutionError(f"Take Profit muito próximo. O servidor exige ao menos {minimum_points} pontos.")
        else:
            if sl and sl <= reference:
                raise MT5ExecutionError("Em uma venda, o Stop Loss precisa ficar acima do preço atual.")
            if tp and tp >= reference:
                raise MT5ExecutionError("Em uma venda, o Take Profit precisa ficar abaixo do preço atual.")
            if sl and minimum_distance and sl - reference < minimum_distance:
                raise MT5ExecutionError(f"Stop Loss muito próximo. O servidor exige ao menos {minimum_points} pontos.")
            if tp and minimum_distance and reference - tp < minimum_distance:
                raise MT5ExecutionError(f"Take Profit muito próximo. O servidor exige ao menos {minimum_points} pontos.")

        request: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": int(position.ticket),
            "symbol": symbol,
            "sl": sl,
            "tp": tp,
            "magic": self.MAGIC,
            "comment": "Prime Trader protection",
        }
        result = mt5.order_send(request)
        return self._result_or_raise(mt5, result)


__all__ = ["MT5Bridge"]
