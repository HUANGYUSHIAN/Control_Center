from __future__ import annotations

import asyncio
import base64
import json
import logging
import sys
from datetime import datetime
import os
from pathlib import Path

import cv2
import numpy as np
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

state = {"subscribers": 0, "source_ok": False, "frame_count": 0}
latest_frame: np.ndarray | None = None
state["server"] = "N/A"
_log = logging.getLogger("tmui.worker_vision")


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


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


def build_table() -> Table:
    resource_monitor.update()
    table = Table(title="worker_vision 高頻狀態")
    table.add_column("項目")
    table.add_column("值")
    table.add_row("server", str(state["server"]))
    table.add_row("影片來源", "正常" if state["source_ok"] else "使用假畫面")
    table.add_row("訂閱數", str(state["subscribers"]))
    table.add_row("已送 frame", str(state["frame_count"]))
    table.add_row("RAM MB(avg/max)", f"{resource_monitor.ram_avg:.1f} / {resource_monitor.ram_max:.1f}")
    if resource_monitor.gpu_available:
        table.add_row("GPU %(avg/max)", f"{resource_monitor.gpu_avg:.1f} / {resource_monitor.gpu_max:.1f}")
        table.add_row("VRAM MB(avg/max)", f"{resource_monitor.vram_avg:.1f} / {resource_monitor.vram_max:.1f}")
    else:
        table.add_row("GPU", "No GPU")
        table.add_row("VRAM", "No GPU")
    return table


def pick_video_file() -> str | None:
    root = Path(__file__).parent / "file"
    for ext in ("*.mp4", "*.avi", "*.mov", "*.mkv"):
        files = list(root.glob(ext))
        if files:
            return str(files[0])
    return None


async def playback_loop() -> None:
    global latest_frame
    video_path = pick_video_file()
    cap = cv2.VideoCapture(video_path) if video_path else None
    state["source_ok"] = bool(cap and cap.isOpened())
    tick = 0
    while True:
        frame = None
        if cap and cap.isOpened():
            ok, raw = cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            frame = raw
        else:
            img = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(img, "worker_vision fallback", (40, 180), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            cv2.putText(img, f"tick={tick}", (40, 230), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 2)
            tick += 1
            frame = img
        latest_frame = frame
        await asyncio.sleep(0.03)


def encode_gray_frame(frame: np.ndarray) -> str:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (480, 270), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
    if not ok:
        return ""
    return base64.b64encode(encoded.tobytes()).decode("ascii")


async def run(ip: str, port: str) -> None:
    uri = f"ws://{ip}:{port}/ws"
    try:
        # ==========================================================
        # I/O CONTRACT (with TMUI server)
        # ==========================================================
        # Input from server:
        #   {"event":"subscribe_view","view":"camera"}
        #   {"event":"unsubscribe_view","view":"camera"}
        #
        # Output to server (then forwarded to frontend):
        #   {"event":"frame","view":"camera","image":"<base64_jpeg_or_gray>"}
        #
        # This module is currently a fallback video -> grayscale placeholder.
        # Replace it with your real vision system streaming:
        # - When camera is subscribed: start your camera/vision pipeline
        # - Render/encode the desired visualization frames to base64 JPEG
        # - When unsubscribed: stop sending frames (closing the stream)
        #
        # For this stage, you only need to send the `frame` image stream.
        # Spatial data / localization / other metadata are not required yet.
        ws_conn = websockets.connect(uri, open_timeout=8)
        async with ws_conn as ws:
            await ws.send(json.dumps({"event": "register", "role": "worker_vision"}, ensure_ascii=False))
            await ws.recv()
            _log.info("worker_vision 註冊成功")

            send_enabled = False

            async def sender() -> None:
                nonlocal send_enabled
                while True:
                    if send_enabled and latest_frame is not None:
                        # Replace encode_gray_frame(latest_frame) with your vision
                        # visualization/overlay output (e.g. object recognition results).
                        payload = {"event": "frame", "view": "camera", "image": encode_gray_frame(latest_frame)}
                        await ws.send(json.dumps(payload, ensure_ascii=False))
                        state["frame_count"] += 1
                    await asyncio.sleep(0.1)  # FPS=10

            send_task = asyncio.create_task(sender())
            try:
                while True:
                    msg = json.loads(await ws.recv())
                    evt = msg.get("event")
                    if evt == "subscribe_view" and msg.get("view") == "camera":
                        send_enabled = True
                        state["subscribers"] = msg.get("count", 1)
                        await ws.send(
                            json.dumps({"event": "view_status", "view": "camera", "status": "streaming"}, ensure_ascii=False)
                        )
                    elif evt == "unsubscribe_view" and msg.get("view") == "camera":
                        send_enabled = False
                        state["subscribers"] = msg.get("count", 0)
                        await ws.send(json.dumps({"event": "view_status", "view": "camera", "status": "idle"}, ensure_ascii=False))
            finally:
                send_task.cancel()
    except TimeoutError:
        _log.error("連線逾時：%s", uri)
        _log.warning(
            "請確認 server IP 是否可達。若 server 跑在 WSL，172.x.x.x 通常只在該主機內可用，"
            "其他實體機請改用 Windows 主機內網 IP（例如 192.168.x.x）。"
        )
        raise


if __name__ == "__main__":
    server_ip, server_port = resolve_server_endpoint("worker_vision")
    state["server"] = f"{server_ip}:{server_port}"
    _log.info("使用 server -> %s", state["server"])
    loop = asyncio.get_event_loop()
    loop.create_task(playback_loop())
    live = Live(build_table(), console=console, refresh_per_second=4)
    live.start()
    try:
        async def refresh_live() -> None:
            while True:
                live.update(build_table())
                await asyncio.sleep(0.25)

        loop.create_task(refresh_live())
        loop.run_until_complete(run(server_ip, str(server_port)))
    finally:
        live.stop()
