from __future__ import annotations

import asyncio
import json
from datetime import datetime

import websockets
from rich.console import Console

console = Console()


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


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
    except Exception as exc:
        console.print(f"[red]{now_text()}[/red] 連線失敗或中斷: {exc}")


if __name__ == "__main__":
    server_ip = input("請輸入 server IP: ").strip()
    server_port = input("請輸入 server Port: ").strip()
    if not server_ip or not server_port:
        raise SystemExit("IP/Port 不能為空")
    asyncio.run(run(server_ip, server_port))
