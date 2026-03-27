from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import random
import sys
import threading
import time
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
_log = logging.getLogger("tmui.worker_robot")

CAMERA_POS = np.array([1.0, 0.0, 7.5], dtype=np.float32)
CAMERA_ROT = np.array([0.0, 90.0, 0.0], dtype=np.float32)
DIGITAL_FPS = 4
STATUS_HZ = 2
FRAME_SIZE = (320, 320)  # width, height
JPEG_QUALITY = 45
RANDOM_MOVE_INTERVAL_STEPS = 24
SIM_STEP_HZ = 60

robot_state = {
    "server": "N/A",
    "digital_on": False,
    "status_on": False,
    "digital_frames": 0,
    "status_updates": 0,
    "dof_count": 0,
    "last_error": "",
}


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
    table = Table(title="worker_robot (Isaac) 即時狀態")
    table.add_column("項目")
    table.add_column("值")
    table.add_row("server", str(robot_state["server"]))
    table.add_row("DOF 數量", str(robot_state["dof_count"]))
    table.add_row("Digital 訂閱", "開啟" if robot_state["digital_on"] else "關閉")
    table.add_row("Status 訂閱", "開啟" if robot_state["status_on"] else "關閉")
    table.add_row("Digital frame", str(robot_state["digital_frames"]))
    table.add_row("Status 更新", str(robot_state["status_updates"]))
    if robot_state["last_error"]:
        table.add_row("最後錯誤", str(robot_state["last_error"]))
    table.add_row("RAM MB(avg/max)", f"{resource_monitor.ram_avg:.1f} / {resource_monitor.ram_max:.1f}")
    if resource_monitor.gpu_available:
        table.add_row("GPU %(avg/max)", f"{resource_monitor.gpu_avg:.1f} / {resource_monitor.gpu_max:.1f}")
        table.add_row("VRAM MB(avg/max)", f"{resource_monitor.vram_avg:.1f} / {resource_monitor.vram_max:.1f}")
    else:
        table.add_row("GPU", "No GPU")
        table.add_row("VRAM", "No GPU")
    return table


class IsaacRobotRuntime:
    def __init__(self) -> None:
        self._sim = None
        self._world = None
        self._robot = None
        self._camera = None
        self.dof_names: list[str] = []
        self._latest_frame_b64 = ""
        self._tick = 0
        self._last_capture_tick = -99999
        self._capture_every_ticks = max(1, int(SIM_STEP_HZ / DIGITAL_FPS))
        self._headless = os.environ.get("TMUI_ISAAC_HEADLESS", "1").strip() != "0"
        self._init_sim()

    def _init_sim(self) -> None:
        from isaacsim import SimulationApp

        self._sim = SimulationApp({"headless": self._headless})

        from omni.isaac.core import World
        import omni.isaac.core.utils.numpy.rotations as rot_utils
        from omni.isaac.core.robots import Robot
        from omni.isaac.core.utils.nucleus import get_assets_root_path
        from omni.isaac.core.utils.prims import add_reference_to_stage
        from omni.isaac.sensor import Camera

        self._world = World(stage_units_in_meters=1.0)
        self._world.scene.add_default_ground_plane()

        self._camera = Camera(
            prim_path="/World/camera",
            position=CAMERA_POS,
            resolution=FRAME_SIZE,
            orientation=rot_utils.euler_angles_to_quats(CAMERA_ROT, degrees=True),
        )

        assets_root = get_assets_root_path()
        asset_path = assets_root + "/Isaac/Robots/Unitree/A1/a1.usd"
        prim_path = "/World/A1"
        add_reference_to_stage(usd_path=asset_path, prim_path=prim_path)

        for _ in range(60):
            self._sim.update()

        self._robot = self._world.scene.add(Robot(prim_path=prim_path, name="my_a1"))
        self._world.reset()
        self._camera.initialize()

        self.dof_names = list(self._robot.dof_names)
        robot_state["dof_count"] = len(self.dof_names)
        _log.info("Isaac robot 載入完成，DOF=%s", robot_state["dof_count"])

    def step(self) -> None:
        if self._tick % RANDOM_MOVE_INTERVAL_STEPS == 0:
            target = np.random.uniform(-1.0, 1.0, size=self._robot.num_dof)
            self._robot.set_joint_positions(target)

        self._world.step(render=True)
        self._tick += 1

        if self._tick - self._last_capture_tick >= self._capture_every_ticks:
            self._sim.update()
            rgba_data = self._camera.get_rgba()
            if rgba_data is not None and rgba_data.ndim == 3:
                bgr = cv2.cvtColor(rgba_data[:, :, :3].astype(np.uint8), cv2.COLOR_RGB2BGR)
                ok, encoded = cv2.imencode(
                    ".jpg",
                    bgr,
                    [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY],
                )
                if ok:
                    self._latest_frame_b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
                    self._last_capture_tick = self._tick

    def get_latest_frame(self) -> str:
        return self._latest_frame_b64

    def get_joint_values(self) -> list[float]:
        return [float(v) for v in self._robot.get_joint_positions()]

    def close(self) -> None:
        if self._sim is not None:
            self._sim.close()
            self._sim = None


