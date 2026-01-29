"""
Clash API 交互模块
用于与 Clash Verge 的 RESTful API 进行通信
"""

import requests
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class ClashAPI:
    """Clash API 客户端"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 9090, secret: str = ""):
        """
        初始化 Clash API 客户端
        
        Args:
            host: Clash API 主机地址
            port: Clash API 端口
            secret: API 密钥（如果设置了的话）
        """
        self.base_url = f"http://{host}:{port}"
        self.secret = secret
        self.session = requests.Session()
        if secret:
            self.session.headers["Authorization"] = f"Bearer {secret}"
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        """
        发送 API 请求
        
        Args:
            method: HTTP 方法
            endpoint: API 端点
            **kwargs: 额外的请求参数
            
        Returns:
            响应的 JSON 数据，失败返回 None
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(method, url, timeout=10, **kwargs)
            response.raise_for_status()
            if response.text:
                return response.json()
            return {}
        except requests.exceptions.RequestException as e:
            logger.error(f"API 请求失败: {url} - {e}")
            return None
        except Exception as e:
            logger.error(f"解析响应失败: {e}")
            return None
    
    def get_version(self) -> Optional[Dict]:
        """获取 Clash 版本信息"""
        return self._request("GET", "/version")
    
    def get_config(self) -> Optional[Dict]:
        """获取 Clash 配置"""
        return self._request("GET", "/configs")
    
    def get_proxies(self) -> Optional[Dict]:
        """
        获取所有代理信息
        
        Returns:
            包含所有代理的字典
        """
        return self._request("GET", "/proxies")
    
    def get_proxy(self, name: str) -> Optional[Dict]:
        """
        获取指定代理的详细信息
        
        Args:
            name: 代理名称
            
        Returns:
            代理详细信息
        """
        return self._request("GET", f"/proxies/{requests.utils.quote(name)}")
    
    def get_proxy_groups(self) -> List[Dict]:
        """
        获取所有代理组
        
        Returns:
            代理组列表
        """
        proxies = self.get_proxies()
        if not proxies:
            return []
        
        groups = []
        proxies_data = proxies.get("proxies", {})
        
        for name, info in proxies_data.items():
            proxy_type = info.get("type", "")
            # Selector 和 URLTest 类型是可以切换的代理组
            if proxy_type in ["Selector", "URLTest", "Fallback", "LoadBalance"]:
                groups.append({
                    "name": name,
                    "type": proxy_type,
                    "now": info.get("now", ""),
                    "all": info.get("all", [])
                })
        
        return groups
    
    def get_group_proxies(self, group_name: str) -> List[str]:
        """
        获取代理组中的所有代理
        
        Args:
            group_name: 代理组名称
            
        Returns:
            代理名称列表
        """
        proxy = self.get_proxy(group_name)
        if proxy:
            return proxy.get("all", [])
        return []
    
    def get_current_proxy(self, group_name: str) -> Optional[str]:
        """
        获取代理组当前选中的代理
        
        Args:
            group_name: 代理组名称
            
        Returns:
            当前代理名称
        """
        proxy = self.get_proxy(group_name)
        if proxy:
            return proxy.get("now")
        return None
    
    def switch_proxy(self, group_name: str, proxy_name: str) -> bool:
        """
        切换代理组的代理
        
        Args:
            group_name: 代理组名称
            proxy_name: 目标代理名称
            
        Returns:
            是否切换成功
        """
        result = self._request(
            "PUT",
            f"/proxies/{requests.utils.quote(group_name)}",
            json={"name": proxy_name}
        )
        success = result is not None
        if success:
            logger.info(f"切换代理成功: {group_name} -> {proxy_name}")
        else:
            logger.error(f"切换代理失败: {group_name} -> {proxy_name}")
        return success
    
    def get_proxy_delay(self, proxy_name: str, url: str = "http://www.gstatic.com/generate_204", timeout: int = 5000) -> Optional[int]:
        """
        测试代理延迟
        
        Args:
            proxy_name: 代理名称
            url: 测试 URL
            timeout: 超时时间（毫秒）
            
        Returns:
            延迟（毫秒），失败返回 None
        """
        result = self._request(
            "GET",
            f"/proxies/{requests.utils.quote(proxy_name)}/delay",
            params={"url": url, "timeout": timeout}
        )
        if result:
            return result.get("delay")
        return None
    
    def test_connection(self) -> bool:
        """
        测试与 Clash API 的连接
        
        Returns:
            是否连接成功
        """
        version = self.get_version()
        return version is not None
    
    def update_config(self, host: str, port: int, secret: str = ""):
        """
        更新 API 配置
        
        Args:
            host: 新的主机地址
            port: 新的端口
            secret: 新的密钥
        """
        self.base_url = f"http://{host}:{port}"
        self.secret = secret
        if secret:
            self.session.headers["Authorization"] = f"Bearer {secret}"
        else:
            self.session.headers.pop("Authorization", None)
