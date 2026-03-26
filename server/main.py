from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import socket
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import psutil
from rich.console import Console
from rich.live import Live
from rich.table import Table
import uvicorn
from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncZeroconf
try:
    import pynvml
except Exception:  # pragma: no cover - fallback when NVML package missing
    pynvml = None

from contracts import Event, Role

# Rich Live 需攔截 stdout/stderr（預設 True），否則 uvicorn / logging 直接寫終端會移動游標，
# Live 仍用「上移 N 行」重繪，游標錯位就會疊出多個表格。非 TTY（重導向）時勿強制 terminal。
console = Console(force_terminal=bool(sys.stdout.isatty()))


def _build_server_logger() -> logging.Logger:
    """將 server 日誌寫檔，避免干擾 Rich Live 單表格刷新。"""
    logger = logging.getLogger("tmui.server")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        log_path = os.path.join(os.path.dirname(__file__), "server.log")
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [tmui:%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(fh)
    logging.getLogger("zeroconf").setLevel(logging.WARNING)
    return logger


_server_log = _build_server_logger()


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


@dataclass
class RuntimeStats:
    connected_frontends: int = 0
    connected_workers: dict[str, bool] = field(
        default_factory=lambda: {
            Role.ACTPLAN: False,
            Role.VISION: False,
            Role.ROBOT: False,
        }
    )
    viewer_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    frame_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))


stats = RuntimeStats()
live_task: asyncio.Task | None = None
live: Live | None = None
SERVICE_TYPE = "_tmui-server._tcp.local."


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
        self._pid = os.getpid()
        self._proc = psutil.Process(self._pid)
        self._gpu_handle = None
        if pynvml is not None:
            try:
                pynvml.nvmlInit()
                if pynvml.nvmlDeviceGetCount() > 0:
                    self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    self.gpu_available = True
            except Exception:
                self.gpu_available = False

    def _update_running_avg(self, prev: float, value: float) -> float:
        return ((prev * self.samples) + value) / (self.samples + 1)

    def update(self) -> None:
        rss_mb = self._proc.memory_info().rss / (1024 * 1024)
        self.ram_avg = self._update_running_avg(self.ram_avg, rss_mb)
        self.ram_max = max(self.ram_max, rss_mb)
        if self.gpu_available and self._gpu_handle is not None:
            try:
                util = float(pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle).gpu)
                mem = pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                vram_mb = mem.used / (1024 * 1024)
                self.gpu_avg = self._update_running_avg(self.gpu_avg, util)
                self.gpu_max = max(self.gpu_max, util)
                self.vram_avg = self._update_running_avg(self.vram_avg, vram_mb)
                self.vram_max = max(self.vram_max, vram_mb)
            except Exception:
                self.gpu_available = False
        self.samples += 1

    def rows(self) -> list[tuple[str, str]]:
        out = [("RAM MB(avg/max)", f"{self.ram_avg:.1f} / {self.ram_max:.1f}")]
        if self.gpu_available:
            out.append(("GPU %(avg/max)", f"{self.gpu_avg:.1f} / {self.gpu_max:.1f}"))
            out.append(("VRAM MB(avg/max)", f"{self.vram_avg:.1f} / {self.vram_max:.1f}"))
        else:
            out.append(("GPU", "No GPU"))
            out.append(("VRAM", "No GPU"))
        return out


resource_monitor = ResourceMonitor()


def build_process_snapshot() -> dict[str, Any]:
    worker_rows = [
        (Role.ACTPLAN, "worker_actplan"),
        (Role.VISION, "worker_vision"),
        (Role.ROBOT, "worker_robot"),
    ]
    children: list[dict[str, Any]] = []
    for idx, (role_key, role_name) in enumerate(worker_rows, start=1):
        is_online = bool(stats.connected_workers.get(role_key, False))
        children.append(
            {
                "id": f"init-{idx}",
                "title": f"確認 {role_name} 連線",
                "progress": 100 if is_online else 0,
                "status": "已完成" if is_online else "等待中",
            }
        )
    overall = int(sum(c["progress"] for c in children) / len(children))
    run_state = "ready" if overall == 100 else "waiting"
    return {
        "event": Event.PROCESS_SNAPSHOT,
        "overallProgress": overall,
        "runState": run_state,
        "controlEnabled": False,
        "tasks": [{"id": "init", "title": "初始化", "children": children}],
    }


