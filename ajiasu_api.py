"""
AJiaSu 控制 API (文件 IPC 客户端)。

接口形态尽量贴近 ClashAPI,这样上层可以用相似的方式调度。
通信对端是 AJiaSu 进程内的 ajiasu_bridge.js,见 ajiasu_bridge.js 顶部注释。
"""

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_IPC_DIR = Path("C:/Users/Public/AJiaSu")
GROUP_ALL = "[ALL]"
GROUP_FAVORITES = "[FAVORITES]"
GROUP_RECENT = "[RECENT]"

# 服务器对象里可能用的字段名(原始 xcall 返回的 JSON 我们不可完全确定,
# 所以做容错)
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


class AJiaSuAPI:
    """通过文件 IPC 控制 AJiaSu。"""

    def __init__(self, ipc_dir: Optional[str] = None, request_timeout: float = 8.0):
        self.ipc_dir = Path(ipc_dir) if ipc_dir else DEFAULT_IPC_DIR
        self.cmd_path = self.ipc_dir / "cmd.json"
        self.result_path = self.ipc_dir / "result.json"
        self.ready_path = self.ipc_dir / "ready.txt"
        self.request_timeout = request_timeout
        self._lock = threading.Lock()

    # -------------------- 底层 RPC --------------------

    def _ensure_dir(self):
        try:
            self.ipc_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _call(self, action: str, **kwargs) -> Tuple[bool, Any]:
        """
        发送一次请求,等待响应。返回 (ok, result_or_error)。
        """
        self._ensure_dir()
        with self._lock:
            req_id = uuid.uuid4().hex
            payload = {"id": req_id, "action": action}
            payload.update(kwargs)

            # 清理可能残留的旧响应
            try:
                if self.result_path.exists():
                    self.result_path.unlink()
            except Exception:
                pass

            try:
                tmp = self.cmd_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(payload), encoding="utf-8")
                os.replace(tmp, self.cmd_path)
            except Exception as e:
                return False, f"写入命令文件失败: {e}"

            deadline = time.time() + self.request_timeout
            while time.time() < deadline:
                if self.result_path.exists():
                    try:
                        text = self.result_path.read_text(encoding="utf-8")
                        data = json.loads(text)
                    except Exception:
                        time.sleep(0.05)
                        continue

                    if data.get("id") and data["id"] != req_id:
                        # 旧响应,等下一轮
                        time.sleep(0.05)
                        continue

                    try:
                        self.result_path.unlink()
                    except Exception:
                        pass

                    if data.get("ok"):
                        return True, data.get("result")
                    return False, data.get("error", "unknown error")

                time.sleep(0.08)

            # 超时:把命令文件清掉以免干扰下一次
            try:
                if self.cmd_path.exists():
                    self.cmd_path.unlink()
            except Exception:
                pass
            return False, f"请求超时(>{self.request_timeout}s),爱加速桥可能未运行"

    # -------------------- 状态 / 测试 --------------------

    def test_connection(self) -> bool:
        """探活(强):mtime + ping 往返。用在初始化/手动检查这种愿意等的地方。"""
        try:
            if not self.ready_path.exists():
                return False
            mtime = self.ready_path.stat().st_mtime
            return (time.time() - mtime) < 60.0 and self._call("ping")[0]
        except Exception:
            return False

    def is_alive(self, max_age_sec: float = 5.0) -> bool:
        """
        探活(轻量,无 IPC 往返)。只看 ready.txt 的 mtime 是否在 max_age_sec
        以内。桥每 ~2s 心跳一次,所以 5s 是稳的。
        用在背景轮询里,避免每次 sync 都做一次 ping 往返。
        """
        try:
            if not self.ready_path.exists():
                return False
            mtime = self.ready_path.stat().st_mtime
            return (time.time() - mtime) < max_age_sec
        except Exception:
            return False

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
        # 有些 xcall 可能返回 {servers: [...]} 之类
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
        # recent 可能是 ID 列表也可能是对象列表
        out = []
        for item in res:
            sid = server_id(item)
            if sid is not None:
                out.append(sid)
        return out

    # -------------------- ClashAPI 兼容接口 --------------------

    def get_proxies(self) -> Optional[Dict]:
        """与 ClashAPI 兼容:返回 {"proxies": {name: {...}}}。"""
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
        """
        把可选的"分组"做成 ClashAPI 风格。
        固定有 [ALL] / [FAVORITES] / [RECENT],其余按 categoryCode 分。
        """
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
        # 字段名我们不能完全确定;尝试几个可能性
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
        """按 name 在所有服务器里找到 ID,然后 vpnConnect。"""
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
        """ping 单个节点,返回延迟 ms。"""
        sid = self._name_to_id(proxy_name)
        if not sid:
            return None
        ok, _res = self._call("pingServers", ids=[sid])
        if not ok:
            return None
        # 等一下 native 那边把 ping 结果写回来
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

    # -------------------- 其它 --------------------

    def update_config(self, ipc_dir: str):
        self.ipc_dir = Path(ipc_dir) if ipc_dir else DEFAULT_IPC_DIR
        self.cmd_path = self.ipc_dir / "cmd.json"
        self.result_path = self.ipc_dir / "result.json"
        self.ready_path = self.ipc_dir / "ready.txt"
