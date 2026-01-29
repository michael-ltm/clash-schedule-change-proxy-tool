"""
Clash 配置自动检测模块
自动检测系统中 Clash Verge 的配置
"""

import os
import sys
import yaml
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple
import requests

logger = logging.getLogger(__name__)


def get_clash_verge_config_dir() -> Optional[Path]:
    """
    获取 Clash Verge 配置目录
    
    Returns:
        配置目录路径，未找到返回 None
    """
    if sys.platform == "darwin":  # macOS
        # Clash Verge Rev
        paths = [
            Path.home() / "Library/Application Support/io.github.clash-verge-rev.clash-verge-rev",
            # 旧版 Clash Verge
            Path.home() / "Library/Application Support/clash-verge",
        ]
    elif sys.platform == "win32":  # Windows
        appdata = os.environ.get("APPDATA", "")
        paths = [
            Path(appdata) / "io.github.clash-verge-rev.clash-verge-rev",
            Path(appdata) / "clash-verge",
        ]
    else:  # Linux
        paths = [
            Path.home() / ".config/clash-verge-rev",
            Path.home() / ".config/clash-verge",
        ]
    
    for path in paths:
        if path.exists():
            logger.info(f"找到 Clash Verge 配置目录: {path}")
            return path
    
    return None


def read_clash_config(config_dir: Path) -> Optional[Dict]:
    """
    读取 Clash 配置文件
    
    Args:
        config_dir: 配置目录
        
    Returns:
        配置字典
    """
    # 尝试读取运行时配置
    config_files = [
        config_dir / "clash-verge.yaml",
        config_dir / "config.yaml",
    ]
    
    for config_file in config_files:
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    if config:
                        logger.info(f"读取配置文件: {config_file}")
                        return config
            except Exception as e:
                logger.warning(f"读取配置文件失败 {config_file}: {e}")
    
    return None


def read_verge_config(config_dir: Path) -> Optional[Dict]:
    """
    读取 Verge 特定配置
    
    Args:
        config_dir: 配置目录
        
    Returns:
        配置字典
    """
    verge_file = config_dir / "verge.yaml"
    if verge_file.exists():
        try:
            with open(verge_file, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"读取 verge.yaml 失败: {e}")
    return None


def detect_clash_settings() -> Tuple[str, int, str]:
    """
    自动检测 Clash 设置
    
    Returns:
        (host, port, secret) 元组
    """
    host = "127.0.0.1"
    port = 9097  # Clash Verge 默认端口
    secret = ""
    
    # 尝试从配置文件读取
    config_dir = get_clash_verge_config_dir()
    if config_dir:
        # 读取 Clash 配置
        clash_config = read_clash_config(config_dir)
        if clash_config:
            # external-controller 格式: "127.0.0.1:9097" 或 ":9097"
            ext_ctrl = clash_config.get("external-controller", "")
            if ext_ctrl:
                if ":" in ext_ctrl:
                    parts = ext_ctrl.rsplit(":", 1)
                    if parts[0]:
                        host = parts[0]
                    try:
                        port = int(parts[1])
                    except ValueError:
                        pass
            
            # 密钥
            secret = clash_config.get("secret", "") or ""
        
        # 读取 Verge 配置（可能覆盖）
        verge_config = read_verge_config(config_dir)
        if verge_config:
            # Verge 可能有自己的端口设置
            ctrl = verge_config.get("clash_controller", {})
            if isinstance(ctrl, dict):
                if ctrl.get("port"):
                    port = ctrl.get("port")
                if ctrl.get("secret"):
                    secret = ctrl.get("secret")
    
    logger.info(f"检测到 Clash 设置: {host}:{port}")
    return host, port, secret


def try_connect(host: str, port: int, secret: str = "", timeout: float = 2.0) -> bool:
    """
    尝试连接到 Clash API
    
    Args:
        host: 主机
        port: 端口
        secret: 密钥
        timeout: 超时时间
        
    Returns:
        是否连接成功
    """
    url = f"http://{host}:{port}/version"
    headers = {}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def auto_detect_and_connect() -> Tuple[str, int, str, bool]:
    """
    自动检测并尝试连接
    
    Returns:
        (host, port, secret, connected) 元组
    """
    # 首先尝试从配置文件检测
    host, port, secret = detect_clash_settings()
    
    if try_connect(host, port, secret):
        logger.info(f"自动连接成功: {host}:{port}")
        return host, port, secret, True
    
    # 如果失败，尝试常用端口
    common_ports = [9097, 9090, 9091, 7890, 7891]
    
    for p in common_ports:
        if p == port:
            continue
        if try_connect(host, p, secret):
            logger.info(f"通过端口扫描连接成功: {host}:{p}")
            return host, p, secret, True
    
    # 返回检测到的设置，但标记未连接
    return host, port, secret, False
