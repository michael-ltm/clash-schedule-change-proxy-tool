// sciter_bridge.cpp — runtime memory injection bridge for AJiaSu (爱加速)
//
// Purpose
//   Live-injects ajiasu_bridge.js into the Sciter scripting engine inside the
//   already-running HD_AJiaSu.exe / AJiaSu.exe process, without modifying
//   res.fvr on disk. This is the "memory-patch" alternative to the disk
//   patcher in ../ajiasu_patcher.py.
//
// Lifecycle
//   1. Python (../ajiasu_injector.py) finds the AJiaSu PID, opens the process,
//      VirtualAllocEx + WriteProcessMemory the path of THIS DLL, then
//      CreateRemoteThread(LoadLibraryW, dll_path).
//   2. The Windows loader fires DllMain(DLL_PROCESS_ATTACH).
//   3. DllMain spawns a worker thread — per MSDN, doing real work in DllMain
//      itself can deadlock the loader.
//   4. Worker thread:
//      a. Resolves sciter.dll's SciterAPI() entry point. Uses the Sciter SDK
//         headers (pulled by CMake FetchContent) for the canonical
//         ISciterAPI struct layout — that's the only way to be safe across
//         Sciter point releases.
//      b. Polls EnumWindows up to 30s for a top-level visible window owned by
//         this process whose class name starts with "scite" (Sciter window
//         classes: SCITER, SciterLD, SciterOSL, …).
//      c. Loads bridge.js text:
//           1) %LocalAppData%\AJiaSu\bridge.js  (developer override / hot-edit)
//           2) Embedded RCDATA resource          (production fallback)
//      d. Subclasses that window with a tiny WndProc that, on receipt of our
//         registered window message, calls SciterAPI()->SciterEval on the UI
//         thread (the only thread allowed to touch Sciter), then immediately
//         un-subclasses itself.
//      e. Sends the registered message synchronously. SciterEval runs.
//   5. Once SciterEval returns, the bridge JS is live in the Sciter VM and
//      behaves exactly the same as the disk-patched version: HTTP-poll IPC to
//      127.0.0.1:62517.
//
// What this DOES NOT handle (intentionally — keeps the DLL minimal)
//   - Re-injection after AJiaSu restart. Python side polls and re-injects.
//   - 32-bit / 64-bit selection. Python injector picks the right DLL.
//   - Logging beyond a single line per step appended to
//     %LocalAppData%\AJiaSu\inject.log. Best-effort, ignores failures.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shlobj.h>
#include <string>
#include <vector>
#include <cstdio>

// Sciter SDK — pulled via CMake FetchContent (see CMakeLists.txt). We only
// need the function-pointer struct ISciterAPI; everything else (DOM, value
// types, behaviour API) we don't touch, but the headers will pull a lot of
// declarations regardless. That's fine — they're declarations only, no
// linker dependency on sciter.lib.
#define _SCITER_BUILD_      // suppress sciter graphics/text linkage assumptions
#include "sciter-x-api.h"   // declares ISciterAPI and SciterAPI()

// Embedded resource. See bridge_resource.rc — RCDATA id 1 is bridge.js bytes.
#ifndef IDR_BRIDGE_JS
#  define IDR_BRIDGE_JS 1
#endif

// ------------------------------------------------------------------
// Tiny logger: one timestamped line per call to
// %LocalAppData%\AJiaSu\inject.log. Failures are silent — logging is
// strictly best-effort.
// ------------------------------------------------------------------
static std::wstring AjiasuDataDir() {
    wchar_t buf[MAX_PATH] = L"";
    if (FAILED(SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA, NULL, 0, buf)))
        return L"";
    std::wstring p = buf;
    p += L"\\AJiaSu";
    CreateDirectoryW(p.c_str(), NULL);
    return p;
}

static void Logf(const char* fmt, ...) {
    std::wstring dir = AjiasuDataDir();
    if (dir.empty()) return;
    std::wstring path = dir + L"\\inject.log";

    char buf[1024] = "";
    va_list ap;
    va_start(ap, fmt);
    _vsnprintf_s(buf, sizeof(buf), _TRUNCATE, fmt, ap);
    va_end(ap);

    SYSTEMTIME st; GetLocalTime(&st);
    char line[1280];
    _snprintf_s(line, sizeof(line), _TRUNCATE,
        "[%02d:%02d:%02d.%03d pid=%lu] %s\r\n",
        st.wHour, st.wMinute, st.wSecond, st.wMilliseconds,
        GetCurrentProcessId(), buf);

    HANDLE h = CreateFileW(path.c_str(), FILE_APPEND_DATA, FILE_SHARE_READ,
                           NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h != INVALID_HANDLE_VALUE) {
        DWORD wrote;
        SetFilePointer(h, 0, NULL, FILE_END);
        WriteFile(h, line, (DWORD)strlen(line), &wrote, NULL);
        CloseHandle(h);
    }
}

