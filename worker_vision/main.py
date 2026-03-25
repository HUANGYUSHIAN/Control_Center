from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import websockets
from rich.console import Console
from rich.live import Live
from rich.table import Table

console = Console()

state = {"subscribers": 0, "source_ok": False, "frame_count": 0}
latest_frame: np.ndarray | None = None


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


def build_table() -> Table:
    table = Table(title="worker_vision 高頻狀態")
    table.add_column("項目")
    table.add_column("值")
    table.add_row("影片來源", "正常" if state["source_ok"] else "使用假畫面")
    table.add_row("訂閱數", str(state["subscribers"]))
    table.add_row("已送 frame", str(state["frame_count"]))
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
            console.print(f"[green]{now_text()}[/green] worker_vision 註冊成功")

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
        console.print(f"[red]{now_text()}[/red] 連線逾時：{uri}")
        console.print(
            "[yellow]請確認 server IP 是否可達。若 server 跑在 WSL，172.x.x.x 通常只在該主機內可用，"
            "其他實體機請改用 Windows 主機內網 IP（例如 192.168.x.x）。[/yellow]"
        )
        raise


if __name__ == "__main__":
    server_ip = input("請輸入 server IP: ").strip()
    server_port = input("請輸入 server Port: ").strip()
    if not server_ip or not server_port:
        raise SystemExit("IP/Port 不能為空")
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
        loop.run_until_complete(run(server_ip, server_port))
    finally:
        live.stop()
