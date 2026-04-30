// AJIASU-BRIDGE v2 — diagnostic edition
// Sciter (QuickJS) inside AJiaSu.exe. Runs in window-main.htm context.
//
// Goals over v1:
// 1) 早期把"我活着"信息落到 bridge.log,即使后续逻辑挂掉也能排错
// 2) IPC 路径用多种格式探测,挑能写入的那一个
// 3) 用 document.timer (windows-main.htm 已经在用,稳) 而不是 setInterval
// 4) 所有 fs 调用 try/catch,异常落到 bridge.log
//
// 协议:
//   request : { id?:string, action:string, ...args }
//   response: { id?:string, ok:bool, result?:any, error?:string }

import * as sys from "@sys";

const POLL_MS = 400;
const HEARTBEAT_EVERY = 5;
const BRIDGE_VERSION = 2;

// 可能的 IPC 根目录;按顺序探测,首个能 mkdir + 写入的胜出。
const IPC_DIR_VARIANTS = [
    "C:\\Users\\Public\\AJiaSu",
    "C:/Users/Public/AJiaSu",
];

let IPC_DIR = IPC_DIR_VARIANTS[0];
let CMD_PATH = "";
let RESULT_PATH = "";
let READY_PATH = "";
let LOG_PATH = "";

const win = Window.this;
const xcall = function() { return win.xcall.apply(win, arguments); };

const enc = new TextEncoder();
const dec = new TextDecoder();

// -------------- fs 安全包装 --------------

function fsExists(path) {
    try { return !!sys.fs.$stat(path); } catch (e) { return false; }
}
function fsMkdir(path) {
    try { sys.fs.$mkdir(path); return true; } catch (e) { return fsExists(path); }
}
function fsRead(path) {
    try {
        const b = sys.fs.$readfile(path);
        return b ? dec.decode(b) : null;
    } catch (e) { return null; }
}
function fsWrite(path, text) {
    try { sys.fs.$writefile(path, enc.encode(text)); return true; }
    catch (e) { return false; }
}
function fsUnlink(path) { try { sys.fs.$unlink(path); } catch (e) {} }

// -------------- 日志 --------------

let logBuffer = ""; // 同时驻留内存,文件写不进去时也至少有内存版

function log(msg) {
    const ts = new Date().toISOString();
    const line = ts + " " + msg + "\n";
    logBuffer += line;
    if (logBuffer.length > 32768) logBuffer = logBuffer.slice(-16384);
    if (LOG_PATH) fsWrite(LOG_PATH, logBuffer);
    try { console.log("[ajiasu-bridge]", msg); } catch (e) {}
}

function setPaths(dir) {
    IPC_DIR = dir;
    CMD_PATH    = dir + "/cmd.json";
    RESULT_PATH = dir + "/result.json";
    READY_PATH  = dir + "/ready.txt";
    LOG_PATH    = dir + "/bridge.log";
}

// -------------- 引导:挑一个能用的 IPC 目录 --------------

function pickIpcDir() {
    for (const dir of IPC_DIR_VARIANTS) {
        const ok = fsMkdir(dir);
        if (!ok) continue;
        const probePath = dir + "/.bridge_probe";
        if (fsWrite(probePath, "ok")) {
            fsUnlink(probePath);
            return dir;
        }
    }
    return IPC_DIR_VARIANTS[0]; // 兜底
}

// -------------- xcall 安全包装 --------------

function safeXcall() {
    try { return win.xcall.apply(win, arguments); }
    catch (e) {
        log("xcall failed: " + (arguments[0] || "?") + " err=" + e);
        throw e;
    }
}

function disconnectIfActive() {
    try {
        if (safeXcall("isServerPicking")) safeXcall("cancelPickServerFromWeb");
        const s = safeXcall("getVpnStats");
        if (s && s.state != 0) safeXcall("vpnDisconnect");
    } catch (e) {}
}

// -------------- 业务命令 --------------

