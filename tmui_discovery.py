"""TMUI worker 與 server 之間的位址解析：環境變數、loopback、Zeroconf、終端機手動輸入。"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

SERVICE_TYPE = "_tmui-server._tcp.local."
DEFAULT_SERVER_PORT = 8765

_log_configured = False


def configure_logging(component: str) -> logging.Logger:
    """每個 worker 行程啟動時呼叫一次；設 TMUI_DEBUG=1 可開 DEBUG。"""
    global _log_configured
    log = logging.getLogger(f"tmui.{component}")
    debug_en = os.environ.get("TMUI_DEBUG", "").strip().lower() in ("1", "true", "yes")
    level = logging.DEBUG if debug_en else logging.INFO
    if not _log_configured:
        logging.getLogger("zeroconf").setLevel(logging.WARNING)
        _log_configured = True
    log.setLevel(level)
    log.propagate = False
    if not log.handlers:
        log_dir = os.environ.get("TMUI_LOG_DIR", "").strip() or os.getcwd()
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"{component}.log")
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [tmui:%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        log.addHandler(fh)
    return log


class DiscoveryListener(ServiceListener):
    """不得在 add_service/update 內呼叫 get_service_info（會阻塞 Zeroconf 事件迴圈）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: list[tuple[str, str]] = []

    def add_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        with self._lock:
            self._queue.append((service_type, name))

    def remove_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        return

    def update_service(self, zc: Zeroconf, service_type: str, name: str) -> None:
        with self._lock:
            self._queue.append((service_type, name))

    def pop_all(self) -> list[tuple[str, str]]:
        with self._lock:
            out, self._queue = self._queue, []
            return out


def can_connect(
    host: str,
    port: int,
    timeout_s: float = 0.8,
    log: logging.Logger | None = None,
) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError as e:
        if log is not None:
            log.debug("TCP %s:%s 失敗: %s", host, port, e)
        return False


def discover_server(
    log: logging.Logger,
    timeout_s: float = 8.0,
) -> tuple[str, int] | None:
    log.info("開始 Zeroconf 瀏覽 service_type=%s，逾時約 %.1fs", SERVICE_TYPE, timeout_s)
    log.info(
        "提示：mDNS 多為連結本機或同一區網廣播；"
        "server 若在 WSL2，廣告位址常為虛擬網段，其他實體機通常看不到，請改用手動 IP（Windows 的 Wi‑Fi IP）。"
    )
    zc = Zeroconf()
    listener = DiscoveryListener()
    browser = ServiceBrowser(zc, SERVICE_TYPE, listener)
    _ = browser
    deadline = time.time() + timeout_s
    try:
        while time.time() < deadline:
            batch = listener.pop_all()
            if batch:
                log.debug("mDNS 佇列候選: %s", batch)
            for st, nm in batch:
                log.debug("get_service_info(%r, %r) …", st, nm)
                info = zc.get_service_info(st, nm, timeout=2000)
                if info and info.parsed_addresses():
                    addr = info.parsed_addresses()[0]
                    log.info("Zeroconf 解析成功: %s:%s (name=%r)", addr, info.port, nm)
                    return addr, info.port
                log.debug("get_service_info 無完整位址: info=%s", info)
            time.sleep(0.15)
    except Exception:
        log.exception("Zeroconf 瀏覽過程發生例外")
        raise
    finally:
        zc.close()
    log.warning("Zeroconf 在 %.1fs 內未找到 _tmui-server", timeout_s)
    return None


def prompt_server_endpoint(log: logging.Logger) -> tuple[str, int]:
    print(
        "\n自動發現失敗。請手動輸入 server 位址（"
        "server 跑在 WSL 時，其他電腦請填該 Windows 機器在 Wi‑Fi 上的區網 IP，而非 WSL 內的 eth0）。\n"
    )
    while True:
        try:
            ip = input("請輸入 TMUI server IP: ").strip()
        except EOFError as e:
            raise RuntimeError(
                "無法讀取終端機輸入。請設定環境變數 TMUI_SERVER 與選用 TMUI_PORT。"
            ) from e
        if not ip:
            print("IP 不可為空，請重新輸入。")
            continue
        try:
            raw_port = input(
                f"請輸入 TMUI server port（預設 {DEFAULT_SERVER_PORT}，直接 Enter）: "
            ).strip()
            port = int(raw_port) if raw_port else DEFAULT_SERVER_PORT
        except ValueError:
            print("port 必須為數字，請重新輸入。")
            continue
        log.info("嘗試手動位址 TCP 連線 %s:%s …", ip, port)
        if can_connect(ip, port, log=log):
            log.info("手動位址連線成功: %s:%s", ip, port)
            return ip, port
        log.warning("無法連線至 %s:%s（請確認 server 已啟動、防火牆、IP 是否為區網可達）", ip, port)
        print(f"無法連線到 {ip}:{port}，請再試或檢查上述項目。\n")


def resolve_server_endpoint(component: str) -> tuple[str, int]:
    """
    順序：TMUI_SERVER（若可連）→ loopback → Zeroconf → 終端機詢問 IP/port。
    """
    log = configure_logging(component)

    env_host = os.environ.get("TMUI_SERVER", "").strip()
    env_port_raw = os.environ.get("TMUI_PORT", "").strip()
    env_port = int(env_port_raw) if env_port_raw else DEFAULT_SERVER_PORT

    if env_host:
        log.info("使用環境變數 TMUI_SERVER=%r TMUI_PORT=%s", env_host, env_port)
        if can_connect(env_host, env_port, log=log):
            log.info("環境變數位址連線成功")
            return env_host, env_port
        log.warning("環境變數指定位址無法連線，改試 loopback 與 Zeroconf，最後會詢問手動輸入")

    log.info("嘗試 loopback port=%s …", DEFAULT_SERVER_PORT)
    for host in ("127.0.0.1", "localhost"):
        if can_connect(host, DEFAULT_SERVER_PORT, log=log):
            log.info("loopback 成功: %s:%s", host, DEFAULT_SERVER_PORT)
            return host, DEFAULT_SERVER_PORT
    log.info("loopback 無法連線（正常若 server 在別台電腦）")

    try:
        found = discover_server(log, timeout_s=8.0)
    except Exception as e:
        log.exception("Zeroconf 失敗，改為手動輸入: %s", e)
        found = None

    if found:
        return found

    return prompt_server_endpoint(log)
