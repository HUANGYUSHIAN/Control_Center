# worker_vision

## 建議環境
- Python `3.10` 或 `3.11`

## 安裝
```bash
cd /mnt/c/Users/huang/Desktop/TMUI/worker_vision
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 啟動
```bash
python3 main.py
```

不需要輸入 server IP/port。啟動時會：
- 先嘗試同機 loopback（`127.0.0.1:8765`、`localhost:8765`）
- 若同機找不到，改用 Zeroconf 自動搜尋內網 server

## 行為
- 背景持續循環讀取 `worker_vision/file` 影片
- 有 `camera` 訂閱時開始送出灰階、低解析度、FPS=10 的 frame
- 沒有訂閱時停止送 frame，但背景播放不中斷
- 若沒有影片檔，會自動改為 fallback 假畫面

## I/O（請替換成你的 Vision System 串流）

### Input（由 TMUI server 送入）
- WebSocket JSON：
  - `event`: `"subscribe_view"`，`view`: `"camera"`
  - `event`: `"unsubscribe_view"`，`view`: `"camera"`

### Output（回傳給 TMUI server，再由 server 轉發給前端）
- 當 camera 被訂閱時，持續送出：
  - `event`: `"frame"`
  - `view`: `"camera"`
  - `image`: `<base64 string>`（建議用你視覺輸出的影像/疊圖後結果，編成 base64 JPEG）

### Replace（哪些要換）
- 目前 placeholder 做法（請替換）：
  - `worker_vision/file` 影片讀取與背景播放
  - `encode_gray_frame()` 的灰階低解析度編碼
- 你應該在 `camera` 訂閱時：
  - 啟動你的 camera/vision pipeline
  - 產出你想在 Camera View 展示的影像（例如：即時物件辨識結果疊圖、其他視覺 streaming）
  - 將影像編碼成 `frame.image` 回傳

### 不需要（此階段）
- 空間定位/座標/其他 metadata（例如 spatial data / localization 等）此階段可不送。

## Resource Monitor
- `rich` 固定區塊會顯示：
  - RAM 使用量（平均/峰值）
  - GPU 使用率（平均/峰值）
  - VRAM 使用量（平均/峰值）
- 若沒有 GPU 或 NVML 不可用，會顯示 `No GPU`，不會中斷程式。
