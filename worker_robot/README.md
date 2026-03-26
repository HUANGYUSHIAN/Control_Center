# worker_robot

## 建議環境
- Python `3.10` 或 `3.11`

## 安裝
```bash
cd /mnt/c/Users/huang/Desktop/TMUI/worker_robot
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
- 使用 PyBullet headless (DIRECT) 載入 `plane.urdf` 與 `franka_panda/panda.urdf`
- 模擬時間持續推進，且每 5 秒更新一次隨機目標關節角
- `digital` 訂閱時以 FPS=10 傳送模擬畫面
- `robot_status` 訂閱時先送關節名稱，後續以固定頻率更新角度

## I/O（請用 Isaac Sim humanoid robot 串接取代）

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

### Replace（何處要替換）
- 目前模擬/渲染/關節讀取都在 `worker_robot/main.py` 內：
  - PyBullet 模擬：`sim_loop`、`randomize_targets`、`apply_targets`
  - 畫面渲染：`capture_frame`
  - 關節角度讀取：`get_joint_values`
- 你應該改成你的 Isaac Sim 人形機器人：
  - 讀取 articulation/joint angles
  - 從相機或 render 取得影像並回填 `frame.image`

## Resource Monitor
- `rich` 固定區塊會顯示：
  - RAM 使用量（平均/峰值）
  - GPU 使用率（平均/峰值）
  - VRAM 使用量（平均/峰值）
- 若沒有 GPU 或 NVML 不可用，會顯示 `No GPU`，不會中斷程式。
