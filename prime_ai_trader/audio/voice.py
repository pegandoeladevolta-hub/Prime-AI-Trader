from __future__ import annotations

import os
import subprocess
import threading
import time


class VoiceService:
    def __init__(self) -> None:
        self._last_message = ""
        self._last_at = 0.0

    def speak(self, message: str, volume: int = 70, min_interval: float = 8.0) -> bool:
        if os.name != "nt" or not message:
            return False
        now = time.monotonic()
        if message == self._last_message and now - self._last_at < min_interval:
            return False
        self._last_message, self._last_at = message, now
        safe = message.replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$v=$s.GetInstalledVoices()|Where-Object {$_.VoiceInfo.Culture.Name -eq 'pt-BR'}|Select-Object -First 1; "
            "if($v){$s.SelectVoice($v.VoiceInfo.Name)}; "
            f"$s.Volume={max(0, min(volume, 100))}; $s.Speak('{safe}')"
        )
        threading.Thread(target=lambda: subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), capture_output=True, timeout=30,
        ), daemon=True).start()
        return True

