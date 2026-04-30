"""
AJiaSu 安装目录自动检测

爱加速实际运行时常见两种 exe 名:
- AJiaSu.exe       : 安装器/启动器 (老版本 / Program Files 下)
- HD_AJiaSu.exe    : 实际客户端,自动更新后从 %LocalAppData% / %AppData%
                     下加载,这才是真正运行的进程
所以"安装目录"必须看哪个 exe 在跑;静态扫描 Program Files 经常找错。
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# 按可能性排序,前面的更常见
EXE_NAMES = ["HD_AJiaSu.exe", "AJiaSu.exe", "AJiaSu_HD.exe"]
RES_NAME = "res.fvr"


def _hidden_subproc_kwargs():
    """让 subprocess 不弹黑色 console (PyInstaller GUI 程序刚需)。"""
    if sys.platform != "win32":
        return {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": creationflags, "startupinfo": si}


def _candidate_dirs() -> List[Path]:
    cands: List[Path] = []
    if sys.platform == "win32":
        env = os.environ
        roots = [
            env.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")),
            env.get("APPDATA", str(Path.home() / "AppData" / "Roaming")),
            env.get("ProgramFiles", r"C:\Program Files"),
            env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            r"C:\\",
            r"D:\\",
        ]
        names = ["AJiaSu", "爱加速", "爱加速VIP"]
        for root in roots:
            if not root:
                continue
            for n in names:
                cands.append(Path(root) / n)
                cands.append(Path(root) / "Programs" / n)
    else:
        home = Path.home()
        cands += [
            home / "AJiaSu",
            home / "Documents" / "AJiaSu",
            Path("/Applications/AJiaSu"),
        ]

    cwd = Path.cwd()
    cands.append(cwd / "AJiaSu")
    cands.append(cwd.parent / "AJiaSu")

    return cands


def is_install_dir(path: Path) -> bool:
    """是否是有效安装目录:含任一 exe 名 + res.fvr。"""
    p = Path(path)
    if not (p / RES_NAME).exists():
        return False
    return any((p / name).exists() for name in EXE_NAMES)


def find_running_install_dir() -> Optional[Path]:
    """
    通过 WMIC / PowerShell 找运行中爱加速进程的真实路径,返回其安装目录。
    覆盖"启动器和真实客户端在不同目录"的场景。
    """
    if sys.platform != "win32":
        return None

    kw = _hidden_subproc_kwargs()

    # 路径 1: WMIC (Win10 默认带,Win11 部分版本被 deprecated 但通常还能用)
    for name in EXE_NAMES:
        try:
            out = subprocess.run(
                ["wmic", "process", "where", f"name='{name}'",
                 "get", "ExecutablePath", "/format:list"],
                capture_output=True, text=True, timeout=8, **kw,
            )
            for line in out.stdout.splitlines():
                line = line.strip()
                if line.lower().startswith("executablepath=") and "=" in line:
                    p = line.split("=", 1)[1].strip()
                    if p:
                        d = Path(p).parent
                        if is_install_dir(d):
                            logger.info(f"WMIC 命中运行中 {name}: {d}")
                            return d
        except Exception as e:
            logger.debug(f"WMIC 查 {name} 失败: {e}")

    # 路径 2: PowerShell (WMIC 缺失时兜底)
    try:
        names_ps = ",".join(f"'{n.replace('.exe','')}'" for n in EXE_NAMES)
        ps_cmd = (
            f"Get-Process | Where-Object {{ $_.Name -in @({names_ps}) }} | "
            "Select-Object -First 1 -ExpandProperty Path"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=8, **kw,
        )
        line = out.stdout.strip()
        if line:
            d = Path(line).parent
            if is_install_dir(d):
                logger.info(f"PowerShell 命中运行中爱加速: {d}")
                return d
    except Exception as e:
        logger.debug(f"PowerShell 查爱加速失败: {e}")

    return None


def detect_install_dir() -> Optional[Path]:
    """
    自动找 AJiaSu 安装目录。优先级:
      1) 当前运行中的进程的目录(WMIC/PowerShell)
      2) 已知候选路径扫描
    """
    running = find_running_install_dir()
    if running:
        return running

    for c in _candidate_dirs():
        try:
            if c.exists() and is_install_dir(c):
                logger.info(f"扫描命中 AJiaSu 安装目录: {c}")
                return c
        except Exception:
            continue
    return None


def is_running() -> bool:
    """爱加速任一 exe 是否在跑。"""
    if sys.platform != "win32":
        return False
    try:
        kw = _hidden_subproc_kwargs()
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5, **kw,
        )
        text = (out.stdout or "").lower()
        return any(name.lower() in text for name in EXE_NAMES)
    except Exception:
        return False


def running_exe_names() -> List[str]:
    """已运行的爱加速 exe 名(用于显示给用户哪个在跑)。"""
    if sys.platform != "win32":
        return []
    try:
        kw = _hidden_subproc_kwargs()
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5, **kw,
        )
        text = (out.stdout or "").lower()
        return [n for n in EXE_NAMES if n.lower() in text]
    except Exception:
        return []
