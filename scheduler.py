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
    
    def set_log_callback(self, callback: Callable[[str], None]):
        """设置日志回调"""
        self._log_callback = callback
    
    def set_status_callback(self, callback: Callable[[str], None]):
        """设置状态回调"""
        self._status_callback = callback
    
    def _log(self, message: str):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        logger.info(message)
        if self._log_callback:
            self._log_callback(log_message)
    
    def _update_status(self, status: str):
        """更新状态"""
        if self._status_callback:
            self._status_callback(status)
    
    def switch_proxy(self, group_name: str = None) -> bool:
        """
        切换代理
        
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
        
        # 随机打乱顺序
        random.shuffle(available_proxies)
        
        # 检查是否需要验证代理可用性
        check_before_switch = self.config.get("check_before_switch", True)
        max_retry = self.config.get("max_retry", 3)
        
        if check_before_switch:
            # 找到可用的代理
            retry_count = 0
            for proxy_name in available_proxies:
                if retry_count >= max_retry:
                    self._log(f"已达到最大重试次数 ({max_retry})")
                    break
                
                self._log(f"检测代理: {proxy_name}")
                available, message = self.proxy_checker.check_proxy_available(proxy_name)
                
                if available:
                    # 切换到这个代理
                    if self.clash_api.switch_proxy(group_name, proxy_name):
                        self._log(f"切换成功: {proxy_name} ({message})")
                        self._update_status(f"当前: {proxy_name}")
                        return True
                    else:
                        self._log(f"切换失败: {proxy_name}")
                        retry_count += 1
                else:
                    self._log(f"代理不可用: {proxy_name} ({message})")
                    retry_count += 1
            
            self._log("错误: 没有找到可用的代理")
            self._update_status("切换失败")
            return False
        else:
            # 随机选择一个代理
            proxy_name = random.choice(available_proxies)
            if self.clash_api.switch_proxy(group_name, proxy_name):
                self._log(f"切换成功: {proxy_name}")
                self._update_status(f"当前: {proxy_name}")
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
