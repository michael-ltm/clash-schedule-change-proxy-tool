"""
AJiaSu res.fvr 补丁工具

把 ajiasu_bridge.js 注入到 AJiaSu 的 res.fvr (zip) 里,并在 window-main.htm
末尾追加一个 <script type="module" src="ajiasu_bridge.js"></script>。
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
PATCH_MARKER = "<!-- AJIASU-BRIDGE-INSTALLED -->"
PATCH_SCRIPT = (
    f'        {PATCH_MARKER}\n'
    f'        <script type="module" src="{BRIDGE_FILENAME}"></script>\n'
)
INSERT_BEFORE = "</head>"
TARGET_HTML = "window-main.htm"
RES_FILE = "res.fvr"
BAK_FILE = "res.fvr.bak"


def _bridge_js_path() -> Path:
    """
    开发态和打包后都能找到 bridge JS。
    PyInstaller one-file 模式下数据文件被解压到 sys._MEIPASS。
    """
    candidates = []
    if getattr(sys, "frozen", False):
        # PyInstaller 解压目录(one-file)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / BRIDGE_FILENAME)
        # exe 旁边(one-folder 模式 / 用户手动放置)
        candidates.append(Path(sys.executable).parent / BRIDGE_FILENAME)
    # 开发态:跟 .py 同目录
    candidates.append(Path(__file__).parent / BRIDGE_FILENAME)

    for c in candidates:
        if c.exists():
            return c
    # 都找不到的话返回最后一个候选,留给上层报错
    return candidates[-1]


def find_res_file(install_dir: Path) -> Optional[Path]:
    """在安装目录里找 res.fvr。"""
    p = Path(install_dir) / RES_FILE
    return p if p.exists() else None


def can_write(install_dir: Path) -> bool:
    """
    判断当前进程能不能改 res.fvr。在 Program Files 下且没管理员时返回 False。
    """
    res = find_res_file(Path(install_dir))
    if res is None:
        # 路径都不对,谈不上权限问题
        return False
    if not os.access(res, os.W_OK):
        return False
    # 父目录也要能写(因为我们要写 .tmp 然后 rename)
    return os.access(res.parent, os.W_OK)


def is_patched(res_path: Path) -> bool:
    """检查 res.fvr 是否已经被打过补丁。"""
    try:
        with zipfile.ZipFile(res_path, "r") as zf:
            names = zf.namelist()
            if BRIDGE_FILENAME not in names:
                return False
            try:
                html = zf.read(TARGET_HTML).decode("utf-8", errors="replace")
            except KeyError:
                return False
            return PATCH_MARKER in html
    except zipfile.BadZipFile:
        return False
    except Exception as e:
        logger.warning(f"检查 res.fvr 是否已打补丁失败: {e}")
        return False


def _modify_html(html: str) -> str:
    """在 </head> 前注入桥脚本。已经有标记则原样返回。"""
    if PATCH_MARKER in html:
        return html
    if INSERT_BEFORE not in html:
        raise RuntimeError(f"{TARGET_HTML} 里找不到 {INSERT_BEFORE!r}")
    return html.replace(INSERT_BEFORE, PATCH_SCRIPT + "    " + INSERT_BEFORE, 1)


def _strip_html(html: str) -> str:
    """从 HTML 里移除补丁脚本。"""
    if PATCH_MARKER not in html:
        return html
    # 把整段插入的内容(包括下方的缩进)移除
    parts = html.split(PATCH_SCRIPT, 1)
    if len(parts) == 2:
        return parts[0] + parts[1]
    # 容错:只删 marker + 下一行 script
    lines = html.split("\n")
    out = []
    skip_next = 0
    for line in lines:
        if skip_next > 0:
            skip_next -= 1
            continue
        if PATCH_MARKER in line:
            skip_next = 1
            continue
        out.append(line)
    return "\n".join(out)


def _rewrite_zip(src: Path, dst: Path, transforms: dict, extra_files: dict):
    """复制 src zip 到 dst,对 transforms 里的成员替换内容,追加 extra_files。"""
    with zipfile.ZipFile(src, "r") as zin, \
         zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:

        seen = set()
        for item in zin.infolist():
            seen.add(item.filename)
            data = zin.read(item.filename)
            if item.filename in transforms:
                data = transforms[item.filename](data)
            new = zipfile.ZipInfo(filename=item.filename, date_time=item.date_time)
            new.compress_type = zipfile.ZIP_DEFLATED
            new.external_attr = item.external_attr
            zout.writestr(new, data)

        for name, payload in extra_files.items():
            if name in seen:
                # 已在循环里写过了;若 transforms 没改过,这里再写一次会重复
                # 所以只在不存在时追加
                continue
            zout.writestr(name, payload)


def patch(install_dir: Path) -> Tuple[bool, str]:
    """
    打补丁。返回 (是否成功, 消息)。
    """
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

    bridge_bytes = bridge_src.read_bytes()

    tmp = res.with_suffix(".fvr.tmp")
    try:
        _rewrite_zip(
            src=res,
            dst=tmp,
            transforms={
                TARGET_HTML: lambda data: _modify_html(
                    data.decode("utf-8")
                ).encode("utf-8"),
                BRIDGE_FILENAME: lambda _data: bridge_bytes,
            },
            extra_files={BRIDGE_FILENAME: bridge_bytes},
        )
        os.replace(tmp, res)
    except Exception as e:
        if tmp.exists():
            try: tmp.unlink()
            except Exception: pass
        return False, f"写入 res.fvr 失败: {e}"

    return True, f"补丁完成,已备份到 {bak.name}"


def unpatch(install_dir: Path) -> Tuple[bool, str]:
    """
    卸载补丁:优先从 res.fvr.bak 恢复;若没有备份则原地剥离。
    """
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

    # 没有备份,尝试在原文件上剥离
    if not is_patched(res):
        return True, "本来就没打补丁"

    tmp = res.with_suffix(".fvr.tmp")
    try:
        with zipfile.ZipFile(res, "r") as zin, \
             zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == BRIDGE_FILENAME:
                    continue
                data = zin.read(item.filename)
                if item.filename == TARGET_HTML:
                    data = _strip_html(data.decode("utf-8")).encode("utf-8")
                new = zipfile.ZipInfo(filename=item.filename, date_time=item.date_time)
                new.compress_type = zipfile.ZIP_DEFLATED
                new.external_attr = item.external_attr
                zout.writestr(new, data)
        os.replace(tmp, res)
    except Exception as e:
        if tmp.exists():
            try: tmp.unlink()
            except Exception: pass
        return False, f"剥离补丁失败: {e}"

    return True, "已剥离补丁"
