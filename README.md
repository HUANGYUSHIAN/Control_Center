# TMUI Intranet Robot Workspace

此專案由三部分組成：

- `server`：FastAPI WebSocket 中樞（負責 worker 註冊、任務狀態與串流/訂閱轉發）
- `worker_actplan`：負責處理自然語言指令（示範：2 秒延遲後回覆字串前半）
- `worker_vision`：負責視覺串流（示範：背景影片循環、灰階低解析度、FPS=10）
- `worker_robot`：負責模擬機器人（示範：PyBullet headless、Digital View 與 Robot status 更新）
- `frontend`：React + MUI 控制介面（連線、顯示 Digital/Camera/Robot Status、指令對話）

---

## 1) 建議安裝準備

- Python：建議 `3.10` 或 `3.11`
- Node.js：建議最新版 LTS（例如 Node 18+）
- 第一次執行前，請先照各子資料夾自己的 `README.md` 安裝依賴與啟動（本 README 會用「請參考」精簡表示）。

---

## 2) 啟動順序（驗證最穩）

1. 啟動 `server`
   - 請參考：`server/README.md`
2. 啟動 `worker_actplan`
   - 請參考：`worker_actplan/README.md`
3. 啟動 `worker_vision`
   - 請參考：`worker_vision/README.md`
4. 啟動 `worker_robot`
   - 請參考：`worker_robot/README.md`
5. 啟動 `frontend`
   - 在 `frontend` 目錄：
     - `npm install`
     - `npm run dev -- --host 0.0.0.0 --port 5173`

---

## 3) 測試流程

1. 待 `server` 與 3 個 worker 都連線穩定後，使用瀏覽器打開：
   - `http://localhost:5173/`
   - 或內網：`http://<你的內網IP>:5173/`
2. 瀏覽器頁面會自動連到 `ws://<目前頁面所在主機>:8765/ws`
3. Display Board 內切換 `Digital View / Camera View / Robot Status`，觀察畫面與 Robot status 更新。

---

## 4) 內網/跨主機連線偵錯

若你遇到 worker 無法連線、或瀏覽器可開但 worker 連不上，請先看：
- `connection.md`

該文件提供 Windows / Linux / WSL 下如何開放與測試 `8765`（含 `netsh interface portproxy` 與防火牆規則範本）。

