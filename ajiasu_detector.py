"""
AJiaSu 安装目录自动检测
"""

import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

EXE_NAME = "AJiaSu.exe"
RES_NAME = "res.fvr"


def _candidate_dirs() -> List[Path]:
    cands: List[Path] = []
    if sys.platform == "win32":
        env = os.environ
        roots = [
            env.get("ProgramFiles", r"C:\Program Files"),
            env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            env.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")),
            env.get("APPDATA", str(Path.home() / "AppData" / "Roaming")),
            r"C:\\",
            r"D:\\",
        ]
        names = ["AJiaSu", "爱加速", "爱加速VIP"]
        for root in roots:
            if not root:
                continue
            for n in names:
                cands.append(Path(root) / n)
    else:
        # 非 Windows 平台:开发态 / 用户自己指定
        # 也支持把 AJiaSu 目录拖到这些位置
        home = Path.home()
        cands += [
            home / "AJiaSu",
            home / "Documents" / "AJiaSu",
            Path("/Applications/AJiaSu"),
        ]

    # 用户工作目录里如果有 reverse/exe/AJiaSu (开发用)
    cwd = Path.cwd()
    cands.append(cwd / "AJiaSu")
    cands.append(cwd.parent / "AJiaSu")

    return cands


def is_install_dir(path: Path) -> bool:
    """判断是不是 AJiaSu 安装目录:必须有 AJiaSu.exe 和 res.fvr。"""
    p = Path(path)
    return (p / EXE_NAME).exists() and (p / RES_NAME).exists()


def detect_install_dir() -> Optional[Path]:
    """自动找 AJiaSu 安装目录,找不到返回 None。"""
    for c in _candidate_dirs():
        try:
            if c.exists() and is_install_dir(c):
                logger.info(f"检测到 AJiaSu 安装目录: {c}")
                return c
        except Exception:
            continue
    return None


def is_running() -> bool:
    """简单判断 AJiaSu.exe 是否在运行(只在 Windows 上准确)。"""
    if sys.platform != "win32":
        return False
    try:
        import subprocess
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {EXE_NAME}"],
            capture_output=True, text=True, timeout=5,
        )
        return EXE_NAME.lower() in out.stdout.lower()
    except Exception:
        return False
