# TMUI Frontend

## 安裝與啟動
```bash
cd /mnt/c/Users/huang/Desktop/TMUI/frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

可用 `http://<你的內網IP>:5173` 讓同網域使用者操作。

## 介面功能
- 三欄布局：`Process Board`、`Display Board`、`Command Board`
- Display Board 三個 tab：
  - `Digital View`（worker_robot 影像）
  - `Camera View`（worker_vision 影像）
  - `Robot Status`（關節角度）
- 切換 tab 會先停止舊視圖再啟動新視圖（無需額外按鈕）
- Command Board 支援語音轉文字草稿（不自動送出）
- 右上角可切換是否顯示各 board log

## 前置條件
- 先啟動 server (`python3 main.py`)
- worker 可選擇啟動；若缺少某 worker，前端會顯示黑畫面或無狀態，而非整體崩潰

## 除錯
- 連不上 server：確認 `ws://<frontend主機IP>:8765/ws` 可達
- Camera 黑畫面：確認 worker_vision 已啟動
- Robot status 無資料：確認 worker_robot 已啟動
