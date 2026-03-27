# worker_robot

## 建議環境
- 使用你已可成功執行 `isaac_main.py` 的 Isaac Sim Python 環境
- 不要覆蓋既有 Isaac / OpenCV 套件版本

## 安裝
```bash
cd /mnt/c/Users/huang/Desktop/TMUI/worker_robot
# 啟用你既有可跑 Isaac 的環境（範例）
source .venv/bin/activate

# 只補「缺少」的 TMUI 通訊套件，不要動既有 isaac/opencv 版本
python -c "import websockets,rich,zeroconf,psutil" || pip install websockets rich zeroconf psutil nvidia-ml-py3
```

## 啟動
```bash
python3 main.py
```

不需要輸入 server IP/port。啟動時會：
- 先嘗試同機 loopback（`127.0.0.1:8765`、`localhost:8765`）
- 若同機找不到，改用 Zeroconf 自動搜尋內網 server

## 行為（Isaac Sim）
- 使用 `isaac_main.py` 同一套場景與機器人來源：
  - `World + ground plane`
  - `Unitree A1`（`/Isaac/Robots/Unitree/A1/a1.usd`）
  - 相機在 `/World/camera`
- `digital` 訂閱時傳送壓縮影像（預設較低負載：`320x320`, JPEG quality `45`, 約 `4 FPS`）
- `robot_status` 訂閱時先送一次 joints，再以較低頻率更新角度（約 `2 Hz`）
- 不寫影像檔案、不在終端列印關節明細；終端以 rich 狀態表為主，持續運行不設時限

## I/O

### Input（由 TMUI server 送入）
- WebSocket JSON：
  - `event`: `"subscribe_view"`，`view`: `"digital"`
  - `event`: `"subscribe_view"`，`view`: `"robot_status"`
  - 停止訂閱時會送：`event`: `"unsubscribe_view"`

### Output（回傳給 TMUI server，再由 server 轉發給前端）
- 當 `digital` 訂閱時持續輸出：
  - `event`: `"frame"`
  - `view`: `"digital"`
  - `image`: `<base64_jpeg>`
- 當 `robot_status` 訂閱時：
  - 初次送一次 joint names：
    - `event`: `"robot_status_init"`
    - `view`: `"robot_status"`
    - `joints`: `[...joint names...]`
  - 之後固定頻率送角度：
    - `event`: `"robot_status_update"`
    - `view`: `"robot_status"`
    - `angles`: `[...angles...]`

### 備註
- 目前 `main.py` 已改為 Isaac Sim 版本（不再使用 PyBullet）。
- 若要調整傳輸負載，可在 `main.py` 內調整：
  - `DIGITAL_FPS`
  - `FRAME_SIZE`
  - `JPEG_QUALITY`
  - `STATUS_HZ`

## Resource Monitor
- `rich` 固定區塊會顯示：
  - RAM 使用量（平均/峰值）
  - GPU 使用率（平均/峰值）
  - VRAM 使用量（平均/峰值）
- 若沒有 GPU 或 NVML 不可用，會顯示 `No GPU`，不會中斷程式。