const handlers = {
    ping       : () => "pong",
    bridgeInfo : () => ({ version: BRIDGE_VERSION, ipcDir: IPC_DIR, ts: Date.now() }),
    version    : () => safeXcall("getClientVersion"),
    accountName: () => safeXcall("getAccountName"),

    list       : () => safeXcall("getOrderedAllServers"),
    fullList   : () => safeXcall("getFullLoadServers"),
    favorites  : () => safeXcall("getFavoriteServersFromLocal"),
    recent     : () => safeXcall("getRecentlyUsedServers"),

    status     : () => safeXcall("getVpnStats"),
    pingReports: () => safeXcall("getPingReports"),
    isPicking  : () => safeXcall("isServerPicking"),

    connect    : (req) => {
        if (!req.srvId) throw "srvId required";
        disconnectIfActive();
        return safeXcall("vpnConnect", String(req.srvId));
    },
    disconnect : () => safeXcall("vpnDisconnect"),
    cancelPick : () => safeXcall("cancelPickServerFromWeb"),

    pick       : (req) => {
        disconnectIfActive();
        return safeXcall("pickServerFromWeb",
            req.level || "", req.code || "", req.servers || []);
    },

    pingServers: (req) => safeXcall("pingMultiServer", { serverIdList: req.ids || [] }),

    getConfig  : (req) => safeXcall("getUserConfig", req.key, req.def || ""),
    setConfig  : (req) => safeXcall("setUserConfig", req.key, String(req.value)),
    getConfigs : () => safeXcall("getUserConfigs"),

    xcall      : (req) => {
        const args = [req.name].concat(req.args || []);
        return win.xcall.apply(win, args);
    },
};

function dispatch(req) {
    const fn = handlers[req.action];
    if (!fn) return { ok: false, error: "unknown action: " + req.action };
    try {
        const r = fn(req);
        return { ok: true, result: r === undefined ? null : r };
    } catch (e) {
        return { ok: false, error: String((e && e.message) || e) };
    }
}

// -------------- 主循环 --------------

let tickN = 0;
function tick() {
    tickN++;
    // 心跳:每 HEARTBEAT_EVERY 次刷新一次 ready.txt
    if ((tickN % HEARTBEAT_EVERY) === 0) {
        fsWrite(READY_PATH, String(Date.now()));
    }
    const text = fsRead(CMD_PATH);
    if (!text) return;
    let req;
    try { req = JSON.parse(text); }
    catch (e) {
        fsWrite(RESULT_PATH, JSON.stringify({ ok:false, error:"bad json: "+e }));
        fsUnlink(CMD_PATH);
        return;
    }
    const resp = dispatch(req);
    if (req.id !== undefined) resp.id = req.id;
    fsWrite(RESULT_PATH, JSON.stringify(resp));
    fsUnlink(CMD_PATH);
}

function startTimer() {
    // window-main.htm 自己也用 document.timer,确认在这版 Sciter 一定有
    function loop() {
        try { tick(); } catch (e) { log("tick exception: " + e); }
        return true; // 让 document.timer 重复执行
    }
    try {
        document.timer(POLL_MS, loop);
        log("document.timer scheduled, " + POLL_MS + "ms");
    } catch (e) {
        log("document.timer failed: " + e + ", fallback setInterval");
        try {
            setInterval(loop, POLL_MS);
            log("setInterval fallback ok");
        } catch (e2) {
            log("setInterval fallback failed: " + e2);
        }
    }
}

// -------------- bootstrap --------------

function boot() {
    const dir = pickIpcDir();
    setPaths(dir);

    // 最早期的存活信号:无论后续如何,这一行 ready.txt 都先写出来
    fsWrite(READY_PATH, String(Date.now()));
    fsUnlink(CMD_PATH);

    log("==== bridge boot v" + BRIDGE_VERSION + " ====");
    log("ipc dir = " + IPC_DIR);
    log("paths: cmd=" + CMD_PATH + " result=" + RESULT_PATH + " ready=" + READY_PATH);

    // 看看 sys.fs 长啥样,出错时心里有数
    try {
        const keys = Object.keys(sys.fs || {}).join(",");
        log("sys.fs keys: " + keys);
    } catch (e) { log("inspect sys.fs failed: " + e); }

    // 探活 xcall
    try {
        const v = safeXcall("getClientVersion");
        log("getClientVersion ok: " + v);
    } catch (e) {
        log("getClientVersion failed: " + e);
    }

    startTimer();
    log("boot done, polling " + POLL_MS + "ms");
}

try { boot(); }
catch (e) {
    // 最后一道保险:连引导都崩,把错写到固定路径
    try {
        sys.fs.$mkdir("C:\\Users\\Public\\AJiaSu");
        sys.fs.$writefile(
            "C:\\Users\\Public\\AJiaSu\\bridge.log",
            new TextEncoder().encode("BOOT FATAL: " + e + "\n")
        );
    } catch (e2) {}
}
