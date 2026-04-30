// AJIASU-BRIDGE v1
// External CLI control bridge for AJiaSu (爱加速).
// Loaded inside Sciter (QuickJS). Watches a command file every POLL_MS,
// executes the corresponding native xcall(), writes the result back, then
// deletes the command file.
//
// Protocol (JSON):
//   request : { id?:string, action:string, ...args }
//   response: { id?:string, ok:bool, result?:any, error?:string }
//
// Files (Windows):
//   C:\Users\Public\AJiaSu\cmd.json     <- written by external CLI
//   C:\Users\Public\AJiaSu\result.json  <- written by this script
//   C:\Users\Public\AJiaSu\ready.txt    <- heartbeat, ms since epoch

import * as sys from "@sys";

const POLL_MS     = 400;
const IPC_DIR     = "C:\\Users\\Public\\AJiaSu";
const CMD_PATH    = IPC_DIR + "\\cmd.json";
const RESULT_PATH = IPC_DIR + "\\result.json";
const READY_PATH  = IPC_DIR + "\\ready.txt";
const HEARTBEAT_EVERY = 5;

const win = Window.this;
const xcall = function() { return win.xcall.apply(win, arguments); };

const enc = new TextEncoder();
const dec = new TextDecoder();

function ensureDir(path) { try { sys.fs.$mkdir(path); } catch(e) {} }
function readText(path) {
    try {
        const buf = sys.fs.$readfile(path);
        if (!buf) return null;
        return dec.decode(buf);
    } catch (e) { return null; }
}
function writeText(path, text) {
    try { sys.fs.$writefile(path, enc.encode(text)); return true; }
    catch (e) { return false; }
}
function unlink(path) { try { sys.fs.$unlink(path); } catch(e) {} }

function disconnectIfActive() {
    try {
        if (xcall("isServerPicking")) xcall("cancelPickServerFromWeb");
        const stats = xcall("getVpnStats");
        if (stats && stats.state != 0) xcall("vpnDisconnect");
    } catch(e) {}
}

const handlers = {
    ping       : () => "pong",
    version    : () => xcall("getClientVersion"),
    accountName: () => xcall("getAccountName"),

    list       : () => xcall("getOrderedAllServers"),
    fullList   : () => xcall("getFullLoadServers"),
    favorites  : () => xcall("getFavoriteServersFromLocal"),
    recent     : () => xcall("getRecentlyUsedServers"),

    status     : () => xcall("getVpnStats"),
    pingReports: () => xcall("getPingReports"),
    isPicking  : () => xcall("isServerPicking"),

    connect    : (req) => {
        if (!req.srvId) throw "srvId required";
        disconnectIfActive();
        return xcall("vpnConnect", String(req.srvId));
    },
    disconnect : () => xcall("vpnDisconnect"),
    cancelPick : () => xcall("cancelPickServerFromWeb"),

    pick       : (req) => {
        disconnectIfActive();
        return xcall("pickServerFromWeb",
            req.level || "", req.code || "", req.servers || []);
    },

    pingServers: (req) => xcall("pingMultiServer", { serverIdList: req.ids || [] }),

    getConfig  : (req) => xcall("getUserConfig", req.key, req.def || ""),
    setConfig  : (req) => xcall("setUserConfig", req.key, String(req.value)),
    getConfigs : () => xcall("getUserConfigs"),

    // Escape hatch: arbitrary xcall, e.g. {action:"xcall", name:"foo", args:[...]}
    xcall      : (req) => {
        const args = [req.name].concat(req.args || []);
        return win.xcall.apply(win, args);
    },
};

function dispatch(req) {
    const fn = handlers[req.action];
    if (!fn) return { ok:false, error:"unknown action: " + req.action };
    try {
        const r = fn(req);
        return { ok:true, result: r === undefined ? null : r };
    } catch (e) {
        return { ok:false, error: String(e && e.message || e) };
    }
}

let tickN = 0;
function tick() {
    tickN++;
    if ((tickN % HEARTBEAT_EVERY) === 0) {
        writeText(READY_PATH, String(Date.now()));
    }
    const text = readText(CMD_PATH);
    if (!text) return;
    let req;
    try { req = JSON.parse(text); }
    catch (e) {
        writeText(RESULT_PATH, JSON.stringify({ ok:false, error:"bad json: "+e }));
        unlink(CMD_PATH);
        return;
    }
    const resp = dispatch(req);
    if (req.id !== undefined) resp.id = req.id;
    writeText(RESULT_PATH, JSON.stringify(resp));
    unlink(CMD_PATH);
}

function start() {
    ensureDir(IPC_DIR);
    unlink(CMD_PATH);
    writeText(READY_PATH, String(Date.now()));
    setInterval(tick, POLL_MS);
    console.log("[ajiasu-bridge] online @ " + CMD_PATH + " every " + POLL_MS + "ms");
}

start();
