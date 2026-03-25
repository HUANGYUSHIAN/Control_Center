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

依序輸入 server IP 與 port。

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
