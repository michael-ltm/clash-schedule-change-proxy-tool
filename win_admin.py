"""
Windows UAC 提权辅助:仅在 Windows 下生效。
"""

import logging
import os
import sys
from typing import List, Optional

logger = logging.getLogger(__name__)


def is_admin() -> bool:
    """是否当前进程已有管理员权限。非 Windows 视为 True(无需提权)。"""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(extra_args: Optional[List[str]] = None) -> bool:
    """
    以管理员身份重启自己。成功返回 True(调用方应紧接着退出当前进程)。
    仅 Windows 有效;非 Windows 直接返回 False。
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        if getattr(sys, "frozen", False):
            # 打包后:sys.executable 就是我们的 exe
            exe = sys.executable
            argv = list(sys.argv[1:])
        else:
            # 开发态:用 python 解释器 + 当前脚本
            exe = sys.executable
            argv = list(sys.argv)

        if extra_args:
            argv = argv + list(extra_args)

        params = " ".join(f'"{a}"' for a in argv)
        # SW_SHOWNORMAL = 1
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        # ShellExecute 返回 >32 表示成功
        return ret > 32
    except Exception as e:
        logger.error(f"提权重启失败: {e}")
        return False


def can_write_path(path) -> bool:
    """简易写权限检查。文件存在用 W_OK,不存在则看父目录的 W_OK。"""
    p = str(path)
    if os.path.exists(p):
        return os.access(p, os.W_OK)
    parent = os.path.dirname(p) or "."
    return os.access(parent, os.W_OK)
