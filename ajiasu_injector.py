"""
ajiasu_injector.py — DLL injection for the runtime "memory-patch" bridge.

This is the Python side of the alternative to ajiasu_patcher.py. Instead of
modifying res.fvr on disk and waiting for AJiaSu to reload it, we inject
sciter_bridge.dll into the already-running HD_AJiaSu.exe process via the
classic CreateRemoteThread + LoadLibraryW dance. The DLL then calls
SciterEval inside AJiaSu's Sciter VM to load ajiasu_bridge.js.

Why this exists
---------------
The disk-patch approach has a silent failure mode: res.fvr gets modified but
Sciter never executes the injected JS (auto-update overwrites it / wrong
res.fvr / bytes don't survive Sciter's HTML parser / etc). The runtime
injection path is independent — if the inject_dll() call returns success,
sciter.dll is in our process, and SciterEval either runs or logs a clear
error to %LocalAppData%\\AJiaSu\\inject.log.

Bitness
-------
A DLL must match the bitness of the target process. We detect AJiaSu's
bitness with IsWow64Process2 (Win10+) or IsWow64Process (older Windows) and
load sciter_bridge_x64.dll or sciter_bridge_x86.dll accordingly.

Limitations
-----------
- Windows only. ctypes.wintypes is unavailable elsewhere.
- Requires SeDebugPrivilege when AJiaSu was started by a different user (we
  run under the same user normally, so this is fine without elevation).
- Some third-party AVs (Norton, Kaspersky) flag CreateRemoteThread as
  injection. Microsoft Defender allows it. If a user reports an AV block,
  point them at the docs section in AJIASU_MODE.md.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Win32 binding setup. ctypes' wintypes covers the basics; we add the few
# function signatures we need.
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi = ctypes.WinDLL("psapi", use_last_error=True)

    PROCESS_CREATE_THREAD     = 0x0002
    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_OPERATION      = 0x0008
    PROCESS_VM_WRITE          = 0x0020
    PROCESS_VM_READ           = 0x0010
    INJECT_ACCESS = (
        PROCESS_CREATE_THREAD
        | PROCESS_QUERY_INFORMATION
        | PROCESS_VM_OPERATION
        | PROCESS_VM_WRITE
        | PROCESS_VM_READ
    )

    MEM_COMMIT  = 0x1000
    MEM_RESERVE = 0x2000
    MEM_RELEASE = 0x8000
    PAGE_READWRITE = 0x04

    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype  = wintypes.HANDLE

    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype  = wintypes.BOOL

    _kernel32.VirtualAllocEx.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
        wintypes.DWORD,  wintypes.DWORD,
    ]
    _kernel32.VirtualAllocEx.restype = ctypes.c_void_p

    _kernel32.VirtualFreeEx.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD,
    ]
    _kernel32.VirtualFreeEx.restype = wintypes.BOOL

    _kernel32.WriteProcessMemory.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
    ]
    _kernel32.WriteProcessMemory.restype = wintypes.BOOL

    _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetModuleHandleW.restype  = wintypes.HMODULE

    _kernel32.GetProcAddress.argtypes = [wintypes.HMODULE, ctypes.c_char_p]
    _kernel32.GetProcAddress.restype  = ctypes.c_void_p

    _kernel32.CreateRemoteThread.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.CreateRemoteThread.restype = wintypes.HANDLE

    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype  = wintypes.DWORD

    _kernel32.GetExitCodeThread.argtypes = [wintypes.HANDLE,
                                            ctypes.POINTER(wintypes.DWORD)]
    _kernel32.GetExitCodeThread.restype  = wintypes.BOOL

    _kernel32.IsWow64Process.argtypes = [wintypes.HANDLE,
                                         ctypes.POINTER(wintypes.BOOL)]
    _kernel32.IsWow64Process.restype  = wintypes.BOOL

    # IsWow64Process2 is Win10+. Use it when present; it tells us machine
    # arch (x64 / arm64) directly. Fallback to IsWow64Process otherwise.
    try:
        _kernel32.IsWow64Process2.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.USHORT),
            ctypes.POINTER(wintypes.USHORT),
        ]
        _kernel32.IsWow64Process2.restype = wintypes.BOOL
        _HAS_IS_WOW64_PROCESS_2 = True
    except AttributeError:
        _HAS_IS_WOW64_PROCESS_2 = False

    _psapi.EnumProcesses.argtypes = [
        ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _psapi.EnumProcesses.restype = wintypes.BOOL

    _psapi.GetModuleBaseNameW.argtypes = [
        wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD,
    ]
    _psapi.GetModuleBaseNameW.restype = wintypes.DWORD


# ---------------------------------------------------------------------------
# Process discovery
# ---------------------------------------------------------------------------

def find_pid(exe_names: list) -> Optional[Tuple[int, str]]:
    """Return (pid, exe_name) of the first running process whose image name
    matches any entry in exe_names (case-insensitive). None if not found.

    Uses tasklist (cheap, no admin) rather than EnumProcesses (needs to
    OpenProcess each one). exe_names may include extension or not.
    """
    if sys.platform != "win32":
        return None
    wants = {n.lower() if n.lower().endswith(".exe") else n.lower() + ".exe"
             for n in exe_names}
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
            creationflags=creationflags,
        )
    except Exception as e:
        logger.debug(f"tasklist failed: {e}")
        return None
    for line in out.stdout.splitlines():
        # CSV: "image","PID","SessionName","Session#","MemUsage"
        parts = [p.strip().strip('"') for p in line.split('","')]
        if len(parts) < 2:
            continue
        name = parts[0].lstrip('"').lower()
        if name in wants:
            try:
                pid = int(parts[1])
            except ValueError:
                continue
            return pid, parts[0].lstrip('"')
    return None


def get_process_bitness(pid: int) -> Optional[str]:
    """Return '64' or '32' for the process bitness, or None on failure.

    Uses IsWow64Process2 on Win10+ which gives us the actual native arch;
    otherwise falls back to IsWow64Process which just tells us "is it WoW64".
    """
    if sys.platform != "win32":
        return None
    h = _kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        # Try a more limited access (some processes deny VM access but allow
        # query-limited).
        h = _kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
    try:
        if _HAS_IS_WOW64_PROCESS_2:
            proc_machine = wintypes.USHORT(0)
            host_machine = wintypes.USHORT(0)
            if _kernel32.IsWow64Process2(h, ctypes.byref(proc_machine),
                                         ctypes.byref(host_machine)):
                # IMAGE_FILE_MACHINE_I386 = 0x014c
                # IMAGE_FILE_MACHINE_UNKNOWN (0) = process is native to host
                if proc_machine.value == 0x014c:
                    return "32"
                # Native -> bitness comes from host_machine.
                # 0x8664 = AMD64, 0xAA64 = ARM64 (treat as 64-bit).
                if host_machine.value in (0x8664, 0xAA64):
                    return "64"
                if host_machine.value == 0x014c:
                    return "32"
        # Fallback.
        is_wow = wintypes.BOOL(False)
        if _kernel32.IsWow64Process(h, ctypes.byref(is_wow)):
            # On 64-bit Windows: WoW64 -> 32-bit process.
            # On 32-bit Windows: never WoW64.
            if is_wow.value:
                return "32"
            # Not WoW64 → matches host bitness. We assume 64 unless Python is 32.
            return "64" if ctypes.sizeof(ctypes.c_void_p) == 8 else "32"
    finally:
        _kernel32.CloseHandle(h)
    return None


# ---------------------------------------------------------------------------
# DLL injection — classic CreateRemoteThread + LoadLibraryW.
# ---------------------------------------------------------------------------

def _last_error_str() -> str:
    err = ctypes.get_last_error()
    if err == 0:
        return ""
    buf = ctypes.create_unicode_buffer(512)
    FORMAT_MESSAGE_FROM_SYSTEM = 0x00001000
    FORMAT_MESSAGE_IGNORE_INSERTS = 0x00000200
    n = ctypes.windll.kernel32.FormatMessageW(
        FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        None, err, 0, buf, len(buf), None,
    )
    return f"err={err} ({buf.value.strip() if n else ''})"


def inject_dll(pid: int, dll_path: Path) -> Tuple[bool, str]:
    """Inject a DLL into the target process.

    Returns (ok, message). On failure the message describes the failing
    Win32 step. We do NOT consider a non-zero remote-thread exit code a
    failure here — LoadLibraryW returns the HMODULE (or 0) but on 64-bit
    Windows GetExitCodeThread truncates the value to 32 bits and the
    truncated value is often nonzero even on success. We just check the
    thread completed.

    Side-effects: allocates and frees a small page in the target's VM.
    """
    if sys.platform != "win32":
        return False, "DLL injection is Windows-only"
    dll_path = Path(dll_path).resolve()
    if not dll_path.exists():
        return False, f"DLL not found: {dll_path}"

    dll_w = str(dll_path) + "\0"
    dll_w_bytes = dll_w.encode("utf-16-le")

    h_proc = _kernel32.OpenProcess(INJECT_ACCESS, False, pid)
    if not h_proc:
        return False, f"OpenProcess failed: {_last_error_str()}"

    remote_addr = None
    h_thread = None
    try:
        remote_addr = _kernel32.VirtualAllocEx(
            h_proc, None, len(dll_w_bytes),
            MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE,
        )
        if not remote_addr:
            return False, f"VirtualAllocEx failed: {_last_error_str()}"

        written = ctypes.c_size_t(0)
        ok = _kernel32.WriteProcessMemory(
            h_proc, remote_addr, dll_w_bytes, len(dll_w_bytes),
            ctypes.byref(written),
        )
        if not ok or written.value != len(dll_w_bytes):
            return False, f"WriteProcessMemory failed: {_last_error_str()}"

        # LoadLibraryW lives in kernel32.dll, which is at the same base
        # address in every process on the same machine (until ASLR changes
        # at boot, which is fine — we always look it up fresh). So passing
        # our own LoadLibraryW pointer to CreateRemoteThread works.
        kernel32 = _kernel32.GetModuleHandleW("kernel32.dll")
        if not kernel32:
            return False, "GetModuleHandle(kernel32) failed"
        load_library = _kernel32.GetProcAddress(kernel32, b"LoadLibraryW")
        if not load_library:
            return False, "GetProcAddress(LoadLibraryW) failed"

        thread_id = wintypes.DWORD(0)
        h_thread = _kernel32.CreateRemoteThread(
            h_proc, None, 0, load_library, remote_addr, 0,
            ctypes.byref(thread_id),
        )
        if not h_thread:
            return False, f"CreateRemoteThread failed: {_last_error_str()}"

        # Wait up to 15s for LoadLibraryW to return. The DLL itself returns
        # quickly (DllMain spawns a thread and returns); we're just waiting
        # for the loader, not the worker.
        WAIT_TIMEOUT  = 0x00000102
        WAIT_OBJECT_0 = 0x00000000
        rc = _kernel32.WaitForSingleObject(h_thread, 15000)
        if rc == WAIT_TIMEOUT:
            return False, "remote LoadLibrary timed out (15s) — DLL may be hung in DllMain"
        if rc != WAIT_OBJECT_0:
            return False, f"WaitForSingleObject rc={rc} {_last_error_str()}"

        exit_code = wintypes.DWORD(0)
        _kernel32.GetExitCodeThread(h_thread, ctypes.byref(exit_code))
        # exit_code is the truncated HMODULE returned by LoadLibraryW. Zero
        # means LoadLibrary failed (DLL missing dependency, wrong bitness,
        # blocked by AV, …). Nonzero means it loaded; we cannot distinguish
        # success vs partial success from here — for that, check
        # %LocalAppData%\AJiaSu\inject.log which the DLL writes.
        if exit_code.value == 0:
            return False, ("remote LoadLibrary returned 0 — DLL failed to "
                           "load. Likely causes: bitness mismatch, missing "
                           "VC runtime, AV block. Check Windows Event Viewer.")
        return True, f"injected (LoadLibrary thread exit=0x{exit_code.value:x})"
    finally:
        if h_thread:
            _kernel32.CloseHandle(h_thread)
        if remote_addr:
            _kernel32.VirtualFreeEx(h_proc, remote_addr, 0, MEM_RELEASE)
        _kernel32.CloseHandle(h_proc)


# ---------------------------------------------------------------------------
# High-level entrypoint used by the GUI.
# ---------------------------------------------------------------------------

def _resolve_dll_dir() -> Path:
    """Where the built DLLs live.

    - Source checkout: bridge_inject/dist/
    - PyInstaller frozen: sys._MEIPASS (build.spec bundles them)
    - Fallback: next to the executable
    """
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass))
        candidates.append(Path(sys.executable).parent)
    candidates.append(Path(__file__).parent / "bridge_inject" / "dist")
    candidates.append(Path(__file__).parent)
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


def dll_for_bitness(bitness: str) -> Path:
    name = f"sciter_bridge_{'x64' if bitness == '64' else 'x86'}.dll"
    return _resolve_dll_dir() / name


# Process names to match. Order matters — HD_AJiaSu.exe is the actually-
# running client; AJiaSu.exe may just be the launcher.
AJIASU_EXE_NAMES = ["HD_AJiaSu.exe", "AJiaSu.exe", "AJiaSu_HD.exe"]


def inject_into_ajiasu() -> Tuple[bool, str]:
    """Find the running AJiaSu process and inject sciter_bridge.dll.

    Returns (ok, message). Message is human-friendly; the GUI shows it.
    """
    if sys.platform != "win32":
        return False, "运行时注入仅支持 Windows"

    found = find_pid(AJIASU_EXE_NAMES)
    if not found:
        return False, "未找到运行中的 AJiaSu 进程,请先启动爱加速并登录到主界面"
    pid, exe = found
    logger.info(f"AJiaSu PID={pid} ({exe})")

    bitness = get_process_bitness(pid) or "64"
    dll = dll_for_bitness(bitness)
    if not dll.exists():
        return False, (f"找不到 {dll.name}。请先 build bridge_inject "
                       f"(预期路径: {dll})")
    logger.info(f"using DLL: {dll}")

    ok, msg = inject_dll(pid, dll)
    if not ok:
        return False, f"注入失败: {msg}"
    return True, (f"已注入 {dll.name} → {exe} (pid {pid})。"
                  f"请等 1-2 秒;如果桥仍未连接,看 "
                  f"%LocalAppData%\\AJiaSu\\inject.log")


# Support running as a module for one-shot manual testing.
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    ok, msg = inject_into_ajiasu()
    print(("OK: " if ok else "FAIL: ") + msg)
    sys.exit(0 if ok else 1)