// ------------------------------------------------------------------
// Bridge JS source loading: %LocalAppData%\AJiaSu\bridge.js first
// (lets the Python side hot-update without rebuilding the DLL), then
// the embedded RCDATA resource. Both yield UTF-8 bytes; we widen to
// UTF-16 because SciterEval takes LPCWSTR.
// ------------------------------------------------------------------
static bool ReadFileBytes(const std::wstring& path, std::string& out) {
    HANDLE h = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ,
                           NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return false;
    LARGE_INTEGER sz; GetFileSizeEx(h, &sz);
    if (sz.QuadPart <= 0 || sz.QuadPart > (16 * 1024 * 1024)) { CloseHandle(h); return false; }
    out.resize((size_t)sz.QuadPart);
    DWORD got = 0;
    BOOL ok = ReadFile(h, out.data(), (DWORD)out.size(), &got, NULL);
    CloseHandle(h);
    return ok && got == out.size();
}

static bool LoadEmbeddedJs(std::string& out) {
    HMODULE self = NULL;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
                       GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCWSTR)&LoadEmbeddedJs, &self);
    if (!self) return false;
    // RT_RCDATA expands to LPSTR (narrow) when UNICODE is not defined; we
    // explicitly call the W variant of FindResource so we pass the wide form.
    // Numeric value of RT_RCDATA is 10.
    HRSRC r = FindResourceW(self, MAKEINTRESOURCEW(IDR_BRIDGE_JS),
                            MAKEINTRESOURCEW(10));
    if (!r) return false;
    HGLOBAL g = LoadResource(self, r);
    if (!g) return false;
    DWORD sz = SizeofResource(self, r);
    const char* p = (const char*)LockResource(g);
    if (!p || sz == 0) return false;
    out.assign(p, sz);
    return true;
}

static std::wstring Utf8ToWide(const std::string& s) {
    if (s.empty()) return std::wstring();
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), NULL, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), w.data(), n);
    return w;
}

static std::wstring LoadBridgeJs() {
    std::wstring dir = AjiasuDataDir();
    if (!dir.empty()) {
        std::string utf8;
        if (ReadFileBytes(dir + L"\\bridge.js", utf8)) {
            Logf("bridge.js: loaded from disk (%zu bytes)", utf8.size());
            return Utf8ToWide(utf8);
        }
    }
    std::string utf8;
    if (LoadEmbeddedJs(utf8)) {
        Logf("bridge.js: loaded from embedded resource (%zu bytes)", utf8.size());
        return Utf8ToWide(utf8);
    }
    Logf("bridge.js: NOT FOUND (neither disk nor embedded resource)");
    return std::wstring();
}

// ------------------------------------------------------------------
// Find a Sciter window in the current process.
//
// Sciter window classes seen in the wild: "SCITER", "SciterLD", "SciterOSL".
// All start with "scite" (case-insensitive). We pick the first visible
// top-level window owned by our PID matching this prefix.
// ------------------------------------------------------------------
struct FindCtx { DWORD pid; HWND hwnd; };

static BOOL CALLBACK EnumWindowsCb(HWND hwnd, LPARAM lp) {
    FindCtx* ctx = (FindCtx*)lp;
    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    if (pid != ctx->pid) return TRUE;
    if (!IsWindowVisible(hwnd)) return TRUE;

    wchar_t cls[64] = L"";
    GetClassNameW(hwnd, cls, 63);
    static const wchar_t* WANT = L"scite";
    for (int i = 0; i < 5; ++i) {
        wchar_t c = cls[i];
        if (c >= L'A' && c <= L'Z') c = (wchar_t)(c + (L'a' - L'A'));
        if (c != WANT[i]) return TRUE;
    }
    ctx->hwnd = hwnd;
    return FALSE; // stop
}

static HWND FindSciterWindow() {
    FindCtx ctx; ctx.pid = GetCurrentProcessId(); ctx.hwnd = NULL;
    EnumWindows(EnumWindowsCb, (LPARAM)&ctx);
    return ctx.hwnd;
}

