"""
配置管理模块
用于保存和加载用户配置
"""

import json
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class Config:
    """配置管理类"""
    
    DEFAULT_CONFIG = {
        # 全局
        "mode": "clash",  # clash | ajiasu
        "interval_seconds": 60,  # 切换间隔(秒);老版本的 interval_minutes 启动时会自动迁移
        "auto_start": False,
        "check_before_switch": True,
        "max_retry": 3,
        "test_timeout_ms": 5000,
        "window_width": 480,
        "window_height": 720,
        "language": "",  # 语言设置，空则自动检测

        # Clash 模式
        "clash_host": "127.0.0.1",
        "clash_port": 9097,  # Clash Verge 默认端口
        "clash_secret": "",
        "selected_group": "",

        # 爱加速 (AJiaSu) 模式
        "ajiasu_install_path": "",        # AJiaSu 安装目录,内含 AJiaSu.exe / res.fvr
        "ajiasu_ipc_dir": "",             # 留空使用默认 C:\\Users\\Public\\AJiaSu
        "ajiasu_selected_group": "",      # 选择的"分组"(地区/分类),GROUP_ALL 等
    }
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_dir: 配置文件目录，默认使用用户目录下的 .clash-proxy-timer
        """
        if config_dir is None:
            # 跨平台配置目录
            if os.name == "nt":  # Windows
                config_dir = os.path.join(os.environ.get("APPDATA", ""), "clash-proxy-timer")
            else:  # macOS / Linux
                config_dir = os.path.join(os.path.expanduser("~"), ".clash-proxy-timer")
        
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "config.json"
        self.config: Dict[str, Any] = self.DEFAULT_CONFIG.copy()
        
        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载配置
        self.load()
    
    def load(self) -> bool:
        """
        从文件加载配置
        
        Returns:
            是否加载成功
        """
        if not self.config_file.exists():
            logger.info("配置文件不存在，使用默认配置")
            return False
        
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                loaded_config = json.load(f)
                # 合并配置,保留默认值
                for key, value in loaded_config.items():
                    if key in self.DEFAULT_CONFIG:
                        self.config[key] = value
                # 迁移:旧版本用的是 interval_minutes,新版改成 interval_seconds
                if "interval_seconds" not in loaded_config and "interval_minutes" in loaded_config:
                    try:
                        self.config["interval_seconds"] = max(1, int(loaded_config["interval_minutes"]) * 60)
                        logger.info(
                            f"已将 interval_minutes={loaded_config['interval_minutes']} 迁移为 "
                            f"interval_seconds={self.config['interval_seconds']}"
                        )
                    except Exception:
                        pass
            logger.info(f"配置加载成功: {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return False
    
    def save(self) -> bool:
        """
        保存配置到文件
        
        Returns:
            是否保存成功
        """
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"配置保存成功: {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """
        设置配置项
        
        Args:
            key: 配置键
            value: 配置值
        """
        self.config[key] = value
    
    def update(self, updates: Dict[str, Any]):
        """
        批量更新配置
        
        Args:
            updates: 要更新的配置字典
        """
        self.config.update(updates)
    
    def reset(self):
        """重置为默认配置"""
        self.config = self.DEFAULT_CONFIG.copy()
    
    def get_log_file(self) -> Path:
        """
        获取日志文件路径
        
        Returns:
            日志文件路径
        """
        return self.config_dir / "proxy_switch.log"
