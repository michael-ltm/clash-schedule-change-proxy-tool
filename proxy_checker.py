"""
代理检测模块
用于检测代理是否可用
"""

import socket
import urllib.request
import logging
from typing import Optional, Tuple
from clash_api import ClashAPI

logger = logging.getLogger(__name__)


class ProxyChecker:
    """代理可用性检测器"""
    
    def __init__(self, clash_api: ClashAPI):
        """
        初始化代理检测器
        
        Args:
            clash_api: Clash API 客户端实例
        """
        self.clash_api = clash_api
        self.test_urls = [
            "http://www.gstatic.com/generate_204",
            "http://cp.cloudflare.com/generate_204",
            "http://www.google.com/generate_204",
        ]
        self.timeout = 5000  # 毫秒
    
    def check_proxy_delay(self, proxy_name: str) -> Tuple[bool, Optional[int], str]:
        """
        通过 Clash API 检测代理延迟
        
        Args:
            proxy_name: 代理名称
            
        Returns:
            (是否可用, 延迟毫秒数, 消息)
        """
        for url in self.test_urls:
            delay = self.clash_api.get_proxy_delay(proxy_name, url, self.timeout)
            if delay is not None:
                if delay > 0:
                    return True, delay, f"延迟: {delay}ms"
                else:
                    continue
        
        return False, None, "无法连接"
    
    def check_proxy_available(self, proxy_name: str) -> Tuple[bool, str]:
        """
        检测代理是否可用
        
        Args:
            proxy_name: 代理名称
            
        Returns:
            (是否可用, 消息)
        """
        available, delay, message = self.check_proxy_delay(proxy_name)
        return available, message
    
    def find_available_proxy(self, proxy_list: list, exclude_current: str = None) -> Optional[str]:
        """
        从代理列表中找到一个可用的代理
        
        Args:
            proxy_list: 代理名称列表
            exclude_current: 要排除的当前代理
            
        Returns:
            可用的代理名称，没有找到返回 None
        """
        for proxy_name in proxy_list:
            # 跳过当前代理和特殊节点
            if proxy_name == exclude_current:
                continue
            if proxy_name.lower() in ["direct", "reject", "global", "auto"]:
                continue
            
            available, message = self.check_proxy_available(proxy_name)
            logger.info(f"检测代理 {proxy_name}: {message}")
            
            if available:
                return proxy_name
        
        return None
    
    def get_all_proxy_delays(self, proxy_list: list) -> dict:
        """
        获取所有代理的延迟
        
        Args:
            proxy_list: 代理名称列表
            
        Returns:
            {代理名称: (是否可用, 延迟, 消息)}
        """
        results = {}
        for proxy_name in proxy_list:
            if proxy_name.lower() in ["direct", "reject"]:
                results[proxy_name] = (True, 0, "直连/拒绝")
                continue
            
            available, delay, message = self.check_proxy_delay(proxy_name)
            results[proxy_name] = (available, delay, message)
        
        return results
    
    def set_timeout(self, timeout_ms: int):
        """
        设置超时时间
        
        Args:
            timeout_ms: 超时时间（毫秒）
        """
        self.timeout = timeout_ms


def check_internet_connection(timeout: int = 5) -> bool:
    """
    检测是否有网络连接
    
    Args:
        timeout: 超时时间（秒）
        
    Returns:
        是否有网络连接
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except socket.error:
        pass
    
    try:
        urllib.request.urlopen("http://www.baidu.com", timeout=timeout)
        return True
    except Exception:
        pass
    
    return False
