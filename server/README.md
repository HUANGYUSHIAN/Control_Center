# TMUI Python Server

## 建議環境
- Python `3.10` 或 `3.11`（建議 `3.11`）
- WSL Ubuntu 或 Linux

## 建立環境與安裝
```bash
cd /mnt/c/Users/huang/Desktop/TMUI/server
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

## 啟動
```bash
python3 main.py
```

啟動後會印出 `ws://<server-ip>:8765/ws`，並透過 Zeroconf 在內網註冊服務，讓 workers 可自動發現。

## 功能摘要
- 接收 frontend 與三個 worker 的 WebSocket 連線
- 透過 Zeroconf 註冊 server（`_tmui-server._tcp.local.`）
- 任務狀態推送（等待中/執行中/已完成/失敗）
- 單一 worker 來源，多 frontend 訂閱的 SFU 轉發
- 高頻資訊用 `rich` 固定區塊刷新
- `rich` 固定區塊包含 RAM/GPU/VRAM 使用率（平均/峰值；若無 GPU 會顯示 No GPU）

## 除錯重點
- 若 frontend 黑畫面：先看對應 worker 是否在線
- 若指令無回覆：確認 `worker_actplan` 是否成功註冊
- 若 camera 無畫面：確認 `worker_vision/file` 是否有影片，沒有會用 fallback 假畫面
