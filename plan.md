<計畫背景>
本project欲建立一個內網工作站，Computer A執行python server (/server)與前端瀏覽器 (/frontend),讓任何使用者能使用前端瀏覽器check機器人工作狀態(包含瀏覽機器人video streaming與狀態文字)，也能夠以NL控制機器人從事特定任務，python server會把任務依照性質包裝給各個worker，包含負責模擬機器人動作的simulation core (/worker_robot using pybullet/isaac sim)，以LLM處理NL指令並編輯機器人動作流程的action planner (/worker_actplan)以及把Camera影像作影像辨識、定位等處理的vision系統 (/worker_vision),目前worker的部份外包出去，這邊僅需簡單demo即可，例如camera畫面改成直接播放影片

<1.前端瀏覽器 (請實作於/frontend)>
1.1. 使用React+MaterialUI開發前端網頁，視窗根據螢幕大小切分成三等份，由左至右分別是Process Board, Display Board以及Commnad Board，三個Board下方有各自的log能顯示包含連線狀態等資訊，有各自的sliders能夠上下查看log日誌方便除錯，畫面右上角有個icon能選擇是否呈現log。由於frontend與python server會再同一台電腦執行，無須輸入python server所在的IP與Port，我會先run python3 main.py再run npm run dev，你需要自己找到同台電腦正在執行的python server
1.2. Process Board呈現任務執行狀態，與python server建立WebSocket，主要的顯示的訊息為<時間> <任務名稱> <狀態>，其中狀態包含等待中、執行中、已完成以及失敗，任務名稱與狀態由python server判定。
1.3. Display Board有三個Tabs能做切換，分別是Digital View(顯示機器人與環境的整個Digital Twin), Camera View (顯示相機視角包含物件辨識等), Robot status(顯示機器人個關節角度等)。Digital View要去跟python server找worker_robot建立WebSocket，將機器人影像透過SFU發送出來，在Digital View呈現； Camera View 則是要去跟python server找worker_vision建立WebSocket，將Camera影像透過SFU發送出來，在Camera View呈現；Robot status則是要去跟python server找worker_robot建立WebSocket，把當前模擬的關節名稱、當前角度等資訊即時display在Robot status上。在Display Board中，default會是Digital View，一旦切換到何種View或是status，先斷開前一個View或是status的WebSocket後，自動建立新的WebSocket並自動開始串流，不需要任何button。例如從Camera View切換到Digital View時，Camera View先發送結束任務的資訊然後斷開對應的WebSocket，之後才建立Digital View所需要的Socket，最後促使worker自動開啟SFU開啟影像串流呈現於前端。
1.4. Commnad Board會是一個對話框，輸入框在底部有個語音輸入icon與發送icon，使用者click語音時用react-speech-recognition把語音即時轉成文字更新在輸入框但是不要輸出，而是讓使用者可以double check完再輸出。Commnad Board會透過Python Server與worker_actplan建立WebSocket，把文字送入後取得replies訊息呈現於對話框中，使用者輸入內容置右對齊，worker_actplan的reply置左對齊，模擬line, FB等通訊軟體常見的layout
1.5. 不用執行npm install而是整理package讓我自行install，install有狀況我再截message即可。npm run dev要能夠有個内網的網址ex. 192.168.10.155，讓同個網域的人可以連線進入做操作。
1.6. 如果某worker沒有連線或回應，例如worker_vision不存在，以至於python server無法處理，frontend的log要顯示狀況，遇到video stream就用黑頻呈現，遇到status就顯示失敗或無狀態，要確保不會讓frontend出現呈現上的錯誤，例如worker_vision不存在但worker_worker正常工作，那Digital View還是能看到robot的畫面而不是甚麼都沒有

