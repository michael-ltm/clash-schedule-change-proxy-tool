"""
AJiaSu 控制 API (HTTP IPC)。

接口形态尽量贴近 ClashAPI,这样上层可以用相似的方式调度。
通信对端是 AJiaSu 进程内的 ajiasu_bridge.js (v4+),
桥通过 fetch() 轮询本地 HTTP 服务器获取命令、提交结果。
"""

import json
import logging
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

IPC_PORT = 62517
GROUP_ALL = "[ALL]"
GROUP_FAVORITES = "[FAVORITES]"
GROUP_RECENT = "[RECENT]"

ID_FIELDS = ["Id", "id", "ServerId", "srvId", "serverId"]
NAME_FIELDS = ["Name", "name", "ServerName", "title", "Title"]
CATEGORY_FIELDS = ["CategoryCode", "categoryCode", "Category", "category", "Area", "area", "AreaCode", "areaCode"]


def _pick(d: dict, keys: List[str], default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, ""):
            return d[k]
    return default


def server_id(s: Any) -> Optional[str]:
    if isinstance(s, (str, int)):
        return str(s)
    if isinstance(s, dict):
        v = _pick(s, ID_FIELDS)
        return None if v is None else str(v)
    return None


def server_name(s: Any) -> str:
    if isinstance(s, (str, int)):
        return str(s)
    if isinstance(s, dict):
        return _pick(s, NAME_FIELDS, default=server_id(s) or "")
    return ""


def server_category(s: Any) -> str:
    if isinstance(s, dict):
        return str(_pick(s, CATEGORY_FIELDS, default=""))
    return ""


class _BridgeState:
    """Shared state between the HTTP handler and the API."""

    def __init__(self):
        self.lock = threading.Lock()
        self.pending_cmd: Optional[dict] = None
        self.result: Optional[dict] = None
        self.result_event = threading.Event()
        self.cmd_available = threading.Event()
        self.last_heartbeat: float = 0.0
        self.bridge_connected: bool = False
        self.bridge_version: int = 0


