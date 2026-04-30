"""
定时任务模块
用于管理定时切换代理的任务
"""

import threading
import time
import logging
import random
from typing import Callable, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ProxyScheduler:
    """代理切换调度器"""
    
    def __init__(self):
        """初始化调度器"""
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._interval_minutes = 30
        self._callback: Optional[Callable] = None
        self._on_tick: Optional[Callable[[int], None]] = None  # 每秒回调，参数为剩余秒数
        self._lock = threading.Lock()
        self._next_run_time: Optional[datetime] = None
        self._remaining_seconds = 0
    
    def set_interval(self, minutes: int):
        """
        设置切换间隔
        
        Args:
            minutes: 间隔分钟数
        """
        with self._lock:
            self._interval_minutes = max(1, minutes)
            logger.info(f"设置切换间隔: {self._interval_minutes} 分钟")
    
    def set_callback(self, callback: Callable):
        """
        设置切换回调函数
        
        Args:
            callback: 切换时调用的函数
        """
        self._callback = callback
    
    def set_on_tick(self, on_tick: Callable[[int], None]):
        """
        设置每秒回调函数
        
        Args:
            on_tick: 每秒调用的函数，参数为剩余秒数
        """
        self._on_tick = on_tick
    
    def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("调度器已经在运行")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("调度器已启动")
    
    def stop(self):
        """停止调度器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self._next_run_time = None
        self._remaining_seconds = 0
        logger.info("调度器已停止")
    
    def is_running(self) -> bool:
        """
        检查调度器是否在运行
        
        Returns:
            是否在运行
        """
        return self._running
    
    def get_remaining_seconds(self) -> int:
        """
        获取距离下次切换的剩余秒数
        
        Returns:
            剩余秒数
        """
        return self._remaining_seconds
    
    def get_next_run_time(self) -> Optional[datetime]:
        """
        获取下次切换时间
        
        Returns:
            下次切换时间
        """
        return self._next_run_time
    
    def trigger_now(self):
        """立即触发一次切换"""
        if self._callback:
            logger.info("手动触发代理切换")
            try:
                self._callback()
            except Exception as e:
                logger.error(f"切换回调执行失败: {e}")
    
    def _run_loop(self):
        """调度循环"""
        while self._running:
            with self._lock:
                interval_seconds = self._interval_minutes * 60
            
            self._remaining_seconds = interval_seconds
            self._next_run_time = datetime.now()
            
            # 倒计时
            while self._remaining_seconds > 0 and self._running:
                if self._on_tick:
                    try:
                        self._on_tick(self._remaining_seconds)
                    except Exception as e:
                        logger.error(f"tick 回调执行失败: {e}")
                
                time.sleep(1)
                self._remaining_seconds -= 1
            
            # 执行切换
            if self._running and self._callback:
                logger.info("定时触发代理切换")
                try:
                    self._callback()
                except Exception as e:
                    logger.error(f"切换回调执行失败: {e}")


class ProxySwitcher:
    """代理切换器"""
    
    def __init__(self, clash_api, proxy_checker, config):
        """
        初始化代理切换器
        
        Args:
            clash_api: Clash API 客户端
            proxy_checker: 代理检测器
            config: 配置管理器
        """
        from clash_api import ClashAPI
        from proxy_checker import ProxyChecker
        from config import Config
        
        self.clash_api: ClashAPI = clash_api
        self.proxy_checker: ProxyChecker = proxy_checker
        self.config: Config = config
        self.scheduler = ProxyScheduler()
        self._log_callback: Optional[Callable[[str], None]] = None
        self._status_callback: Optional[Callable[[str], None]] = None
        self._used_proxies: set = set()  # 记录已使用的代理
        self._all_proxies: set = set()   # 记录所有可用代理
    
    def set_log_callback(self, callback: Callable[[str], None]):
        """设置日志回调"""
        self._log_callback = callback
    
    def set_status_callback(self, callback: Callable[[str], None]):
        """设置状态回调"""
        self._status_callback = callback
    
    def _log(self, message: str):
        """记录日志"""
        logger.info(message)
        if self._log_callback:
            self._log_callback(message)
    
    def _update_status(self, status: str):
        """更新状态"""
        if self._status_callback:
            self._status_callback(status)
    
    def switch_proxy(self, group_name: str = None) -> bool:
        """
        切换代理 - 优先选择延迟低且未使用的代理
        
        Args:
            group_name: 代理组名称，为 None 时使用配置中的组
            
        Returns:
            是否切换成功
        """
        if group_name is None:
            group_name = self.config.get("selected_group", "")
        
        if not group_name:
            self._log("错误: 未选择代理组")
            return False
        
        self._log(f"开始切换代理组: {group_name}")
        self._update_status("正在切换...")
        
        # 获取当前代理
        current_proxy = self.clash_api.get_current_proxy(group_name)
        self._log(f"当前代理: {current_proxy}")
        
        # 获取代理列表
        proxy_list = self.clash_api.get_group_proxies(group_name)
        if not proxy_list:
            self._log("错误: 无法获取代理列表")
            self._update_status("切换失败")
            return False
        
        # 过滤掉特殊节点
        available_proxies = [
            p for p in proxy_list 
            if p.lower() not in ["direct", "reject", "global", "auto"]
            and p != current_proxy
        ]
        
        if not available_proxies:
            self._log("错误: 没有可用的代理节点")
            self._update_status("切换失败")
            return False
        
        # 更新所有代理列表
        self._all_proxies = set(available_proxies)
        
        # 检查是否所有代理都已使用过，如果是则重置
        if self._used_proxies >= self._all_proxies:
            self._log("所有代理已使用一轮，重置使用记录")
            self._used_proxies.clear()
        
        # 检查是否需要验证代理可用性
        check_before_switch = self.config.get("check_before_switch", True)
        
        if check_before_switch:
            # 获取所有代理的延迟信息
            self._log("正在测试代理延迟...")
            delay_results = self.proxy_checker.get_all_proxy_delays(available_proxies)
            
            # 筛选可用的代理，并按延迟排序
            available_with_delay = []
            for proxy_name, (available, delay, message) in delay_results.items():
                if available and delay is not None:
                    available_with_delay.append((proxy_name, delay))
            
            if not available_with_delay:
                self._log("错误: 没有可用的代理节点")
                self._update_status("切换失败")
                return False
            
            # 按延迟排序（从低到高）
            available_with_delay.sort(key=lambda x: x[1])
            
            # 优先选择未使用过的代理
            unused_proxies = [(name, delay) for name, delay in available_with_delay 
                            if name not in self._used_proxies]
            
            # 如果有未使用的代理，使用它们；否则使用所有可用代理
            candidates = unused_proxies if unused_proxies else available_with_delay
            
            self._log(f"找到 {len(candidates)} 个候选代理（未使用: {len(unused_proxies)}）")
            
            # 尝试切换到延迟最低的未使用代理
            for proxy_name, delay in candidates:
                used_status = "已使用" if proxy_name in self._used_proxies else "未使用"
                self._log(f"尝试切换: {proxy_name} (延迟: {delay}ms, 状态: {used_status})")
                
                if self.clash_api.switch_proxy(group_name, proxy_name):
                    self._log(f"✓ 切换成功: {proxy_name} (延迟: {delay}ms)")
                    self._update_status(f"当前: {proxy_name}")
                    self._used_proxies.add(proxy_name)
                    return True
                else:
                    self._log(f"✗ 切换失败: {proxy_name}")
            
            self._log("错误: 所有候选代理切换失败")
            self._update_status("切换失败")
            return False
        else:
            # 不检测延迟时，优先选择未使用的代理
            unused_proxies = [p for p in available_proxies if p not in self._used_proxies]
            candidates = unused_proxies if unused_proxies else available_proxies
            
            # 随机选择一个候选代理
            proxy_name = random.choice(candidates)
            
            if self.clash_api.switch_proxy(group_name, proxy_name):
                self._log(f"切换成功: {proxy_name}")
                self._update_status(f"当前: {proxy_name}")
                self._used_proxies.add(proxy_name)
                return True
            else:
                self._log(f"切换失败: {proxy_name}")
                self._update_status("切换失败")
                return False
    
    def start_auto_switch(self):
        """启动自动切换"""
        interval = self.config.get("interval_minutes", 30)
        self.scheduler.set_interval(interval)
        self.scheduler.set_callback(self.switch_proxy)
        self.scheduler.start()
        self._log(f"自动切换已启动，间隔: {interval} 分钟")
    
    def stop_auto_switch(self):
        """停止自动切换"""
        self.scheduler.stop()
        self._log("自动切换已停止")
    
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self.scheduler.is_running()


class AJiaSuProxySwitcher:
    """
    爱加速节点切换器,接口和 ProxySwitcher 一致,GUI 层可以无差别使用。

    "代理组" 在爱加速里映射为 [ALL] / [FAVORITES] / [RECENT] / 各 categoryCode。
    切换流程:从所选 group 取节点列表 -> (可选) ping 排序 -> vpnConnect。
    """

    def __init__(self, ajiasu_api, config):
        from ajiasu_api import AJiaSuAPI
        from config import Config

        self.ajiasu_api: AJiaSuAPI = ajiasu_api
        self.config: Config = config
        self.scheduler = ProxyScheduler()
        self._log_callback: Optional[Callable[[str], None]] = None
        self._status_callback: Optional[Callable[[str], None]] = None
        self._used_proxies: set = set()
        self._all_proxies: set = set()

    def set_log_callback(self, callback: Callable[[str], None]):
        self._log_callback = callback

    def set_status_callback(self, callback: Callable[[str], None]):
        self._status_callback = callback

    def _log(self, message: str):
        logger.info(message)
        if self._log_callback:
            self._log_callback(message)

    def _update_status(self, status: str):
        if self._status_callback:
            self._status_callback(status)

    def switch_proxy(self, group_name: str = None) -> bool:
        if group_name is None:
            group_name = self.config.get("ajiasu_selected_group", "")

        if not group_name:
            self._log("错误: 未选择爱加速分组")
            return False

        self._log(f"开始切换爱加速节点(分组: {group_name})")
        self._update_status("正在切换...")

        proxy_list = self.ajiasu_api.get_group_proxies(group_name)
        if not proxy_list:
            self._log("错误: 该分组下没有节点")
            self._update_status("切换失败")
            return False

        current = self.ajiasu_api.get_current_server_name()
        available = [p for p in proxy_list if p != current]
        if not available:
            available = proxy_list

        self._all_proxies = set(available)
        if self._used_proxies >= self._all_proxies:
            self._log("所有节点已使用一轮,重置使用记录")
            self._used_proxies.clear()

        check = self.config.get("check_before_switch", True)

        if check:
            # 一次性 ping 整组,然后按延迟挑节点
            ids = [self.ajiasu_api._name_to_id(p) for p in available]
            ids = [i for i in ids if i]
            if ids:
                self._log(f"正在测试 {len(ids)} 个节点的延迟...")
                self.ajiasu_api.ping_servers(ids)
                # 等 native 把 ping 写完
                import time as _t
                _t.sleep(min(5.0, 0.05 * len(ids) + 1.0))
                reports = self.ajiasu_api.get_ping_reports() or []
            else:
                reports = []

            id2delay = {}
            for r in reports:
                from ajiasu_api import _pick as ap
                rid = ap(r or {}, ["ServerId", "serverId", "Id", "id"])
                d = ap(r, ["Delay", "delay", "Ping", "ping", "Latency", "latency", "Ms", "ms"])
                try:
                    di = int(d)
                except (TypeError, ValueError):
                    continue
                if rid is not None and di > 0:
                    id2delay[str(rid)] = di

            scored = []
            for name in available:
                sid = self.ajiasu_api._name_to_id(name)
                delay = id2delay.get(str(sid)) if sid else None
                if delay is not None:
                    scored.append((name, delay))

            if not scored:
                self._log("所有节点延迟均不可用,改用未测速候选")
                scored = [(n, 99999) for n in available]

            scored.sort(key=lambda x: x[1])
            unused = [(n, d) for n, d in scored if n not in self._used_proxies]
            candidates = unused if unused else scored

            self._log(f"找到 {len(candidates)} 个候选节点(未使用: {len(unused)})")

            for name, delay in candidates:
                used_status = "已使用" if name in self._used_proxies else "未使用"
                self._log(f"尝试切换: {name} (延迟: {delay}ms, 状态: {used_status})")
                if self.ajiasu_api.switch_proxy(group_name, name):
                    self._log(f"✓ 切换成功: {name} (延迟: {delay}ms)")
                    self._update_status(f"当前: {name}")
                    self._used_proxies.add(name)
                    return True
                else:
                    self._log(f"✗ 切换失败: {name}")

            self._log("错误: 所有候选节点切换失败")
            self._update_status("切换失败")
            return False
        else:
            unused = [p for p in available if p not in self._used_proxies]
            candidates = unused if unused else available
            name = random.choice(candidates)
            if self.ajiasu_api.switch_proxy(group_name, name):
                self._log(f"切换成功: {name}")
                self._update_status(f"当前: {name}")
                self._used_proxies.add(name)
                return True
            else:
                self._log(f"切换失败: {name}")
                self._update_status("切换失败")
                return False

    def start_auto_switch(self):
        interval = self.config.get("interval_minutes", 30)
        self.scheduler.set_interval(interval)
        self.scheduler.set_callback(self.switch_proxy)
        self.scheduler.start()
        self._log(f"爱加速自动切换已启动,间隔: {interval} 分钟")

    def stop_auto_switch(self):
        self.scheduler.stop()
        self._log("爱加速自动切换已停止")

    def is_running(self) -> bool:
        return self.scheduler.is_running()
