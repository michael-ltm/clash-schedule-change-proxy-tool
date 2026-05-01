# 爱加速 (AJiaSu) 模式 — 技术文档 / 故障排查手册

> 这份文档的目标读者:**Windows 上协助调试的 AI / 开发者本人**。
> 涵盖架构、关键文件、API 依赖、所有失败点和对应排查步骤。

---

## 1. 一句话目标

让本工具(原本只支持 Clash Verge)用相同的 UX —— 选分组、设间隔、定时切换 —— 来自动切换 **爱加速 (AJiaSu)** 客户端的节点。

爱加速本身**没有公开 HTTP API**,所以我们走"代码注入 + HTTP IPC"的路子。

---

## 2. 整体架构

```
┌──────────────────────────────────────────┐         ┌─────────────────────────────────────┐
│  我们的工具 (Python + customtkinter)       │         │  爱加速进程 (Windows GUI app)          │
│                                          │         │                                     │
│  ┌────────────────┐                      │         │  ┌────────────────────────────┐     │
│  │ AJiaSuAPI       │  HTTP server         │  HTTP   │  │ ajiasu_bridge.js (注入)     │    │
│  │ (Python 端)     │  127.0.0.1:62517     │  IPC    │  │ - document.timer 定时轮询   │    │
│  │                 │ ◄──── fetch() ───────│         │  │ - 调 xcall 触达 native      │    │
│  │ 发命令/收结果    │ ────── resp ────────►│         │  │ - 结果随下次 poll 回传      │    │
│  └────────────────┘                      │         │  └────────────────────────────┘     │
│        │                                 │         │            │                        │
│        ▼                                 │         │            ▼ xcall                  │
│  switcher / scheduler / GUI              │         │  vpnConnect / getOrderedAllServers   │
│                                          │         │  pingMultiServer / getVpnStats ...  │
└──────────────────────────────────────────┘         │            │                        │
                                                      │            ▼ 真实 VPN 操作            │
                                                      │  Sciter (sciter.dll) + native C++     │
                                                      └─────────────────────────────────────┘
```

