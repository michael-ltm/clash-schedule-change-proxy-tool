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
        "app_title": "定时更改Clash代理",
        
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
        "app_title": "Clash Proxy Timer",
        
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
