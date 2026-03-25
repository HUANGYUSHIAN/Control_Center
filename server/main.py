from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from rich.console import Console
from rich.live import Live
from rich.table import Table
import uvicorn

from contracts import Event, Role

console = Console()
app = FastAPI(title="TMUI Server")


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
            console.print(f"[cyan][worker:{role}][/cyan] {payload.get('message', '')}")


hub = Hub()


def build_live_table() -> Table:
    table = Table(title="TMUI 即時狀態（高頻刷新）")
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
    return table


async def live_refresher() -> None:
    global live
    live = Live(build_live_table(), console=console, refresh_per_second=4)
    live.start()
    try:
        while True:
            if live:
                live.update(build_live_table())
            await asyncio.sleep(0.25)
    finally:
        if live:
            live.stop()


@app.on_event("startup")
async def on_startup() -> None:
    global live_task
    live_task = asyncio.create_task(live_refresher())
    ip = get_local_ip()
    console.print(f"[green]Server 啟動完成: ws://{ip}:8765/ws[/green]")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if live_task:
        live_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await live_task


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
        console.print(f"[yellow]接收連線[/yellow] role={role}")

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
        console.print(f"[red]連線中斷[/red] role={role}")
    except Exception as exc:
        console.print(f"[red]處理錯誤[/red] role={role}, error={exc}")
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
    uvicorn.run("main:app", host="0.0.0.0", port=8765, reload=False)
