1. 請建立一個python server在/server中，能夠在WSL利用python3 main.py執行server。Server會不斷地循環播放/server/file的影片，並開啟特定的port，一旦有人透過內往指定server的IP與port，以WebSocket連線進來請求stream，建立SFU (Selective Forwarding Unit) - 轉發模式把影像持續發送過去，直到沒有人再接收資料時才關閉SFU。SFU要確保Python Server 只上傳 1 份 串流給伺服器，伺服器再像「郵局」一樣，把這份數據包複製並轉發給 B, C, D...。註解請用繁體中文解釋哪個部分處理那些任務，並及時print狀態包含"接收甚麼請求"、"處理甚麼情況"、"狀態如何"、連線人數等等方便例如內網video stream出事(例如防火牆等問題)，能debug。你必須要有個readme教我如何創建環境(環境名稱不用寫，但是要評估適合的python version，給我terminal command創建&install)

2. 請用React+MaterialUI設計一個簡單前端網頁放在/frontend，前端使用npm run dev即可打開，輸入python server的IP與Port後能夠WebSocket建立連線，發起video streaming的請求透過SFU把循環播放的影片呈現在影片播放框上。你不用npm install而是把package寫好讓我自己npm install，並有追蹤code確認websocket, SFU等狀態，以及readme教我如何使用與偵錯

3. 影片建議畫質降低，同時降低FPS以節省SFU資源，確保streaming穩定且不會觸發防火牆或安全性問題

4. 請修正/server/main.py，使用rich讓SFU正在轉發...的能在固定地方不斷刷新，其餘資訊正常列印

