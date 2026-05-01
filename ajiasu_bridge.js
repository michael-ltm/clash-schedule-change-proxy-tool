// AJIASU-BRIDGE v14 — hybrid: fast fetch chain + timer watchdog

(function() {
    var BRIDGE_VERSION = 14;
    var BASE = "http://127.0.0.1:62517";
    var win = Window.this;
    var _pendingResult = null;
    var _loopActive = false;
    var _lastFetchStart = 0;

    function xc() {
        try { return win.xcall.apply(win, arguments); }
        catch(e) { throw e; }
    }

    function disc() {
        try {
            if (xc("isServerPicking")) xc("cancelPickServerFromWeb");
            var s = xc("getVpnStats");
            if (s && s.state != 0) xc("vpnDisconnect");
        } catch(e) {}
    }

    var H = {
        ping:        function()  { return "pong"; },
        bridgeInfo:  function()  { return {version:BRIDGE_VERSION,ts:Date.now()}; },
        version:     function()  { return xc("getClientVersion"); },
        accountName: function()  { return xc("getAccountName"); },
        list:        function()  { return xc("getOrderedAllServers"); },
        fullList:    function()  { return xc("getFullLoadServers"); },
        favorites:   function()  { return xc("getFavoriteServersFromLocal"); },
        recent:      function()  { return xc("getRecentlyUsedServers"); },
        status:      function()  { return xc("getVpnStats"); },
        pingReports: function()  { return xc("getPingReports"); },
        isPicking:   function()  { return xc("isServerPicking"); },
        connect:     function(r) { if(!r.srvId) throw "srvId required"; disc(); return xc("vpnConnect",String(r.srvId)); },
        disconnect:  function()  { return xc("vpnDisconnect"); },
        cancelPick:  function()  { return xc("cancelPickServerFromWeb"); },
        pick:        function(r) { disc(); return xc("pickServerFromWeb",r.level||"",r.code||"",r.servers||[]); },
        pingServers: function(r) { return xc("pingMultiServer",{serverIdList:r.ids||[]}); },
        getConfig:   function(r) { return xc("getUserConfig",r.key,r.def||""); },
        setConfig:   function(r) { return xc("setUserConfig",r.key,String(r.value)); },
        getConfigs:  function()  { return xc("getUserConfigs"); },
        xcall:       function(r) { return win.xcall.apply(win,[r.name].concat(r.args||[])); }
    };

    function dispatch(req) {
        var fn = H[req.action];
        if (!fn) return {ok:false,error:"unknown action: "+req.action};
        try {
            var r = fn(req);
            return {ok:true,result:r===undefined?null:r};
        } catch(e) {
            return {ok:false,error:String((e&&e.message)||e)};
        }
    }

    function safeStringify(obj) {
        try { return JSON.stringify(obj); }
        catch(e) { return JSON.stringify({ok:false,error:"stringify: "+e}); }
    }

    function doFetch() {
        _lastFetchStart = Date.now();
        _loopActive = true;
        var opts = {};
        if (_pendingResult) {
            opts.method = "POST";
            opts.headers = {"Content-Type": "application/json"};
            opts.body = safeStringify(_pendingResult);
            _pendingResult = null;
        }
        fetch(BASE + "/bridge/poll?hb=1", opts)
            .then(function(r) { return r.text(); })
            .then(function(body) {
                if (body && body !== "none") {
                    var req;
                    try { req = JSON.parse(body); } catch(e) {
                        doFetch();
                        return;
                    }
                    var result = dispatch(req);
                    if (req.id !== undefined) result.id = req.id;
                    _pendingResult = result;
                }
                doFetch();
            })
            ["catch"](function() {
                _loopActive = false;
            });
    }

    // Watchdog: check every 5s if loop is dead and restart it
    // Key: the timer ONLY restarts the loop, never chains fetches itself.
    // This prevents unbounded promise chain growth during disconnection.
    var _watchdogCount = 0;
    document.timer(5000, function() {
        _watchdogCount++;
        if (!_loopActive || (Date.now() - _lastFetchStart > 15000)) {
            _loopActive = false;
            _pendingResult = null;
            doFetch();
        }
        return true;
    });

    doFetch();
})();