**关键点**:
- 爱加速 UI 是 [Sciter](https://sciter.com/) 引擎(QuickJS 内核)绘制,UI 资源在 `res.fvr` (其实是 zip)
- 我们把 `ajiasu_bridge.js` 的内容注入到 `window-main.htm` 的 body `<script>` 块末尾(Sciter 不执行新增的 `<script>` 标签)
- 爱加速启动 → 加载主窗口 → 我们的代码一并执行 → 它通过 `Window.this.xcall(...)` 调用 native 端
- 通信通道是 HTTP:`127.0.0.1:62517` 上的轮询式 IPC(桥用 `fetch()` 轮询,Python 端用内嵌 HTTP server)
- **为什么不用文件 IPC**:这个版本的 Sciter 的 `@sys` 模块没有 `fs.$writefile`,只有只读文件 API

---

## 3. 关键 exe — `AJiaSu.exe` vs `HD_AJiaSu.exe`

**很重要,踩过坑**。爱加速分两层:

| exe 名 | 角色 | 通常位置 |
|---|---|---|
| `AJiaSu.exe` | **启动器**,也是安装包里那个 | `C:\Program Files\AJiaSu\` 或用户安装目录 |
| `HD_AJiaSu.exe` | **真正的客户端**,启动器从更新服拉下来后运行的 | `%LocalAppData%\AJiaSu\` 或 `%AppData%\AJiaSu\` 之类 |

每个 exe 旁边都有自己的 `res.fvr`。**补丁必须打到当前真正运行的那个 exe 旁边的 res.fvr**,否则桥脚本永远不会被加载。

`ajiasu_detector.py`:
- `EXE_NAMES = ["HD_AJiaSu.exe", "AJiaSu.exe", "AJiaSu_HD.exe"]`
- `find_running_install_dir()` 用 **WMIC** 查运行中进程的真实路径(PowerShell 兜底)
- `detect_install_dir()` **优先**用运行中进程目录,再退到候选路径扫描

**故障**:补丁打了但 `bridge.log` 不存在 / `ready.txt` 不存在 → 99% 是补丁打到了启动器目录,真正运行的 HD_AJiaSu.exe 在另一处。

修复:**保持爱加速运行**,在我们工具里 ⚙ → "自动",WMIC 会拿到运行中 HD 的真实目录;关掉爱加速,再点"安装桥接",这次就打对了。

---

## 4. 文件清单(项目根)

| 文件 | 作用 |
|---|---|
| `ajiasu_bridge.js` | 桥脚本,运行在爱加速 Sciter 进程里。**代码被内联注入到 window-main.htm 的 body `<script>` 块末尾**,通过 `fetch()` 与 Python HTTP server 通信 |
| `ajiasu_patcher.py` | 打/卸补丁:zip 重写 `res.fvr`,在最后一个 `</script>` 之前注入桥代码(用 `/* AJIASU-BRIDGE-START/END */` 标记),首次会备份 `res.fvr.bak`。幂等。提供 `can_write()` / `is_patched()` |
| `ajiasu_detector.py` | 自动检测安装目录(WMIC 优先 + 候选扫描),检测进程是否在跑 |
| `ajiasu_api.py` | Python 端 HTTP IPC 服务端。内嵌 HTTP server 在 `127.0.0.1:62517`,接口形态与 `ClashAPI` 对齐,GUI 可用同一套调度器 |
| `win_admin.py` | UAC:`is_admin()` / `relaunch_as_admin()` (`ShellExecute runas`) / `can_write_path()` |
| `scheduler.py` | `ProxySwitcher` (Clash) + `AJiaSuProxySwitcher` (AJiaSu) + `ProxyScheduler` (秒级倒计时,纯 Python timer) |
| `gui.py` | customtkinter 界面,顶部 SegmentedButton 切 Clash / 爱加速 |
| `config.py` | JSON 配置;`mode` / `interval_seconds` / `ajiasu_install_path` / `ajiasu_patch_ever_installed` 等 |
| `i18n.py` | zh_CN / en_US 双语 |

---

## 5. 桥脚本 v14 (`ajiasu_bridge.js`) 关键设计

```js
// 核心架构: 连续 fetch 链 + document.timer 看门狗
// - 正常运行: fetch().then() → doFetch() → fetch().then() → ... (无限链)
// - 错误恢复: .catch() 设置 _loopActive=false → 看门狗每5s重启一次
// - 服务器返回命令(JSON)或 "none"
// - 有命令就 dispatch → 结果存 _pendingResult,下次 fetch 用 POST 发送

function doFetch() {
    _loopActive = true;
    fetch(BASE + "/bridge/poll?hb=1", opts)
        .then(r => r.text())
        .then(body => { /* dispatch if command */ doFetch(); })
        .catch(() => { _loopActive = false; }); // 看门狗会重启
}
// 看门狗: 每5s检查一次
document.timer(5000, function() {
    if (!_loopActive) doFetch();
    return true;
});
```

**Sciter promise 特性**: fetch() 返回的 Promise 的 .then() 回调首次解析延迟 ~5s(Sciter 空闲事件循环阶段才处理 microtask),但一旦开始执行,后续 .then() 在同一批次内立即执行。因此连续 fetch 链在稳态下可达 ~40ms 命令响应。

**服务器端长轮询**: 无命令时,Python HTTP 服务器 hold 2s 再返回 "none",用 `cmd_available` Event 实现新命令到达时立即唤醒。

**为什么用 HTTP 而不用文件 IPC**: 这个版本的 Sciter(爱加速 4.9.6.0)的 `@sys.fs` 模块**没有 `$writefile`**,只有只读 API。`fetch()` 可以正常访问 localhost。

**为什么注入到 body `<script>` 而不是新增 `<script>` 标签**: Sciter 不执行运行时新增到 DOM 的 `<script>` 标签。唯一能执行注入代码的方式是追加到**已有的 `<script>` 块**末尾。

**注入代码中不能出现 `<script>` 字面量**: Sciter 的 HTML 解析器会把 JS 注释/字符串中的 `<script>` 当作标签解析,导致整个脚本块被截断。

### 协议

桥每 400ms 轮询 Python HTTP server:

- `GET /bridge/poll?hb=1` → 服务器返回命令 JSON 或 `"none"`
- `POST /bridge/poll?hb=1` (body = 上次结果) → 服务器收结果 + 返回下条命令
- `POST /bridge/hello` → 桥启动时发送,附带版本信息

支持的 action:`ping` / `version` / `accountName` / `list` / `fullList` / `favorites` / `recent` / `status` / `pingReports` / `isPicking` / `connect` / `disconnect` / `cancelPick` / `pick` / `pingServers` / `getConfig` / `setConfig` / `getConfigs` / `bridgeInfo` / `xcall`(任意 escape hatch)。

---

## 6. 我们依赖的 native xcall 名字 (反汇编 AJiaSu_4.9.6.0 得到)

如果爱加速更新后改了名字,这些调用就会失败 — 用 GUI 的"查看桥日志"按钮可以看到诊断信息。

```
vpnConnect(srvId)           // 连节点
vpnDisconnect()             // 断开
isServerPicking()           // 是否在智能选节点
cancelPickServerFromWeb()   // 取消智能选
pickServerFromWeb(level, code, servers)
getOrderedAllServers()      // 全部节点 (排好序)
getFullLoadServers()        // 满载节点 ID 列表
getFavoriteServersFromLocal()
getRecentlyUsedServers()
getVpnStats()               // 当前连接状态
pingMultiServer({serverIdList: [...]})
getPingReports()
getClientVersion()
getAccountName()
getUserConfig(key, def)
setUserConfig(key, value)
getUserConfigs()
```

**不确定的是返回 JSON 的字段名**:节点对象的 `Id` / `id` / `ServerId`、`Name` / `name`、`CategoryCode` 等。`ajiasu_api.py` 用 `ID_FIELDS / NAME_FIELDS / CATEGORY_FIELDS` 容错探测多个候选。

GUI 提供 **"导出原始数据"** 按钮:把 `getOrderedAllServers / getVpnStats / favorites / recent` 原始 JSON dump 到 `%TEMP%\ajiasu_raw.json`,可以查看真实字段名,如果字段名变了改 `ajiasu_api.py` 的常量列表即可。

---

## 7. HTTP IPC 通信

Python 端在 `127.0.0.1:62517` 启动一个 HTTP server(`AJiaSuAPI.start_server()`),桥脚本通过 `fetch()` 连续轮询(long-polling)。

| 端点 | 方法 | 用途 |
|---|---|---|
| `/bridge/poll?hb=1` | GET 或 POST | 桥轮询命令 + 提交上次结果;`hb=1` 同时作为心跳。无命令时服务器 hold 2s 再返回 |
| `/ping` | GET | 简单探活 |

Python 端用 `is_alive()` 检查上次心跳时间是否在 5s 以内。

**注意**: 端口 62517 是固定的,不支持多实例同时运行。

**性能**: 稳态下命令响应延迟 ~40ms,首次连接需 ~5s(Sciter promise 初始化)。

---

## 8. 常见故障树

```
GUI 顶部状态显示"爱加速桥未响应"
│
├─ ① C:\Users\Public\AJiaSu\bridge.log 不存在
│   └─ 桥脚本根本没在爱加速进程里跑起来
│       ├─ 补丁没生效 → 检查 res.fvr 是否被改:
│       │   解压 res.fvr 看 window-main.htm 是否含 <!-- AJIASU-BRIDGE-INSTALLED -->
│       │   ajiasu_bridge.js 是否在压缩包里
│       └─ 补丁打到了错误的 res.fvr (启动器/真实客户端不同目录)
│           → 保持爱加速运行,⚙ → "自动" 重新检测;
│             此时日志显示"已锁定运行中爱加速的目录"才对
│
├─ ② bridge.log 存在但很短,只有 BOOT FATAL: ...
│   └─ 桥脚本一进来就崩,八成是 sys.fs API 名字不对
│       (这版 Sciter 不支持 $writefile/$mkdir/$readfile 之一)
│       → 看具体错误信息,改 ajiasu_bridge.js 用 async 版 (sys.fs.readfile 而非 $readfile)
│
├─ ③ bridge.log 有 "boot done" 但 ready.txt mtime 不更新
│   └─ document.timer 没跑 → setInterval 会兜底,看 log 是否有 "fallback ok"
│       如果两个都失败,就要找 Sciter 版本对应的 timer API
│
├─ ④ ready.txt 每秒在更新 (桥活着) 但 Python 端读不到
│   └─ 路径不一致:Python 期望 C:\Users\Public\AJiaSu,
│       桥实际写到了别处 → 看 bridge.log 第一行 "ipc dir = ..."
│
└─ ⑤ 一切都对,IPC 也通,但 xcall 失败
    └─ bridge.log 会有 "xcall failed: vpnConnect err=..."
       说明爱加速版本变化,native 函数被重命名
       → 用 strings AJiaSu.exe 重新对照
```

---

## 9. UAC 与权限

只有装在 `C:\Program Files\` 的 res.fvr 改不动时才需要管理员。我们的策略:
- **不**全局加 UAC manifest(避免普通启动也弹 UAC)
- 打补丁前 `os.access(res, W_OK) + IsUserAnAdmin()` 预检
- 写不动且非管理员 → 弹 messagebox 询问"是否以管理员身份重启"
- 同意 → `ShellExecuteW("runas", ...)` 重启自己,当前进程退出,新进程已是管理员上下文

桥跑起来后通信全在 `C:\Users\Public\` 下,**任何账号都能读写,运行期不需要管理员**。

---

## 10. GUI 关键路径(防卡)

慢调用全挪到后台线程,完成后用 `root.after(0, ...)` 切回主线程:

| GUI 调用 | 慢点 | 已挪到线程 |
|---|---|---|
| `_patch_ajiasu` | tasklist (~5s) + zip 重写 (~1-2s) | ✅ |
| `_unpatch_ajiasu` | 同上 | ✅ |
| `_refresh_groups` | 桥离线时 IPC 8s 超时 | ✅,且 AJiaSu 模式先 `is_alive()` 短路 |
| `_on_group_selected` | 同上 | ✅ |
| `_test_all_proxies` | ping 多节点 | ✅(原本就有) |
| `_switch_now` | 切节点 | ✅(原本就有) |
| `_dump_ajiasu_raw` | 多次 IPC | ✅ |
| `_auto_detect_ajiasu_clicked` | WMIC 调用 | ✅ |
| `_init_ajiasu_connection` | test_connection | ✅ |
| `_sync_with_backend` | 周期同步 | ✅,先 `is_alive()` 短路 |

**判断 GUI 卡了**:点击响应迟、Windows 标题栏显示"未响应"。这通常意味着主线程还在跑 IPC 或 subprocess,需要补一个 thread 包装。

---

## 11. 故障诊断标准操作流程 (SOP)

> **当用户报"桥未响应"时,按以下顺序问 / 看**:

1. **任务管理器看进程名**
   - `HD_AJiaSu.exe` 在跑 → 启动器和真实客户端不同目录,接 SOP 步骤 2
   - `AJiaSu.exe` 在跑 → 单 exe 模式,接 SOP 步骤 3
   - 都不在 → 用户没启动爱加速

2. **保持爱加速运行,工具里点 ⚙ → 自动**
   - 日志显示"已锁定运行中爱加速的目录: X"
   - 检查 X 是不是和你之前打补丁的目录一样,不一样的话说明前面打错地方了
   - 关掉爱加速 → 重新点"安装桥接" → 再启动爱加速

3. **看 `C:\Users\Public\AJiaSu\bridge.log`**
   - 不存在 → 补丁没生效。`unzip res.fvr` 检查 ajiasu_bridge.js 是否真的进去了,window-main.htm 有没有那行 script
   - 存在但只有 "BOOT FATAL" → 看具体异常,大概率 Sciter 这版的 API 名字与桥用的不一致
   - 存在且有 "boot done" → 应该正常,看 ready.txt mtime,如果不更新就是 timer 不工作

4. **看 `C:\Users\Public\AJiaSu\ready.txt`**
   - mtime 在最近 5 秒内 → 桥在跑,Python 端的问题
   - mtime 很久 / 不更新 → 桥被加载了但 timer 卡住

5. **导出原始数据 (设置面板里的"导出原始数据"按钮)**
   - 检查 `%TEMP%\ajiasu_raw.json` 里 servers 数组每项的字段名
   - 如果 `Id` / `Name` 等不存在,需要改 `ajiasu_api.py` 的字段映射

---

## 12. 升级/兼容性注意

- 爱加速自动更新会**覆盖** `res.fvr` → 桥被擦掉。我们存了 `ajiasu_patch_ever_installed` 标记,启动检测到"曾经装过但现在没了"会显示橙色横幅"补丁被覆盖,点这里重新安装"
- xcall 函数名重命名:bridge.log 会显示 `xcall failed: <name> err=...`,改 `ajiasu_bridge.js` 里 `handlers` 即可
- res.fvr 字段名变更:dump 原始数据,改 `ajiasu_api.py` 里 `ID_FIELDS` / `NAME_FIELDS` / `CATEGORY_FIELDS`
- Sciter 版本升级:它的 `@sys` 模块 API 可能微调,bridge.log 启动时会 dump `Object.keys(sys.fs)`,出错时一目了然

---

## 13. 调试快捷入口

| 任务 | 怎么做 |
|---|---|
| 看桥日志 | GUI 设置面板 → "查看桥日志" 按钮(用记事本打开 + tail 50 行进 GUI 日志栏) |
| 看节点字段名 | GUI 设置面板 → "导出原始数据"(写到 `%TEMP%\ajiasu_raw.json`) |
| 看是不是真打补丁了 | 解压 `res.fvr`(它是 zip),看 `ajiasu_bridge.js` 在不在,`window-main.htm` 末尾有没有 marker |
| 看哪个 exe 在跑 | 任务管理器 / `tasklist /FI "IMAGENAME eq HD_AJiaSu.exe"` |
| 看运行中进程的真实路径 | `wmic process where "name='HD_AJiaSu.exe'" get ExecutablePath` |
| 重置补丁状态 | 删 `res.fvr.bak` 重来,或工具里"卸载桥接" |

---

## 14. 已知不支持

- 爱加速登录界面阶段:桥脚本是跟着 `window-main.htm` 加载的,**必须登录进去主窗口**才会启动桥
- 多账号 / 多实例并发:IPC 文件是固定路径,两个工具实例同时操作会乱
- 非 Windows:仅 Windows;EXE 只在 Windows 跑,WMIC 也是 Windows 命令

---

## 15. 仓库 / 当前版本

- repo: <https://github.com/michael-ltm/clash-schedule-change-proxy-tool>
- 入口:`main.py` → `gui.py:IntervalProxyGUI`
- 当前版本见 `pyproject.toml` 的 `version`(每次发版会同步打 git tag `vX.Y.Z`,触发 GitHub Actions 构建 Windows + macOS 包发到 Releases)
