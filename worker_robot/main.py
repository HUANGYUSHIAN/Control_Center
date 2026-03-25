from __future__ import annotations

import asyncio
import base64
import json
import math
import random
from datetime import datetime

import cv2
import numpy as np
import pybullet as p
import pybullet_data
import websockets
from rich.console import Console
from rich.live import Live
from rich.table import Table

console = Console()

robot_state = {"digital_on": False, "status_on": False, "digital_frames": 0, "status_updates": 0}
joint_names: list[str] = []
joint_indices: list[int] = []
joint_targets: dict[int, float] = {}


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


def build_table() -> Table:
    table = Table(title="worker_robot 高頻狀態")
    table.add_column("項目")
    table.add_column("值")
    table.add_row("Digital 訂閱", "開啟" if robot_state["digital_on"] else "關閉")
    table.add_row("Status 訂閱", "開啟" if robot_state["status_on"] else "關閉")
    table.add_row("Digital frame", str(robot_state["digital_frames"]))
    table.add_row("Status 更新", str(robot_state["status_updates"]))
    return table


def init_sim() -> int:
    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0, 0, -9.8)
    p.loadURDF("plane.urdf")
    robot = p.loadURDF("franka_panda/panda.urdf", useFixedBase=True)
    for i in range(p.getNumJoints(robot)):
        info = p.getJointInfo(robot, i)
        if info[2] == p.JOINT_REVOLUTE:
            joint_indices.append(i)
            joint_names.append(info[1].decode("utf-8"))
            joint_targets[i] = 0.0
    return robot


def randomize_targets() -> None:
    for idx in joint_indices:
        joint_targets[idx] = random.uniform(-math.pi / 2, math.pi / 2)


def apply_targets(robot: int) -> None:
    for idx in joint_indices:
        p.setJointMotorControl2(robot, idx, p.POSITION_CONTROL, targetPosition=joint_targets[idx], force=120)


def capture_frame(width: int = 480, height: int = 270) -> str:
    view = p.computeViewMatrixFromYawPitchRoll([0.4, 0.0, 0.3], 1.4, 35, -30, 0, 2)
    proj = p.computeProjectionMatrixFOV(60, width / height, 0.1, 10)
    _, _, rgba, _, _ = p.getCameraImage(width, height, view, proj, renderer=p.ER_TINY_RENDERER)
    arr = np.array(rgba, dtype=np.uint8).reshape(height, width, 4)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
    if not ok:
        return ""
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def get_joint_values(robot: int) -> list[float]:
    return [p.getJointState(robot, idx)[0] for idx in joint_indices]


async def run(ip: str, port: str) -> None:
    robot = init_sim()
    uri = f"ws://{ip}:{port}/ws"
    async with websockets.connect(uri) as ws:
        # ==========================================================
        # I/O CONTRACT (with TMUI server)
        # ==========================================================
        # Input from server (frontend subscription):
        #   {"event":"subscribe_view","view":"digital"}
        #   {"event":"subscribe_view","view":"robot_status"}
        #
        # Output to server (forwarded to frontend subscribers):
        #   - For digital view:
        #       {"event":"frame","view":"digital","image":"<base64_jpeg>"}
        #   - For robot status:
        #       {"event":"robot_status_init","view":"robot_status","joints":[...]}
        #       {"event":"robot_status_update","view":"robot_status","angles":[...]}
        #
        # This module is currently a PyBullet placeholder.
        # Replace the simulation + capture code with your Isaac Sim humanoid robot integration.
        await ws.send(json.dumps({"event": "register", "role": "worker_robot"}, ensure_ascii=False))
        await ws.recv()
        console.print(f"[green]{now_text()}[/green] worker_robot 註冊成功")

        async def sim_loop() -> None:
            tick = 0
            while True:
                if tick % 50 == 0:  # 5秒一次，模擬步進頻率10Hz
                    randomize_targets()
                apply_targets(robot)
                p.stepSimulation()
                tick += 1
                await asyncio.sleep(0.1)

        async def digital_sender() -> None:
            while True:
                if robot_state["digital_on"]:
                    # When digital view is subscribed, keep sending frames.
                    # For the final system, replace capture_frame() with your Isaac Sim
                    # camera render (or any image stream/visualization you want to show).
                    await ws.send(json.dumps({"event": "frame", "view": "digital", "image": capture_frame()}, ensure_ascii=False))
                    robot_state["digital_frames"] += 1
                await asyncio.sleep(0.1)  # FPS=10

        async def status_sender() -> None:
            sent_init = False
            while True:
                if robot_state["status_on"]:
                    if not sent_init:
                        # Send joint names once at the start of robot_status subscription.
                        # For Isaac Sim, map your robot's joint naming to this `joints` list.
                        await ws.send(
                            json.dumps(
                                {"event": "robot_status_init", "view": "robot_status", "joints": joint_names},
                                ensure_ascii=False,
                            )
                        )
                        sent_init = True
                    # Then periodically send current joint angles.
                    # For Isaac Sim, replace get_joint_values() with your articulation/joint angles readout.
                    await ws.send(
                        json.dumps(
                            {"event": "robot_status_update", "view": "robot_status", "angles": get_joint_values(robot)},
                            ensure_ascii=False,
                        )
                    )
                    robot_state["status_updates"] += 1
                else:
                    sent_init = False
                await asyncio.sleep(1 / 6)

        tasks = [asyncio.create_task(sim_loop()), asyncio.create_task(digital_sender()), asyncio.create_task(status_sender())]
        try:
            while True:
                msg = json.loads(await ws.recv())
                evt = msg.get("event")
                view = msg.get("view")
                if evt == "subscribe_view" and view == "digital":
                    robot_state["digital_on"] = True
                    await ws.send(json.dumps({"event": "view_status", "view": "digital", "status": "streaming"}, ensure_ascii=False))
                elif evt == "unsubscribe_view" and view == "digital":
                    robot_state["digital_on"] = False
                    await ws.send(json.dumps({"event": "view_status", "view": "digital", "status": "idle"}, ensure_ascii=False))
                elif evt == "subscribe_view" and view == "robot_status":
                    robot_state["status_on"] = True
                    await ws.send(json.dumps({"event": "view_status", "view": "robot_status", "status": "streaming"}, ensure_ascii=False))
                elif evt == "unsubscribe_view" and view == "robot_status":
                    robot_state["status_on"] = False
                    await ws.send(json.dumps({"event": "view_status", "view": "robot_status", "status": "idle"}, ensure_ascii=False))
        finally:
            for task in tasks:
                task.cancel()
            p.disconnect()


if __name__ == "__main__":
    server_ip = input("請輸入 server IP: ").strip()
    server_port = input("請輸入 server Port: ").strip()
    if not server_ip or not server_port:
        raise SystemExit("IP/Port 不能為空")

    live = Live(build_table(), console=console, refresh_per_second=4)
    live.start()
    try:
        async def refresh_live() -> None:
            while True:
                live.update(build_table())
                await asyncio.sleep(0.25)

        loop = asyncio.get_event_loop()
        loop.create_task(refresh_live())
        loop.run_until_complete(run(server_ip, server_port))
    finally:
        live.stop()
