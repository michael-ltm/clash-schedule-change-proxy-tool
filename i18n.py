"""
国际化模块 / Internationalization Module
支持简体中文和英文 / Supports Simplified Chinese and English
"""

import locale
import sys

# 语言包
TRANSLATIONS = {
    "zh_CN": {
        # 窗口
        "app_title": "定时切换代理",

        # 模式
        "mode_label": "模式",
        "mode_clash": "Clash",
        "mode_ajiasu": "爱加速",
        "mode_switched": "已切换到模式: {mode}",

        # AJiaSu
        "ajiasu_path": "安装目录",
        "ajiasu_detect": "自动",
        "ajiasu_patch": "安装桥接",
        "ajiasu_unpatch": "卸载桥接",
        "ajiasu_bridge_unknown": "桥接状态: 未知",
        "ajiasu_bridge_patched": "● 桥接已安装",
        "ajiasu_bridge_not_patched": "● 桥接未安装",
        "ajiasu_bridge_online": "● 爱加速桥已在线",
        "ajiasu_bridge_offline": "● 爱加速桥未响应",
        "ajiasu_bridge_offline_tip": "未收到爱加速桥的响应,请确认: 1) 桥接已安装  2) AJiaSu.exe 已启动并打开主窗口",
        "ajiasu_path_invalid": "安装目录无效(需包含 AJiaSu.exe 和 res.fvr)",
        "ajiasu_detected": "已检测到安装目录: {path}",
        "ajiasu_not_detected": "未自动检测到 AJiaSu 安装目录,请手动选择",
        "ajiasu_running_warn": "请先关闭 AJiaSu.exe 再操作补丁",
        "ajiasu_patch_done_tip": "补丁已就绪,请启动 AJiaSu.exe",
        "ajiasu_starting": "正在初始化爱加速模式...",
        "ajiasu_banner_unpatched": "⚠ 桥接未安装 — 点这里安装",
        "ajiasu_banner_no_path": "⚠ 未配置爱加速安装目录 — 点 ⚙ 设置",
        "ajiasu_need_admin_title": "需要管理员权限",
        "ajiasu_need_admin_msg": "{path} 没有写入权限(通常是因为爱加速装在 Program Files)。\n\n是否以管理员身份重启本程序?重启后请再次点击\"安装桥接\"。",
        "ajiasu_relaunch_failed": "提权重启失败,请右键以管理员身份重新启动本程序",
        "ajiasu_no_write_perm": "没有写入权限",

        # 状态
        "status_detecting": "● 检测中...",
        "status_connected": "● 已连接",
        "status_disconnected": "● 未连接",
        "status_connect_failed": "● 连接失败",
        
        # 连接设置
        "host": "地址",
        "port": "端口",
        "secret": "密钥",
        "secret_placeholder": "可选",
        "reconnect": "重新连接",
        
        # 主设置
        "proxy_group": "代理组",
        "current_node": "当前节点",
        "interval": "切换间隔",
        "minutes": "分钟",
        "check_before_switch": "切换前检测可用性",
        
        # 按钮
        "start_auto": "▶  开始自动切换",
        "stop": "⏹  停止",
        "switch_now": "立即切换",
        "test_all": "测速全部",
        
        # 日志
        "log": "日志",
        "clear": "清空",
        
        # 消息
        "loading": "加载中...",
        "please_connect": "请先连接",
        "no_proxy_group": "无代理组",
        "auto_connected": "自动连接成功",
        "connect_failed_tip": "连接失败，点击 ⚙ 检查设置",
        "detecting_clash": "正在检测 Clash 设置...",
        "please_select_group": "请先选择代理组",
        "interval_must_be_number": "间隔必须是数字",
        "port_must_be_number": "端口必须是数字",
        "trying_connect": "尝试连接",
        "testing_proxies": "测试 {count} 个代理...",
        "test_complete": "完成: {ok}/{total} 可用",
        
        # 语言
        "language": "语言",
        "lang_zh": "简体中文",
        "lang_en": "English",
    },
    
    "en_US": {
        # Window
        "app_title": "Proxy Timer",

        # Mode
        "mode_label": "Mode",
        "mode_clash": "Clash",
        "mode_ajiasu": "AJiaSu",
        "mode_switched": "Switched to mode: {mode}",

        # AJiaSu
        "ajiasu_path": "Install Dir",
        "ajiasu_detect": "Auto",
        "ajiasu_patch": "Install Bridge",
        "ajiasu_unpatch": "Uninstall Bridge",
        "ajiasu_bridge_unknown": "Bridge status: unknown",
        "ajiasu_bridge_patched": "● Bridge installed",
        "ajiasu_bridge_not_patched": "● Bridge not installed",
        "ajiasu_bridge_online": "● AJiaSu bridge online",
        "ajiasu_bridge_offline": "● AJiaSu bridge offline",
        "ajiasu_bridge_offline_tip": "No response from the AJiaSu bridge. Make sure: 1) bridge is installed; 2) AJiaSu.exe is running with main window open.",
        "ajiasu_path_invalid": "Invalid install dir (needs AJiaSu.exe and res.fvr)",
        "ajiasu_detected": "Detected install dir: {path}",
        "ajiasu_not_detected": "AJiaSu install dir not auto-detected. Please pick manually.",
        "ajiasu_running_warn": "Close AJiaSu.exe before patching",
        "ajiasu_patch_done_tip": "Patch ready. Start AJiaSu.exe to use it.",
        "ajiasu_starting": "Starting AJiaSu mode...",
        "ajiasu_banner_unpatched": "⚠ Bridge not installed — click here to install",
        "ajiasu_banner_no_path": "⚠ AJiaSu install dir not set — click ⚙ to configure",
        "ajiasu_need_admin_title": "Administrator permission required",
        "ajiasu_need_admin_msg": "{path} is not writable (usually because AJiaSu is installed under Program Files).\n\nRelaunch this app as administrator? After relaunch, click \"Install Bridge\" again.",
        "ajiasu_relaunch_failed": "Failed to relaunch as admin. Please right-click and run as administrator.",
        "ajiasu_no_write_perm": "No write permission",

        # Status
        "status_detecting": "● Detecting...",
        "status_connected": "● Connected",
        "status_disconnected": "● Disconnected",
        "status_connect_failed": "● Connect Failed",
        
        # Connection settings
        "host": "Host",
        "port": "Port",
        "secret": "Secret",
        "secret_placeholder": "Optional",
        "reconnect": "Reconnect",
        
        # Main settings
        "proxy_group": "Proxy Group",
        "current_node": "Current Node",
        "interval": "Interval",
        "minutes": "min",
        "check_before_switch": "Check availability before switch",
        
        # Buttons
        "start_auto": "▶  Start Auto Switch",
        "stop": "⏹  Stop",
        "switch_now": "Switch Now",
        "test_all": "Test All",
        
        # Log
        "log": "Log",
        "clear": "Clear",
        
        # Messages
        "loading": "Loading...",
        "please_connect": "Please connect first",
        "no_proxy_group": "No proxy group",
        "auto_connected": "Auto connected",
        "connect_failed_tip": "Connection failed, click ⚙ to check settings",
        "detecting_clash": "Detecting Clash settings...",
        "please_select_group": "Please select a proxy group first",
        "interval_must_be_number": "Interval must be a number",
        "port_must_be_number": "Port must be a number",
        "trying_connect": "Trying to connect",
        "testing_proxies": "Testing {count} proxies...",
        "test_complete": "Done: {ok}/{total} available",
        
        # Language
        "language": "Language",
        "lang_zh": "简体中文",
        "lang_en": "English",
    }
}