// ------------------------------------------------------------------
// UI-thread trampoline.
//
// SciterEval must be called on the thread that owns the Sciter window.
// Our worker thread is not that thread. So we install a one-shot
// window subclass: when the UI thread receives our registered
// message, it calls SciterEval and removes itself.
// ------------------------------------------------------------------
struct EvalState {
    ISciterAPI*  api;
    std::wstring js;
    UINT         evalMsg;
    WNDPROC      origProc;
    BOOL         evalOk;
};

static EvalState g_eval = {};

static LRESULT CALLBACK SubclassedProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == g_eval.evalMsg) {
        if (g_eval.api && g_eval.api->SciterEval) {
            g_eval.evalOk = g_eval.api->SciterEval(
                hwnd, g_eval.js.c_str(), (UINT)g_eval.js.size(), NULL);
            Logf("SciterEval -> %s", g_eval.evalOk ? "OK" : "FALSE (script error)");
        } else {
            Logf("SciterEval: api or function pointer NULL");
        }
        // Restore the original WndProc so we don't sit in the message loop forever.
        SetWindowLongPtrW(hwnd, GWLP_WNDPROC, (LONG_PTR)g_eval.origProc);
        return 0;
    }
    return CallWindowProcW(g_eval.origProc, hwnd, msg, wp, lp);
}

// ------------------------------------------------------------------
// Worker thread: poll for Sciter window, then run SciterEval on UI thread.
// ------------------------------------------------------------------
static DWORD WINAPI WorkerThread(LPVOID) {
    Logf("worker: starting");

    // sciter.dll is already loaded into the process; GetModuleHandle is fine.
    HMODULE sciter = GetModuleHandleW(L"sciter.dll");
    if (!sciter) sciter = LoadLibraryW(L"sciter.dll");
    if (!sciter) {
        Logf("worker: sciter.dll not loaded in process — abort");
        return 1;
    }

    typedef ISciterAPI* (SCAPI *SciterAPI_t)();
    SciterAPI_t pAPI = (SciterAPI_t)GetProcAddress(sciter, "SciterAPI");
    if (!pAPI) {
        Logf("worker: GetProcAddress(SciterAPI) failed — abort (Sciter version mismatch?)");
        return 2;
    }
    ISciterAPI* api = pAPI();
    if (!api) {
        Logf("worker: SciterAPI() returned NULL — abort");
        return 3;
    }
    Logf("worker: SciterAPI=%p api=%p ver=%u", pAPI, api, (unsigned)api->version);

    // Poll up to 30s for a Sciter window. If we injected during AJiaSu
    // startup, the main window may not exist yet.
    HWND hwnd = NULL;
    for (int i = 0; i < 60 && !hwnd; ++i) {
        hwnd = FindSciterWindow();
        if (!hwnd) Sleep(500);
    }
    if (!hwnd) { Logf("worker: no Sciter window after 30s — abort"); return 4; }
    Logf("worker: Sciter HWND=%p", hwnd);

    std::wstring js = LoadBridgeJs();
    if (js.empty()) { Logf("worker: empty bridge JS — abort"); return 5; }

    g_eval.api      = api;
    g_eval.js       = std::move(js);
    g_eval.evalMsg  = RegisterWindowMessageW(L"AJIASU_BRIDGE_EVAL_v1");
    g_eval.origProc = (WNDPROC)SetWindowLongPtrW(hwnd, GWLP_WNDPROC,
                                                 (LONG_PTR)SubclassedProc);
    if (!g_eval.origProc) {
        Logf("worker: SetWindowLongPtr failed err=%lu", GetLastError());
        return 6;
    }
    // SendMessage is synchronous — blocks until the UI thread runs SubclassedProc.
    SendMessageW(hwnd, g_eval.evalMsg, 0, 0);
    Logf("worker: done (eval %s)", g_eval.evalOk ? "OK" : "FAIL");
    return g_eval.evalOk ? 0 : 7;
}

// ------------------------------------------------------------------
// DllMain — minimal. Spawn the worker and return immediately so the
// loader doesn't deadlock.
// ------------------------------------------------------------------
extern "C" BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinst);
        HANDLE t = CreateThread(NULL, 0, WorkerThread, NULL, 0, NULL);
        if (t) CloseHandle(t);
    }
    return TRUE;
}