class _BridgeHandler(BaseHTTPRequestHandler):
    state: _BridgeState

    def _handle_poll(self, raw_body=b""):
        if "hb=1" in self.path:
            self.server._state.last_heartbeat = time.time()
            self.server._state.bridge_connected = True

        if raw_body:
            try:
                data = json.loads(raw_body)
                with self.server._state.lock:
                    self.server._state.result = data
                self.server._state.result_event.set()
            except Exception:
                pass

        with self.server._state.lock:
            cmd = self.server._state.pending_cmd
            if cmd:
                body = json.dumps(cmd).encode()
                self.server._state.pending_cmd = None
                self._respond(200, body)
                return

        deadline = time.time() + 2.0
        while time.time() < deadline:
            self.server._state.cmd_available.wait(timeout=0.1)
            self.server._state.cmd_available.clear()
            with self.server._state.lock:
                cmd = self.server._state.pending_cmd
                if cmd:
                    body = json.dumps(cmd).encode()
                    self.server._state.pending_cmd = None
                    self._respond(200, body)
                    return
        self._respond(200, b"none")

    def do_GET(self):
        if self.path.startswith("/bridge/poll"):
            self._handle_poll()
        elif self.path == "/ping":
            self._respond(200, b"pong")
        else:
            self._respond(404, b"not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        if self.path.startswith("/bridge/poll"):
            self._handle_poll(raw)
        elif self.path == "/bridge/result":
            try:
                data = json.loads(raw)
            except Exception:
                data = {"ok": False, "error": "bad json from bridge"}
            with self.server._state.lock:
                self.server._state.result = data
            self.server._state.result_event.set()
            self._respond(200, b"ok")
        elif self.path == "/bridge/hello":
            try:
                info = json.loads(raw)
                self.server._state.bridge_version = info.get("version", 0)
            except Exception:
                pass
            self.server._state.last_heartbeat = time.time()
            self.server._state.bridge_connected = True
            logger.info("AJiaSu bridge connected (v%s)", self.server._state.bridge_version)
            with self.server._state.lock:
                cmd = self.server._state.pending_cmd
                if cmd:
                    body = json.dumps(cmd).encode()
                    self.server._state.pending_cmd = None
                else:
                    body = b"ok"
            self._respond(200, body)
        else:
            self._respond(404, b"not found")

    def _respond(self, code: int, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


class AJiaSuAPI:
    """通过 HTTP IPC 控制 AJiaSu。"""

    def __init__(self, port: int = IPC_PORT, request_timeout: float = 8.0):
        self.port = port
        self.request_timeout = request_timeout
        self._state = _BridgeState()
        self._server: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._started = False

    def start_server(self):
        if self._started:
            return
        self._state.last_heartbeat = 0.0
        self._state.bridge_connected = False
        try:
            self._server = HTTPServer(("127.0.0.1", self.port), _BridgeHandler)
            self._server._state = self._state
            self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._server_thread.start()
            self._started = True
            logger.info("AJiaSu IPC server started on 127.0.0.1:%d", self.port)
        except OSError as e:
            logger.error("Failed to start IPC server on port %d: %s", self.port, e)

    def stop_server(self):
        if self._server:
            self._server.shutdown()
            self._server = None
            self._started = False

    def _ensure_server(self):
        if not self._started:
            self.start_server()

    # -------------------- 底层 RPC --------------------

    def _call(self, action: str, **kwargs) -> Tuple[bool, Any]:
        self._ensure_server()
        with self._lock:
            req_id = uuid.uuid4().hex
            payload = {"id": req_id, "action": action}
            payload.update(kwargs)

            self._state.result_event.clear()
            with self._state.lock:
                self._state.result = None
                self._state.pending_cmd = payload
            self._state.cmd_available.set()

            deadline = time.time() + self.request_timeout
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                if self._state.result_event.wait(timeout=min(remaining, 0.5)):
                    self._state.result_event.clear()
                    with self._state.lock:
                        data = self._state.result
                        self._state.result = None
                    if data is None:
                        continue
                    if data.get("id") and data["id"] != req_id:
                        continue
                    if data.get("ok"):
                        return True, data.get("result")
                    return False, data.get("error", "unknown error")

            with self._state.lock:
                self._state.pending_cmd = None
            return False, f"请求超时(>{self.request_timeout}s),爱加速桥可能未运行"

    # -------------------- 状态 / 测试 --------------------

    def test_connection(self) -> bool:
        self._ensure_server()
        if not self._state.bridge_connected:
            return False
        if (time.time() - self._state.last_heartbeat) > 60.0:
            return False
        for attempt in range(3):
            ok, _ = self._call("ping")
            if ok:
                return True
            time.sleep(1)
        return False

    def is_alive(self, max_age_sec: float = 5.0) -> bool:
        if not self._started or not self._state.bridge_connected:
            return False
        return (time.time() - self._state.last_heartbeat) < max_age_sec

    def get_version(self) -> Optional[Dict]:
        ok, res = self._call("version")
        if not ok:
            return None
        return {"version": res, "premium": False}

    # -------------------- 服务器列表 --------------------

    def get_all_servers(self) -> List[Any]:
        ok, res = self._call("list")
        if not ok or res is None:
            return []
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            for k in ("servers", "list", "data"):
                if isinstance(res.get(k), list):
                    return res[k]
        return []

    def get_favorite_ids(self) -> List[str]:
        ok, res = self._call("favorites")
        return [str(x) for x in res] if ok and isinstance(res, list) else []

    def get_recent_ids(self) -> List[str]:
        ok, res = self._call("recent")
        if not ok or not isinstance(res, list):
            return []
        out = []
        for item in res:
            sid = server_id(item)
            if sid is not None:
                out.append(sid)
        return out

    # -------------------- ClashAPI 兼容接口 --------------------

    def get_proxies(self) -> Optional[Dict]:
        servers = self.get_all_servers()
        proxies: Dict[str, Dict] = {}
        for s in servers:
            sid = server_id(s)
            if sid is None:
                continue
            name = server_name(s) or sid
            proxies[name] = {
                "name": name,
                "type": "AJiaSu",
                "id": sid,
                "category": server_category(s),
                "raw": s,
            }
        return {"proxies": proxies}

    def get_proxy_groups(self) -> List[Dict]:
        servers = self.get_all_servers()
        names_by_cat: Dict[str, List[str]] = {}
        all_names: List[str] = []
        for s in servers:
            sid = server_id(s)
            if sid is None:
                continue
            name = server_name(s) or sid
            all_names.append(name)
            cat = server_category(s) or "OTHER"
            names_by_cat.setdefault(cat, []).append(name)

        current = self.get_current_server_name() or ""
        groups = [{
            "name": GROUP_ALL,
            "type": "Selector",
            "now": current,
            "all": all_names,
        }]

        fav_ids = set(self.get_favorite_ids())
        if fav_ids:
            id2name = {server_id(s): server_name(s) or server_id(s)
                       for s in servers if server_id(s)}
            fav_names = [id2name[i] for i in fav_ids if i in id2name]
            if fav_names:
                groups.append({
                    "name": GROUP_FAVORITES, "type": "Selector",
                    "now": current, "all": fav_names,
                })

        rec_ids = self.get_recent_ids()
        if rec_ids:
            id2name = {server_id(s): server_name(s) or server_id(s)
                       for s in servers if server_id(s)}
            rec_names = [id2name[i] for i in rec_ids if i in id2name]
            if rec_names:
                groups.append({
                    "name": GROUP_RECENT, "type": "Selector",
                    "now": current, "all": rec_names,
                })

        for cat in sorted(names_by_cat.keys()):
            groups.append({
                "name": cat,
                "type": "Selector",
                "now": current,
                "all": names_by_cat[cat],
            })
        return groups

    def get_group_proxies(self, group_name: str) -> List[str]:
        for g in self.get_proxy_groups():
            if g["name"] == group_name:
                return list(g.get("all", []))
        return []

    def get_current_server_name(self) -> Optional[str]:
        stats = self.get_status() or {}
        for k in ("ServerName", "serverName", "name", "Name"):
            if isinstance(stats, dict) and stats.get(k):
                return str(stats[k])
        sid = None
        for k in ("ServerId", "serverId", "Id", "id", "srvId"):
            if isinstance(stats, dict) and stats.get(k):
                sid = str(stats[k])
                break
        if sid:
            for s in self.get_all_servers():
                if server_id(s) == sid:
                    return server_name(s) or sid
            return sid
        return None

    def get_current_proxy(self, _group_name: str) -> Optional[str]:
        return self.get_current_server_name()

    def switch_proxy(self, _group_name: str, proxy_name: str) -> bool:
        sid = self._name_to_id(proxy_name)
        if not sid:
            logger.error(f"找不到节点的 srvId: {proxy_name}")
            return False
        ok, _res = self._call("connect", srvId=sid)
        if ok:
            logger.info(f"AJiaSu 切换节点: {proxy_name} (id={sid})")
        else:
            logger.error(f"AJiaSu 切换失败: {proxy_name} ({_res})")
        return ok

    def _name_to_id(self, name: str) -> Optional[str]:
        for s in self.get_all_servers():
            if server_name(s) == name:
                return server_id(s)
        return None

    def get_proxy_delay(self, proxy_name: str, *_args, **_kwargs) -> Optional[int]:
        sid = self._name_to_id(proxy_name)
        if not sid:
            return None
        ok, _res = self._call("pingServers", ids=[sid])
        if not ok:
            return None
        deadline = time.time() + 6.0
        while time.time() < deadline:
            ok2, reports = self._call("pingReports")
            if ok2 and isinstance(reports, list):
                for r in reports:
                    rid = _pick(r or {}, ["ServerId", "serverId", "Id", "id"])
                    if rid is not None and str(rid) == sid:
                        delay = _pick(r, ["Delay", "delay", "Ping", "ping", "Latency", "latency", "Ms", "ms"])
                        try:
                            d = int(delay)
                            if d > 0:
                                return d
                        except (TypeError, ValueError):
                            pass
            time.sleep(0.3)
        return None

    # -------------------- AJiaSu 专属操作 --------------------

    def get_status(self) -> Optional[Dict]:
        ok, res = self._call("status")
        return res if ok and isinstance(res, dict) else None

    def disconnect(self) -> bool:
        return self._call("disconnect")[0]

    def auto_pick(self, level: str = "", code: str = "",
                  servers: Optional[List[str]] = None) -> bool:
        return self._call("pick", level=level, code=code, servers=servers or [])[0]

    def ping_servers(self, ids: List[str]) -> bool:
        return self._call("pingServers", ids=list(ids))[0]

    def get_ping_reports(self) -> List[Dict]:
        ok, res = self._call("pingReports")
        return res if ok and isinstance(res, list) else []

    # -------------------- 兼容旧接口 --------------------

    def update_config(self, ipc_dir: str = ""):
        pass
