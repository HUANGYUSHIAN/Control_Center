# TMUI Connection Guide（開放 Port 與建立 Worker 連線）

此文件的目標：在啟動 `worker_actplan / worker_vision / worker_robot` 之前，先確保外部（或其他主機）能連到 `python server (FastAPI WebSocket)`。

假設：
- `server` WebSocket 位址為：`ws://<server-ip>:8765/ws`
- `server` 執行在 **WSL / Linux / Windows** 其中一種環境

---

## 0) 確認 server 正確在監聽

無論 server 在哪個環境，都要確保它以 `0.0.0.0` 監聽（讓外部能連進來）。

你現在 `server/main.py` 使用：
- `uvicorn.run(..., host="0.0.0.0", port=8765)`

因此重點會落在「該環境是否允許外部 TCP 8765」與「跨環境是否需要轉送（WSL -> Windows LAN）」。

---

## 1) 情境 A：server 在 WSL（最常見）

當 `server` 跑在 WSL 時：
- **WSL 有自己的內網 IP（例如 `172.28.x.x`）**
- 但其他「外部 Linux 主機」通常**不能直接連到 `172.28.x.x`**

所以做法是：在 Windows 使用 `netsh interface portproxy` 把 Windows 的 `8765` 轉發到 WSL 的 `172.28.x.x:8765`，並放行 Windows 防火牆。

### Step A1：先找 WSL 的 IP（connectaddress 要用）

在 WSL 內（server 那台機器）執行：

```bash
hostname -I
# 或
ip -4 addr
```

假設你拿到 WSL IP = `172.28.250.88`。

### Step A2：在 Windows 設定 portproxy（listenport=8765 -> connectaddress=WSL_IP:8765）

在 Windows（PowerShell，建議用管理員）執行（範本）：

```powershell
netsh interface portproxy add v4tov4 `
  listenaddress=0.0.0.0 listenport=8765 `
  connectaddress=<WSL_IP> connectport=8765
```

使用你的經驗（範例）：

```powershell
netsh interface portproxy add v4tov4 `
  listenaddress=0.0.0.0 listenport=8765 `
  connectaddress=172.28.250.88 connectport=8765
```

確認是否建立成功：

```powershell
netsh interface portproxy show all
```

應該會看到类似：
- `0.0.0.0  8765  ->  172.28.250.88  8765`

### Step A3：在 Windows 放行防火牆 inbound TCP 8765

```powershell
New-NetFirewallRule -DisplayName "TMUI server 8765" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765
```

### Step A4：用「worker 所在的外部 Linux」測 TCP 是否可達（確認真的打得到）

在外部 Linux worker 主機：

```bash
nc -vz <Windows_LAN_IP> 8765
# 例如：192.168.50.49
```

如果 `succeeded!`，代表連線層已通。

### Step A5：worker 設定 server IP/Port

worker 輸入：
- `server IP`：用 `Windows_LAN_IP`（例如 `192.168.50.49`）
- `server Port`：`8765`

WebSocket 路徑固定是：
- `/ws`

因此 server 使用 `ws://192.168.50.49:8765/ws`

---

## 2) 情境 B：server 在 Linux（原生 Linux）

如果 `server` 直接跑在 Linux（沒有 WSL/VM 轉送問題），那只需要：
- Linux 防火牆允許 TCP `8765`
- server 監聽 `0.0.0.0`（已在你的程式做了）

### Step B1：若使用 UFW（Ubuntu/Debian 常見）

```bash
sudo ufw allow 8765/tcp
sudo ufw status
```

### Step B2：若未啟用 UFW

就需要依你的發行版防火牆設定（可先用以下方式確認是否被卡）：

從外部 worker 主機跑：

```bash
nc -vz <Linux_SERVER_IP> 8765
```

如果失敗，再查 Linux 的防火牆 / 安全群組設定（雲端則要看 security group）。

### Step B3：worker 輸入 server IP/Port

- `server IP`：Linux SERVER 的 LAN IP
- `server Port`：8765

---

## 3) 情境 C：server 在 Windows（原生 Windows）

若 server 跑在 Windows：
- Windows 防火牆要放行 TCP 8765
- server 監聽 `0.0.0.0`（建議做法同上）

### Step C1：放行 Windows 防火牆 inbound TCP 8765

PowerShell（管理員）：

```powershell
New-NetFirewallRule -DisplayName "TMUI server 8765" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765
```

### Step C2：找 Windows LAN IP

例如 Wi-Fi 網卡 `192.168.50.49`（用你 ipconfig 的結果）。

### Step C3：worker 輸入 server IP/Port

- `server IP`：Windows LAN IP（例如 `192.168.50.49`）
- `server Port`：8765

---

## 4) 啟動順序建議（建立 worker 前）

1. 先啟動 `server`
   - 在對應環境啟動 `python3 main.py`
2. 若 server 在 WSL：
   - 再確認 Windows 已設定 `portproxy + 防火牆`
3. 在 worker 所在機器測 TCP：
   - `nc -vz <server-ip> 8765`
4. 再啟動 worker（依序或並行都可以）
   - `worker_actplan`、`worker_vision`、`worker_robot`
5. 最後啟動 frontend

---

## 5) 常見錯誤對照（快速判斷）

1. worker 顯示 `timed out during opening handshake`
   - 多半是「TCP 根本連不到」或「跨網段/WSL 轉送沒做好」
   - 先用 `nc -vz` 檢查
2. worker 能註冊，但畫面沒串流
   - 通常是 view 的訂閱事件（digital/camera/robot_status）流程問題

---

## 6)（瀏覽器所在機器）檢查 WebSocket 連線前的 TCP 層可達性

Browser/前端會連 `ws://<server-ip>:8765/ws`。WebSocket 的錯誤通常可以先用「TCP 8765 是否可達」快速判斷。

把下面指令在「你打開瀏覽器的那台機器」上跑即可（Windows / Linux / WSL 三擇一）。

### 6.1 Windows（PowerShell）

```powershell
Test-NetConnection -ComputerName 192.168.50.49 -Port 8765 -InformationLevel Detailed
```

重點看：
- `TcpTestSucceeded : True` 代表 TCP 層通了
- 若是 `False`，通常是防火牆/路由/portproxy 沒做

也可用：

```powershell
ping 192.168.50.49
```

ping 成功不代表 8765 可達，但失敗通常代表網路不通。

### 6.2 Linux（Terminal）

```bash
nc -vz 192.168.50.49 8765
```

若你的系統沒有 `nc`，可先嘗試：

```bash
sudo apt-get update && sudo apt-get install -y netcat-openbsd
```

### 6.3 WSL（Terminal）

WSL 基本上跟 Linux 一樣，用 TCP 測試即可：

```bash
nc -vz 192.168.50.49 8765
```

---

## 7)（選用）WebSocket 層測試（用工具）

如果你已經安裝了 `websocat` / `wscat`，可以直接測握手是否能通。

### 7.1 `websocat`（若有）

```bash
websocat -n1 ws://192.168.50.49:8765/ws
```

### 7.2 `wscat`（若有）

```bash
npx wscat -c ws://192.168.50.49:8765/ws
```

沒有安裝時可先跳過這段，TCP 層測試（第 6 點）通常足夠判斷「是否防火牆/端口不可達」。

