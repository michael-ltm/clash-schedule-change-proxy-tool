"""
AJiaSu res.fvr 补丁工具

策略: 把桥代码追加到 <body> 里最后一个 <script> 块末尾(</script> 之前)。
这是 Sciter 唯一会执行注入代码的位置——新增的 <script> 标签不会被执行。
首次安装会备份原始 res.fvr 到 res.fvr.bak。
"""

import logging
import os
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

BRIDGE_FILENAME = "ajiasu_bridge.js"
BRIDGE_VERSION = 14
PATCH_MARKER_START = "/* AJIASU-BRIDGE-START */"
PATCH_MARKER_END = "/* AJIASU-BRIDGE-END */"
TARGET_HTML = "window-main.htm"
RES_FILE = "res.fvr"
BAK_FILE = "res.fvr.bak"


def _bridge_js_path() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / BRIDGE_FILENAME)
        candidates.append(Path(sys.executable).parent / BRIDGE_FILENAME)
    candidates.append(Path(__file__).parent / BRIDGE_FILENAME)
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


def find_res_file(install_dir: Path) -> Optional[Path]:
    p = Path(install_dir) / RES_FILE
    return p if p.exists() else None


def can_write(install_dir: Path) -> bool:
    res = find_res_file(Path(install_dir))
    if res is None:
        return False
    if not os.access(res, os.W_OK):
        return False
    return os.access(res.parent, os.W_OK)


def is_patched(res_path: Path) -> bool:
    try:
        with zipfile.ZipFile(res_path, "r") as zf:
            try:
                html = zf.read(TARGET_HTML).decode("utf-8", errors="replace")
            except KeyError:
                return False
            return PATCH_MARKER_START in html
    except zipfile.BadZipFile:
        return False
    except Exception as e:
        logger.warning(f"检查 res.fvr 是否已打补丁失败: {e}")
        return False


def _modify_html(html: str, bridge_js: str) -> str:
    if PATCH_MARKER_START in html:
        return html

    last_close = html.rfind("</script>")
    if last_close == -1:
        raise RuntimeError(f"{TARGET_HTML} 里找不到 </script>")

    patch_block = (
        f"\n            {PATCH_MARKER_START}\n"
        f"{bridge_js}\n"
        f"            {PATCH_MARKER_END}\n"
        f"        "
    )
    return html[:last_close] + patch_block + html[last_close:]


def _strip_html(html: str) -> str:
    if PATCH_MARKER_START not in html:
        return html
    start = html.find(PATCH_MARKER_START)
    end = html.find(PATCH_MARKER_END)
    if start == -1 or end == -1:
        return html
    end += len(PATCH_MARKER_END)
    while start > 0 and html[start-1] in ' \t\n':
        start -= 1
    while end < len(html) and html[end] in ' \t\n':
        end += 1
    return html[:start] + html[end:]


def _rewrite_zip(src: Path, dst: Path, transforms: dict):
    with zipfile.ZipFile(src, "r") as zin, \
         zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in transforms:
                data = transforms[item.filename](data)
            new = zipfile.ZipInfo(filename=item.filename, date_time=item.date_time)
            new.compress_type = zipfile.ZIP_DEFLATED
            new.external_attr = item.external_attr
            zout.writestr(new, data)


def patch(install_dir: Path) -> Tuple[bool, str]:
    install_dir = Path(install_dir)
    res = find_res_file(install_dir)
    if res is None:
        return False, f"未找到 {install_dir / RES_FILE}"

    bridge_src = _bridge_js_path()
    if not bridge_src.exists():
        return False, f"找不到桥脚本 {bridge_src}"

    if is_patched(res):
        return True, "已经打过补丁,无需重复"

    bak = install_dir / BAK_FILE
    if not bak.exists():
        try:
            shutil.copy2(res, bak)
        except Exception as e:
            return False, f"备份失败: {e}"

    bridge_js = bridge_src.read_text(encoding="utf-8")

    tmp = res.with_suffix(".fvr.tmp")
    try:
        _rewrite_zip(
            src=res,
            dst=tmp,
            transforms={
                TARGET_HTML: lambda data: _modify_html(
                    data.decode("utf-8"), bridge_js
                ).encode("utf-8"),
            },
        )
        os.replace(tmp, res)
    except Exception as e:
        if tmp.exists():
            try: tmp.unlink()
            except Exception: pass
        return False, f"写入 res.fvr 失败: {e}"

    return True, f"补丁完成,已备份到 {bak.name}"


def unpatch(install_dir: Path) -> Tuple[bool, str]:
    install_dir = Path(install_dir)
    res = find_res_file(install_dir)
    if res is None:
        return False, f"未找到 {install_dir / RES_FILE}"

    bak = install_dir / BAK_FILE
    if bak.exists():
        try:
            shutil.copy2(bak, res)
            return True, "已从备份恢复"
        except Exception as e:
            return False, f"恢复失败: {e}"

    if not is_patched(res):
        return True, "本来就没打补丁"

    tmp = res.with_suffix(".fvr.tmp")
    try:
        _rewrite_zip(
            src=res,
            dst=tmp,
            transforms={
                TARGET_HTML: lambda data: _strip_html(
                    data.decode("utf-8")
                ).encode("utf-8"),
            },
        )
        os.replace(tmp, res)
    except Exception as e:
        if tmp.exists():
            try: tmp.unlink()
            except Exception: pass
        return False, f"剥离补丁失败: {e}"

    return True, "已剥离补丁"
