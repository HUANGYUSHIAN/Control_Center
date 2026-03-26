from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
import os
from pathlib import Path

import psutil
import websockets
from rich.console import Console
from rich.live import Live
from rich.table import Table
try:
    import pynvml
except Exception:  # pragma: no cover
    pynvml = None

console = Console()

_TMUI_ROOT = Path(__file__).resolve().parent.parent
if str(_TMUI_ROOT) not in sys.path:
    sys.path.insert(0, str(_TMUI_ROOT))
from tmui_discovery import resolve_server_endpoint  # noqa: E402

state = {"requests": 0, "replies": 0, "server": "N/A"}


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


class ResourceMonitor:
    def __init__(self) -> None:
        self.samples = 0
        self.ram_avg = 0.0
        self.ram_max = 0.0
        self.gpu_avg = 0.0
        self.gpu_max = 0.0
        self.vram_avg = 0.0
        self.vram_max = 0.0
        self.gpu_available = False
        self._proc = psutil.Process(os.getpid())
        self._gpu_handle = None
        if pynvml is not None:
            try:
                pynvml.nvmlInit()
                if pynvml.nvmlDeviceGetCount() > 0:
                    self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    self.gpu_available = True
            except Exception:
                self.gpu_available = False

    def _avg(self, prev: float, value: float) -> float:
        return ((prev * self.samples) + value) / (self.samples + 1)

    def update(self) -> None:
        rss_mb = self._proc.memory_info().rss / (1024 * 1024)
        self.ram_avg = self._avg(self.ram_avg, rss_mb)
        self.ram_max = max(self.ram_max, rss_mb)
        if self.gpu_available and self._gpu_handle is not None:
            try:
                util = float(pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle).gpu)
                mem = pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                vram_mb = mem.used / (1024 * 1024)
                self.gpu_avg = self._avg(self.gpu_avg, util)
                self.gpu_max = max(self.gpu_max, util)
                self.vram_avg = self._avg(self.vram_avg, vram_mb)
                self.vram_max = max(self.vram_max, vram_mb)
            except Exception:
                self.gpu_available = False
        self.samples += 1


resource_monitor = ResourceMonitor()


def build_table() -> Table:
    resource_monitor.update()
    table = Table(title="worker_actplan 高頻狀態")
    table.add_column("項目")
    table.add_column("值")
    table.add_row("server", state["server"])
    table.add_row("requests", str(state["requests"]))
    table.add_row("replies", str(state["replies"]))
    table.add_row("RAM MB(avg/max)", f"{resource_monitor.ram_avg:.1f} / {resource_monitor.ram_max:.1f}")
    if resource_monitor.gpu_available:
        table.add_row("GPU %(avg/max)", f"{resource_monitor.gpu_avg:.1f} / {resource_monitor.gpu_max:.1f}")
        table.add_row("VRAM MB(avg/max)", f"{resource_monitor.vram_avg:.1f} / {resource_monitor.vram_max:.1f}")
    else:
        table.add_row("GPU", "No GPU")
        table.add_row("VRAM", "No GPU")
    return table


async def run(ip: str, port: str) -> None:
    uri = f"ws://{ip}:{port}/ws"
    console.print(f"[cyan]{now_text()}[/cyan] 連線到 {uri}")
    try:
        async with websockets.connect(uri) as ws:
            # ================================
            # I/O CONTRACT (with TMUI server)
            # ================================
            # Input from server:
            #   {"event":"command_input","text":"<user natural language>"}
            #
            # Output to server:
            #   {"event":"command_reply","role":"assistant","text":"<assistant reply>"}
            #
            # This worker currently mocks an LLM action planner by:
            # - sleeping 2 seconds
            # - returning the first half of the input string
            #
            # Replace that mock section with your real LLM action planner module.
            await ws.send(json.dumps({"event": "register", "role": "worker_actplan"}, ensure_ascii=False))
            ack = json.loads(await ws.recv())
            console.print(f"[green]{now_text()}[/green] 註冊成功: {ack}")

            while True:
                data = json.loads(await ws.recv())
                if data.get("event") != "command_input":
                    continue
                text = data.get("text", "")
                console.print(f"[yellow]{now_text()}[/yellow] 收到請求: {text}")
                state["requests"] += 1

                # -----------------------------
                # MOCK LLM ACTION PLANNER
                # -----------------------------
                # TODO: Replace the following mock logic with real inference:
                # - call your LLM/action-planner
                # - generate a reply string
                # Example pseudo-code (you implement in your module):
                #   reply = llm_action_planner.generate(text)
                await asyncio.sleep(2)
                reply = text[: len(text) // 2] if text else ""

                # Send the reply back to the server
                await ws.send(
                    json.dumps(
                        {"event": "command_reply", "role": "assistant", "text": reply},
                        ensure_ascii=False,
                    )
                )
                console.print(f"[green]{now_text()}[/green] 已回覆: {reply}")
                state["replies"] += 1
    except Exception as exc:
        console.print(f"[red]{now_text()}[/red] 連線失敗或中斷: {exc}")


if __name__ == "__main__":
    server_ip, server_port = resolve_server_endpoint("worker_actplan")
    state["server"] = f"{server_ip}:{server_port}"
    console.print(f"[cyan]{now_text()}[/cyan] 使用 server -> {state['server']}")

    live = Live(build_table(), console=console, refresh_per_second=4)
    live.start()
    try:
        async def refresh_live() -> None:
            while True:
                live.update(build_table())
                await asyncio.sleep(0.25)

        loop = asyncio.get_event_loop()
        loop.create_task(refresh_live())
        loop.run_until_complete(run(server_ip, str(server_port)))
    finally:
        live.stop()