class SharedData:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.stop = False
        self.digital_on = False
        self.status_on = False
        self.latest_frame = ""
        self.joint_names: list[str] = []
        self.joint_values: list[float] = []


async def ws_worker(ip: str, port: str, shared: SharedData) -> None:
    uri = f"ws://{ip}:{port}/ws"
    sent_status_init = False
    while True:
        with shared.lock:
            if shared.stop:
                return
        try:
            async with websockets.connect(uri, open_timeout=8) as ws:
                await ws.send(json.dumps({"event": "register", "role": "worker_robot"}, ensure_ascii=False))
                await ws.recv()
                _log.info("worker_robot 註冊成功")
                sent_status_init = False

                async def recv_loop() -> None:
                    while True:
                        msg = json.loads(await ws.recv())
                        evt = msg.get("event")
                        view = msg.get("view")
                        if evt == "subscribe_view" and view == "digital":
                            with shared.lock:
                                shared.digital_on = True
                            await ws.send(
                                json.dumps({"event": "view_status", "view": "digital", "status": "streaming"}, ensure_ascii=False)
                            )
                        elif evt == "unsubscribe_view" and view == "digital":
                            with shared.lock:
                                shared.digital_on = False
                            await ws.send(
                                json.dumps({"event": "view_status", "view": "digital", "status": "idle"}, ensure_ascii=False)
                            )
                        elif evt == "subscribe_view" and view == "robot_status":
                            with shared.lock:
                                shared.status_on = True
                            await ws.send(
                                json.dumps({"event": "view_status", "view": "robot_status", "status": "streaming"}, ensure_ascii=False)
                            )
                        elif evt == "unsubscribe_view" and view == "robot_status":
                            with shared.lock:
                                shared.status_on = False
                            await ws.send(
                                json.dumps({"event": "view_status", "view": "robot_status", "status": "idle"}, ensure_ascii=False)
                            )

                async def digital_sender() -> None:
                    while True:
                        with shared.lock:
                            enabled = shared.digital_on
                            frame = shared.latest_frame
                        robot_state["digital_on"] = enabled
                        if enabled and frame:
                            await ws.send(json.dumps({"event": "frame", "view": "digital", "image": frame}, ensure_ascii=False))
                            robot_state["digital_frames"] += 1
                        await asyncio.sleep(1 / DIGITAL_FPS)

                async def status_sender() -> None:
                    nonlocal sent_status_init
                    while True:
                        with shared.lock:
                            enabled = shared.status_on
                            names = list(shared.joint_names)
                            vals = list(shared.joint_values)
                        robot_state["status_on"] = enabled
                        if enabled:
                            if not sent_status_init:
                                await ws.send(
                                    json.dumps(
                                        {"event": "robot_status_init", "view": "robot_status", "joints": names},
                                        ensure_ascii=False,
                                    )
                                )
                                sent_status_init = True
                            await ws.send(
                                json.dumps(
                                    {"event": "robot_status_update", "view": "robot_status", "angles": vals},
                                    ensure_ascii=False,
                                )
                            )
                            robot_state["status_updates"] += 1
                        else:
                            sent_status_init = False
                        await asyncio.sleep(1 / STATUS_HZ)

                tasks = [
                    asyncio.create_task(recv_loop()),
                    asyncio.create_task(digital_sender()),
                    asyncio.create_task(status_sender()),
                ]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for task in pending:
                    task.cancel()
                for task in done:
                    exc = task.exception()
                    if exc:
                        raise exc
        except Exception as exc:
            robot_state["last_error"] = str(exc)
            _log.exception("WebSocket 連線或處理失敗: %s", exc)
            await asyncio.sleep(2.0)


def ws_thread_main(ip: str, port: str, shared: SharedData) -> None:
    import asyncio

    asyncio.run(ws_worker(ip, port, shared))


if __name__ == "__main__":
    server_ip, server_port = resolve_server_endpoint("worker_robot")
    robot_state["server"] = f"{server_ip}:{server_port}"
    _log.info("使用 server -> %s", robot_state["server"])
    shared = SharedData()
    runtime = IsaacRobotRuntime()
    with shared.lock:
        shared.joint_names = list(runtime.dof_names)
        shared.joint_values = [0.0 for _ in runtime.dof_names]

    ws_thread = threading.Thread(
        target=ws_thread_main,
        args=(server_ip, str(server_port), shared),
        daemon=True,
    )
    ws_thread.start()

    live = Live(build_table(), console=console, refresh_per_second=4, transient=False)
    live.start(refresh=True)
    try:
        while True:
            runtime.step()
            with shared.lock:
                shared.joint_values = runtime.get_joint_values()
                shared.latest_frame = runtime.get_latest_frame()
                if shared.stop:
                    break
            live.update(build_table(), refresh=True)
            time.sleep(1 / SIM_STEP_HZ)
    except KeyboardInterrupt:
        pass
    finally:
        with shared.lock:
            shared.stop = True
        ws_thread.join(timeout=2.0)
        runtime.close()
        live.stop()
