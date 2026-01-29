#!/usr/bin/env python3
"""
Clash Verge 定时代理切换工具
主程序入口
"""

import sys
import os
import logging
from pathlib import Path

# 确保模块路径正确
if getattr(sys, 'frozen', False):
    # 打包后的路径
    application_path = Path(sys.executable).parent
else:
    # 开发时的路径
    application_path = Path(__file__).parent

sys.path.insert(0, str(application_path))

from config import Config


def setup_logging(config: Config):
    """
    设置日志
    
    Args:
        config: 配置管理器
    """
    log_file = config.get_log_file()
    
    # 配置日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # 配置根日志器
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # 减少第三方库的日志输出
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def check_dependencies():
    """检查依赖是否安装"""
    missing = []
    
    try:
        import requests
    except ImportError:
        missing.append("requests")
    
    try:
        import customtkinter
    except ImportError:
        missing.append("customtkinter")
    
    if missing:
        print(f"缺少依赖: {', '.join(missing)}")
        print("请运行: uv sync 或 pip install -r requirements.txt")
        return False
    
    return True


def main():
    """主函数"""
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 初始化配置
    config = Config()
    
    # 设置日志
    setup_logging(config)
    
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("定时更改Clash代理 - 启动")
    logger.info("=" * 50)
    
    # 检查 GUI
    try:
        import customtkinter as ctk
        # 测试能否创建实例
        root = ctk.CTk()
        root.withdraw()
        root.destroy()
    except ImportError:
        logger.error("customtkinter 未安装")
        print("错误: customtkinter 未安装")
        print("请运行: uv sync 或 pip install customtkinter")
        sys.exit(1)
    except Exception as e:
        logger.error(f"无法初始化界面: {e}")
        print(f"错误: 无法初始化图形界面 - {e}")
        sys.exit(1)
    
    # 启动 GUI
    try:
        from gui import IntervalProxyGUI
        app = IntervalProxyGUI()
        app.run()
    except Exception as e:
        logger.exception("程序运行错误")
        print(f"程序错误: {e}")
        sys.exit(1)
    
    logger.info("程序退出")


if __name__ == "__main__":
    main()
