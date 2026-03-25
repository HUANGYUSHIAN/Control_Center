# worker_actplan

## 建議環境
- Python `3.10` 或 `3.11`

## 安裝
```bash
cd /mnt/c/Users/huang/Desktop/TMUI/worker_actplan
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 啟動
```bash
python3 main.py
```

依序輸入 server IP 與 port。若無法連線會直接結束。

## 行為
- 收到 `command_input` 後等待 2 秒
- 回傳輸入字串前半段作為 `command_reply`

## I/O（請替換 mock 以串你的 LLM Action Planner）

### Input（由 TMUI server 送入）
- WebSocket JSON：
  - `event`: `"command_input"`
  - `text`: 使用者自然語言指令（string）

### Output（回傳給 TMUI server）
- WebSocket JSON：
  - `event`: `"command_reply"`
  - `role`: `"assistant"`
  - `text`: 你的 action planner 產生的回覆（string）

### Replace（何處要替換）
- 目前的 mock 在 `worker_actplan/main.py` 內：
  - `await asyncio.sleep(2)`
  - `reply = text[: len(text) // 2]`
- 你需要把以上兩段替換成呼叫你的 LLM action planner module（例如 `reply = your_llm(text)`）。