class Hub:
    def __init__(self) -> None:
        self.frontends: set[WebSocket] = set()
        self.workers: dict[str, WebSocket] = {}
        self.view_subscribers: dict[str, set[WebSocket]] = defaultdict(set)

    async def send_json(self, ws: WebSocket, payload: dict[str, Any]) -> None:
        await ws.send_text(json.dumps(payload, ensure_ascii=False))

    async def broadcast_frontend(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self.frontends:
            try:
                await self.send_json(ws, payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.frontends.discard(ws)

    async def broadcast_task_status(self, task_name: str, status: str, detail: str = "") -> None:
        payload = {
            "event": Event.TASK_STATUS,
            "time": now_text(),
            "task": task_name,
            "status": status,
            "detail": detail,
        }
        await self.broadcast_frontend(payload)

    async def frontend_view_switch(self, ws: WebSocket, next_view: str) -> None:
        for view_name in list(self.view_subscribers.keys()):
            if ws in self.view_subscribers[view_name]:
                self.view_subscribers[view_name].discard(ws)
                stats.viewer_count[view_name] = len(self.view_subscribers[view_name])
                await self.notify_worker_view(view_name, subscribe=False)
        if next_view:
            self.view_subscribers[next_view].add(ws)
            stats.viewer_count[next_view] = len(self.view_subscribers[next_view])
            await self.notify_worker_view(next_view, subscribe=True)

    async def notify_worker_view(self, view_name: str, subscribe: bool) -> None:
        worker_role = Role.ROBOT if view_name in {"digital", "robot_status"} else Role.VISION
        worker = self.workers.get(worker_role)
        if worker is None:
            await self.broadcast_task_status(f"{view_name}_stream", "失敗", f"{worker_role} 不在線")
            return
        evt = Event.SUBSCRIBE_VIEW if subscribe else Event.UNSUBSCRIBE_VIEW
        payload = {"event": evt, "view": view_name, "count": len(self.view_subscribers[view_name])}
        await self.send_json(worker, payload)
        action = "執行中" if subscribe else "已完成"
        await self.broadcast_task_status(f"{view_name}_stream", action, f"訂閱數={payload['count']}")

    async def route_command(self, text: str) -> None:
        worker = self.workers.get(Role.ACTPLAN)
        await self.broadcast_task_status("actplan", "等待中", "等待 worker_actplan")
        if worker is None:
            await self.broadcast_frontend(
                {"event": Event.COMMAND_REPLY, "role": "assistant", "text": "worker_actplan 未連線"}
            )
            await self.broadcast_task_status("actplan", "失敗", "worker_actplan 未連線")
            return
        await self.send_json(worker, {"event": Event.COMMAND_INPUT, "text": text})
        await self.broadcast_task_status("actplan", "執行中", "已轉派 worker_actplan")

    async def route_worker_payload(self, role: str, payload: dict[str, Any]) -> None:
        event = payload.get("event")
        if event == Event.COMMAND_REPLY:
            await self.broadcast_frontend(payload)
            await self.broadcast_task_status("actplan", "已完成", "回覆已送達")
            return
        if event == Event.FRAME:
            view = payload.get("view", "")
            stats.frame_count[view] += 1
            for ws in list(self.view_subscribers[view]):
                try:
                    await self.send_json(ws, payload)
                except Exception:
                    self.view_subscribers[view].discard(ws)
            return
        if event in {Event.ROBOT_STATUS_INIT, Event.ROBOT_STATUS_UPDATE, Event.VIEW_STATUS}:
            for ws in list(self.view_subscribers.get(payload.get("view", "robot_status"), set())):
                try:
                    await self.send_json(ws, payload)
                except Exception:
                    self.view_subscribers[payload.get("view", "robot_status")].discard(ws)
            return
        if event == Event.LOG:
            _server_log.info("[worker:%s] %s", role, payload.get("message", ""))


hub = Hub()


def build_live_table() -> Table:
    resource_monitor.update()
    table = Table(title="TMUI 即時狀態")
    table.add_column("項目")
    table.add_column("值")
    table.add_row("frontend 連線數", str(stats.connected_frontends))
    table.add_row("worker_actplan", "在線" if stats.connected_workers[Role.ACTPLAN] else "離線")
    table.add_row("worker_vision", "在線" if stats.connected_workers[Role.VISION] else "離線")
    table.add_row("worker_robot", "在線" if stats.connected_workers[Role.ROBOT] else "離線")
    table.add_row("digital 訂閱", str(stats.viewer_count["digital"]))
    table.add_row("camera 訂閱", str(stats.viewer_count["camera"]))
    table.add_row("robot_status 訂閱", str(stats.viewer_count["robot_status"]))
    table.add_row("digital frame", str(stats.frame_count["digital"]))
    table.add_row("camera frame", str(stats.frame_count["camera"]))
    for k, v in resource_monitor.rows():
        table.add_row(k, v)
    return table


async def live_refresher() -> None:
    global live
    # get_renderable：每次 refresh 重算表格；勿同時用手動 update + 內建 RefreshThread 雙重刷新。
    # redirect_* 預設 True，讓 uvicorn / print / logging 經 Rich，與 Live 的游標還原一致。
    live = Live(
        get_renderable=build_live_table,
        console=console,
        refresh_per_second=4,
        transient=False,
        redirect_stdout=True,
        redirect_stderr=True,
    )
    live.start(refresh=True)
    try:
        while True:
            await asyncio.sleep(0.5)
    finally:
        if live:
            live.stop()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global live_task
    live_task = asyncio.create_task(live_refresher())
    async_zc: AsyncZeroconf | None = None
    try:
        ip = get_local_ip()
        hostname = socket.gethostname()
        _server_log.info(
            "準備註冊 mDNS：get_local_ip()=%r hostname=%r；"
            "若 server 在 WSL2，此 IP 常為虛擬網段，其他實體機無法用 mDNS/TCP 連到該位址，"
            "請在 Windows 上查 Wi‑Fi 的區網 IP 給 worker，或讓 server 跑在原生 Linux/Windows。",
            ip,
            hostname,
        )
        async_zc = AsyncZeroconf()
        service_name = f"TMUI-Server-{hostname}.{SERVICE_TYPE}"
        zc_service = ServiceInfo(
            SERVICE_TYPE,
            service_name,
            addresses=[socket.inet_aton(ip)],
            port=8765,
            properties={"path": "/ws".encode()},
            server=f"{hostname}.local.",
        )
        _server_log.info(
            "mDNS ServiceInfo type=%r name=%r port=%s addresses=%r server=%r",
            SERVICE_TYPE,
            service_name,
            8765,
            [ip],
            zc_service.server,
        )
        broadcast = await async_zc.async_register_service(zc_service)
        await broadcast
        _server_log.info("mDNS 註冊完成，WebSocket: ws://%s:8765/ws", ip)
        _server_log.info(
            "Server 啟動完成: ws://%s:8765/ws；Workers 可於任意時間連線（晚於啟動亦可）",
            ip,
        )
    except Exception as exc:
        _server_log.warning("mDNS 註冊失敗（HTTP/WebSocket 仍會運作）: %s", exc, exc_info=True)
        if async_zc is not None:
            with contextlib.suppress(Exception):
                await async_zc.async_close()
            async_zc = None
    yield
    if live_task:
        live_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await live_task
    if async_zc is not None:
        with contextlib.suppress(Exception):
            await async_zc.async_close()


app = FastAPI(lifespan=lifespan, title="TMUI Server")


@app.websocket("/ws")
async def ws_entry(ws: WebSocket) -> None:
    await ws.accept()
    role = ""
    try:
        raw = await ws.receive_text()
        reg = json.loads(raw)
        if reg.get("event") != Event.REGISTER:
            await hub.send_json(ws, {"event": Event.ERROR, "message": "第一則訊息必須是 register"})
            await ws.close()
            return
        role = reg.get("role", "")
        await hub.send_json(ws, {"event": Event.REGISTER_ACK, "role": role})
        _server_log.info("接收 WebSocket 連線 role=%s", role)

        if role == Role.FRONTEND:
            hub.frontends.add(ws)
            stats.connected_frontends = len(hub.frontends)
            await hub.send_json(ws, build_process_snapshot())
        else:
            hub.workers[role] = ws
            if role in stats.connected_workers:
                stats.connected_workers[role] = True
                await hub.broadcast_frontend(build_process_snapshot())
                if all(stats.connected_workers.values()):
                    await hub.broadcast_task_status("初始化", "已完成", "三個 worker 已連線")
                else:
                    await hub.broadcast_task_status("初始化", "執行中", f"{role} 已連線")

        while True:
            data = await ws.receive_text()
            payload = json.loads(data)
            event = payload.get("event")
            if event == Event.HEARTBEAT:
                continue
            if role == Role.FRONTEND:
                if event == Event.SUBSCRIBE_VIEW:
                    await hub.frontend_view_switch(ws, payload.get("view", ""))
                elif event == Event.UNSUBSCRIBE_VIEW:
                    await hub.frontend_view_switch(ws, "")
                elif event == Event.COMMAND_INPUT:
                    await hub.route_command(payload.get("text", ""))
                elif event == Event.PROCESS_CONTROL:
                    await hub.send_json(ws, {"event": Event.ERROR, "message": "目前僅支援初始化流程，尚未開放手動流程控制"})
                else:
                    await hub.send_json(ws, {"event": Event.ERROR, "message": f"未知事件 {event}"})
            else:
                await hub.route_worker_payload(role, payload)
    except WebSocketDisconnect:
        _server_log.info("WebSocket 連線中斷 role=%s", role)
    except Exception as exc:
        _server_log.exception("WebSocket 處理錯誤 role=%s", role)
    finally:
        if role == Role.FRONTEND:
            hub.frontends.discard(ws)
            stats.connected_frontends = len(hub.frontends)
            await hub.frontend_view_switch(ws, "")
        elif role:
            if hub.workers.get(role) is ws:
                del hub.workers[role]
            if role in stats.connected_workers:
                stats.connected_workers[role] = False
                await hub.broadcast_frontend(build_process_snapshot())
                await hub.broadcast_task_status("初始化", "等待中", f"{role} 離線，等待重連")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8765,
        reload=False,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