# 支持的语言
SUPPORTED_LANGUAGES = ["zh_CN", "en_US"]

# 当前语言
_current_language = "zh_CN"


def detect_system_language() -> str:
    """
    检测系统语言
    
    Returns:
        语言代码 (zh_CN 或 en_US)
    """
    try:
        if sys.platform == "darwin":
            # macOS
            import subprocess
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleLanguages"],
                capture_output=True, text=True
            )
            if "zh" in result.stdout.lower():
                return "zh_CN"
        else:
            # Windows / Linux
            lang = locale.getdefaultlocale()[0] or ""
            if lang.startswith("zh"):
                return "zh_CN"
    except Exception:
        pass
    
    return "en_US"


def get_language() -> str:
    """获取当前语言"""
    return _current_language


def set_language(lang: str):
    """
    设置当前语言
    
    Args:
        lang: 语言代码 (zh_CN 或 en_US)
    """
    global _current_language
    if lang in SUPPORTED_LANGUAGES:
        _current_language = lang


def t(key: str, **kwargs) -> str:
    """
    获取翻译文本
    
    Args:
        key: 翻译键
        **kwargs: 格式化参数
        
    Returns:
        翻译后的文本
    """
    translations = TRANSLATIONS.get(_current_language, TRANSLATIONS["en_US"])
    text = translations.get(key, key)
    
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    
    return text


def init_language(saved_lang: str = None):
    """
    初始化语言设置
    
    Args:
        saved_lang: 保存的语言设置，None 则自动检测
    """
    global _current_language
    
    if saved_lang and saved_lang in SUPPORTED_LANGUAGES:
        _current_language = saved_lang
    else:
        _current_language = detect_system_language()