<2. Python server (請實作於/server)>
2.1. 負責處理frontend發送的任務，依據類型找worker_actplan, worker_robot, worker_vision處理對應的任務，並適當更新frontend的狀態，例如分派任務時要回傳到前端顯示什麼任務正在執行、什麼任務正在等待中等等，相關連結建立方式與流程已在前端完整規劃，請確保能達成所有內容。
2.2 為了方便偵錯，請即時print狀態包含"接收甚麼請求"、"處理甚麼情況"、"狀態如何"、連線人數等等方便例如內網video stream出事(例如防火牆等問題)，其中SFU或是robot關節角度等更新時，請不要逐條print出來，而是用rich在固定地方不斷刷新，因為比如FPS=60時，print的資訊會被streaming等佔據而看不到其他重要資訊，請妥善衡量那些要用rich在固定地方刷新而那些一定要print出來。
2.3 worker_robot要不斷地進行動作模擬就算是沒有動作也要確保digital twin的時間還有再推進，只要有一個人要求SFU就要把模擬畫面上傳1份串流給伺服器，伺服器再像「郵局」一樣，把這份數據包複製並轉發給 B, C, D...，直到沒有人再接收資料時才關閉SFU，如果有任何人要求Robot status，也需要以固定時間查看當前各關節名稱與角度送出去，直到沒有人接收為止。worker_vision則是要一旦有一個人要求SFU就要把當前streaming傳出去直到沒有人接收才斷開。
2.4 撰寫requirements.txt以及WSL或是linux安裝指令(包含建立env與建議的python version)於README.md中，python3 main.py就可以執行Python server，執行時會把server的IP與port print出來

<3. Worker_ActionPlanner (請實作於/worker_actplan)>
3.1. python3 main.py執行程式，依序要求輸入ip與port後連上python server(會先跑)，如果無法建立連線則結束程式
3.2. 接收到Python server的worker_actplan的文字input時，先等待2秒(time.sleep)，然後根據字串長度截取一半作為回應，傳到frontend上
3.3. 要有log方便偵錯，視情況print或用rich在固定地方刷新
3.4. 撰寫requirements.txt以及WSL或是linux安裝指令(包含建立env與建議的python version)於README.md中

<4. Worker_Vision (請實作於/worker_vision)>
4.1. python3 main.py執行程式，依序要求輸入ip與port後連上python server(會先跑)，如果無法建立連線則結束程式
4.2. 不斷循環播放/worker_vision/file的影片，一旦接收到Python server的worker_vision的請求，建立SFU開啟影像串流，FPS=10並調低解析度，frame要轉成黑白才能發送出去，沒有人接收時worker_vision的SFU終止，但是影像播放仍在背景虛擬執行
4.3. 要有log方便偵錯，視情況print或用rich在固定地方刷新
4.4. 撰寫requirements.txt以及WSL或是linux安裝指令(包含建立env與建議的python version)於README.md中
4.5. 建議複製C:\Users\huang\Desktop\Intranet_Stream\server關鍵部分來修改

<5. Worker_Robot (請實作於/worker_robot)>
5.1. python3 main.py執行程式，依序要求輸入ip與port後連上python server(會先跑)，如果無法建立連線則結束程式
5.2. 執行時開啟pybullet(但是不要開取GUI)，設定plane.urdf與franka_panda/panda.urdf，並讓時間持續推移，一旦接收到digital view需要SFU時，設定模擬FPS=10並調低解析度，每5秒隨機設定各關節任意可執行角度，讓frontend能查看到當前模擬情況；如果接收到robot status則不需要上傳模擬畫面，但是一樣要每5秒隨機設定各關節任意可執行角度，把各關節角度1秒更新6次(相當於FPS=10)在frontend的Robot status中，僅初始建立連線時會需要上傳各關節名稱，之後只須跟新當前角度即可，且沒有接收者時自動斷開
5.3. 要有log方便偵錯，視情況print或用rich在固定地方刷新
5.4. 撰寫requirements.txt以及WSL或是linux安裝指令(包含建立env與建議的python version)於README.md中
