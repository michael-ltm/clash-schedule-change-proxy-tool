"""
GUI 界面模块
使用 customtkinter 创建现代化 Material 风格界面
"""

import customtkinter as ctk
import threading
import logging
from datetime import datetime
from typing import Optional

from clash_api import ClashAPI
from proxy_checker import ProxyChecker
from config import Config
from scheduler import ProxySwitcher
from clash_detector import auto_detect_and_connect
from i18n import t, init_language, set_language, get_language, SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

# 设置主题
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class IntervalProxyGUI:
    """代理切换工具主界面 - Material 风格"""
    
    def __init__(self):
        """初始化界面"""
        # 初始化配置
        self.config = Config()
        
        # 初始化语言
        init_language(self.config.get("language"))
        
        # 自动检测 Clash 设置
        self._auto_detect_clash()
        
        # 初始化组件
        self.clash_api = ClashAPI(
            host=self.config.get("clash_host"),
            port=self.config.get("clash_port"),
            secret=self.config.get("clash_secret")
        )
        self.proxy_checker = ProxyChecker(self.clash_api)
        self.switcher = ProxySwitcher(self.clash_api, self.proxy_checker, self.config)
        
        # 创建主窗口
        self.root = ctk.CTk()
        self.root.title(t("app_title"))
        self.root.geometry("480x720")
        self.root.minsize(420, 580)
        
        # 连接设置是否展开
        self._settings_expanded = False
        
        # 同步定时器 ID
        self._sync_timer_id = None
        self._last_proxy = None
        
        # 创建界面
        self._create_widgets()
        
        # 设置回调
        self.switcher.set_log_callback(self._append_log)
        self.switcher.set_status_callback(self._update_status)
        self.switcher.scheduler.set_on_tick(self._on_tick)
        
        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # 初始化连接
        self._init_connection()
    
    def _auto_detect_clash(self):
        """自动检测 Clash 设置"""
        saved_host = self.config.get("clash_host", "")
        saved_port = self.config.get("clash_port", 0)
        
        host, port, secret, connected = auto_detect_and_connect()
        
        if connected or not saved_host or not saved_port:
            self.config.set("clash_host", host)
            self.config.set("clash_port", port)
            if secret:
                self.config.set("clash_secret", secret)
            self.config.save()
    
    def _create_widgets(self):
        """创建界面组件"""
        # ===== 头部状态栏 =====
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))
        
        ctk.CTkLabel(
            header, 
            text=t("app_title"),
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(side="left")
        
        # 语言切换
        self.lang_btn = ctk.CTkButton(
            header,
            text="EN" if get_language() == "zh_CN" else "中",
            width=28,
            height=28,
            corner_radius=14,
            fg_color="#333333",
            hover_color="#444444",
            command=self._toggle_language
        )
        self.lang_btn.pack(side="right", padx=(4, 0))
        
        # 状态
        self.status_indicator = ctk.CTkLabel(
            header,
            text=t("status_detecting"),
            font=ctk.CTkFont(size=11),
            text_color="#888888"
        )
        self.status_indicator.pack(side="right", padx=(0, 6))
        
        self.settings_btn = ctk.CTkButton(
            header,
            text="⚙",
            width=28,
            height=28,
            corner_radius=14,
            fg_color="transparent",
            hover_color="#333333",
            command=self._toggle_settings
        )
        self.settings_btn.pack(side="right")
        
        # ===== 连接设置（默认隐藏）=====
        self.settings_frame = ctk.CTkFrame(self.root, corner_radius=10)
        
        settings_inner = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        settings_inner.pack(fill="x", padx=14, pady=14)
        
        # 地址端口行
        row1 = ctk.CTkFrame(settings_inner, fg_color="transparent")
        row1.pack(fill="x", pady=3)
        
        ctk.CTkLabel(row1, text=t("host"), width=45, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
        self.host_entry = ctk.CTkEntry(row1, width=110, height=28)
        self.host_entry.pack(side="left", padx=(0, 12))
        
        ctk.CTkLabel(row1, text=t("port"), width=35, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
        self.port_entry = ctk.CTkEntry(row1, width=65, height=28)
        self.port_entry.pack(side="left")
        
        # 密钥行
        row2 = ctk.CTkFrame(settings_inner, fg_color="transparent")
        row2.pack(fill="x", pady=3)
        
        ctk.CTkLabel(row2, text=t("secret"), width=45, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
        self.secret_entry = ctk.CTkEntry(row2, width=140, height=28, show="•", placeholder_text=t("secret_placeholder"))
        self.secret_entry.pack(side="left", padx=(0, 12))
        
        self.connect_btn = ctk.CTkButton(row2, text=t("reconnect"), width=80, height=28, command=self._reconnect)
        self.connect_btn.pack(side="right")
        
        # 填充设置值
        self.host_entry.insert(0, self.config.get("clash_host", "127.0.0.1"))
        self.port_entry.insert(0, str(self.config.get("clash_port", 9097)))
        self.secret_entry.insert(0, self.config.get("clash_secret", ""))
        
        # ===== 主设置区 =====
        main_card = ctk.CTkFrame(self.root, corner_radius=10)
        main_card.pack(fill="x", padx=20, pady=8)
        
        main_inner = ctk.CTkFrame(main_card, fg_color="transparent")
        main_inner.pack(fill="x", padx=16, pady=14)
        
        # 代理组选择
        group_row = ctk.CTkFrame(main_inner, fg_color="transparent")
        group_row.pack(fill="x", pady=4)
        
        ctk.CTkLabel(group_row, text=t("proxy_group"), font=ctk.CTkFont(size=13)).pack(side="left")
        
        self.refresh_btn = ctk.CTkButton(
            group_row, text="↻", width=28, height=28,
            corner_radius=14, fg_color="#333333",
            command=self._refresh_groups
        )
        self.refresh_btn.pack(side="right")
        
        self.group_combo = ctk.CTkComboBox(
            group_row, values=[], width=180, height=28,
            command=self._on_group_selected
        )
        self.group_combo.pack(side="right", padx=6)
        self.group_combo.set(t("loading"))
        
        # 当前代理显示
        current_row = ctk.CTkFrame(main_inner, fg_color="transparent")
        current_row.pack(fill="x", pady=4)
        
        ctk.CTkLabel(current_row, text=t("current_node"), font=ctk.CTkFont(size=13)).pack(side="left")
        self.current_proxy_label = ctk.CTkLabel(
            current_row, text="-",
            font=ctk.CTkFont(size=13),
            text_color="#3B8ED0"
        )
        self.current_proxy_label.pack(side="right")
        
        # 分隔线
        ctk.CTkFrame(main_inner, height=1, fg_color="#333333").pack(fill="x", pady=10)
        
        # 切换间隔
        interval_row = ctk.CTkFrame(main_inner, fg_color="transparent")
        interval_row.pack(fill="x", pady=4)
        
        ctk.CTkLabel(interval_row, text=t("interval"), font=ctk.CTkFont(size=13)).pack(side="left")
        
        interval_input = ctk.CTkFrame(interval_row, fg_color="transparent")
        interval_input.pack(side="right")
        
        self.interval_entry = ctk.CTkEntry(interval_input, width=55, height=28, justify="center")
        self.interval_entry.pack(side="left")
        self.interval_entry.insert(0, str(self.config.get("interval_minutes", 30)))
        
        ctk.CTkLabel(interval_input, text=t("minutes"), font=ctk.CTkFont(size=13)).pack(side="left", padx=(6, 0))
        
        # 检测开关
        check_row = ctk.CTkFrame(main_inner, fg_color="transparent")
        check_row.pack(fill="x", pady=4)
        
        ctk.CTkLabel(check_row, text=t("check_before_switch"), font=ctk.CTkFont(size=13)).pack(side="left")
        
        self.check_var = ctk.BooleanVar(value=self.config.get("check_before_switch", True))
        self.check_switch = ctk.CTkSwitch(check_row, text="", variable=self.check_var, width=40)
        self.check_switch.pack(side="right")
        
        # ===== 控制区域 =====
        control_card = ctk.CTkFrame(self.root, corner_radius=10)
        control_card.pack(fill="x", padx=20, pady=8)
        
        control_inner = ctk.CTkFrame(control_card, fg_color="transparent")
        control_inner.pack(fill="x", padx=16, pady=14)
        
        # 倒计时
        self.countdown_label = ctk.CTkLabel(
            control_inner,
            text="--:--",
            font=ctk.CTkFont(size=42, weight="bold"),
            text_color="#555555"
        )
        self.countdown_label.pack(pady=(0, 12))
        
        # 主按钮
        self.start_btn = ctk.CTkButton(
            control_inner,
            text=t("start_auto"),
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            corner_radius=10,
            command=self._toggle_auto_switch
        )
        self.start_btn.pack(fill="x", pady=3)
        
        # 次要按钮组
        btn_row = ctk.CTkFrame(control_inner, fg_color="transparent")
        btn_row.pack(fill="x", pady=3)
        btn_row.grid_columnconfigure((0, 1), weight=1)
        
        self.switch_now_btn = ctk.CTkButton(
            btn_row,
            text=t("switch_now"),
            height=36,
            fg_color="#2B2B2B",
            hover_color="#383838",
            command=self._switch_now
        )
        self.switch_now_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        
        self.test_btn = ctk.CTkButton(
            btn_row,
            text=t("test_all"),
            height=36,
            fg_color="#2B2B2B",
            hover_color="#383838",
            command=self._test_all_proxies
        )
        self.test_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        
        # ===== 日志区域 =====
        log_frame = ctk.CTkFrame(self.root, corner_radius=10)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(8, 16))
        
        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=12, pady=(10, 4))
        
        ctk.CTkLabel(log_header, text=t("log"), font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkButton(
            log_header, text=t("clear"), width=40, height=20,
            fg_color="transparent", hover_color="#333333",
            font=ctk.CTkFont(size=10),
            command=self._clear_log
        ).pack(side="right")
        
        self.log_text = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Menlo", size=11),
            corner_radius=6
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(4, 10))
    
    def _toggle_language(self):
        """切换语言"""
        current = get_language()
        new_lang = "en_US" if current == "zh_CN" else "zh_CN"
        set_language(new_lang)
        self.config.set("language", new_lang)
        self.config.save()
        
        # 提示需要重启
        self._append_log("Language changed. Please restart the app. / 语言已更改，请重启应用。")
        self.lang_btn.configure(text="EN" if new_lang == "zh_CN" else "中")
    
    def _toggle_settings(self):
        """切换设置面板显示"""
        if self._settings_expanded:
            self.settings_frame.pack_forget()
            self._settings_expanded = False
        else:
            self.settings_frame.pack(fill="x", padx=20, pady=(0, 8), after=self.root.winfo_children()[0])
            self._settings_expanded = True
    
    def _init_connection(self):
        """初始化连接"""
        def do_connect():
            if self.clash_api.test_connection():
                version = self.clash_api.get_version()
                v = version.get("version", "?") if version else "?"
                self.root.after(0, lambda: self.status_indicator.configure(
                    text=f"{t('status_connected')} v{v}", text_color="#4CAF50"
                ))
                self.root.after(0, self._refresh_groups)
                self.root.after(0, lambda: self._append_log(t("auto_connected")))
                self.root.after(0, self._start_sync)
            else:
                self.root.after(0, lambda: self.status_indicator.configure(
                    text=t("status_disconnected"), text_color="#F44336"
                ))
                self.root.after(0, lambda: self._append_log(t("connect_failed_tip")))
                self.root.after(0, lambda: self.group_combo.set(t("please_connect")))
                self.root.after(0, self._stop_sync)
        
        threading.Thread(target=do_connect, daemon=True).start()
    
    def _start_sync(self):
        """启动与 Clash 的状态同步"""
        self._stop_sync()
        self._sync_with_clash()
    
    def _stop_sync(self):
        """停止同步"""
        if self._sync_timer_id:
            self.root.after_cancel(self._sync_timer_id)
            self._sync_timer_id = None
    
    def _sync_with_clash(self):
        """与 Clash 同步当前状态"""
        def do_sync():
            try:
                group = self.group_combo.get()
                if group in [t("loading"), t("please_connect"), t("no_proxy_group")]:
                    return
                
                current = self.clash_api.get_current_proxy(group)
                if current and current != self._last_proxy:
                    self._last_proxy = current
                    self.root.after(0, lambda: self.current_proxy_label.configure(text=current))
                
                groups = self.clash_api.get_proxy_groups()
                if groups:
                    names = [g["name"] for g in groups]
                    current_values = list(self.group_combo.cget("values") or [])
                    if names != current_values:
                        self.root.after(0, lambda: self.group_combo.configure(values=names))
                        
            except Exception as e:
                logger.debug(f"Sync failed: {e}")
        
        threading.Thread(target=do_sync, daemon=True).start()
        self._sync_timer_id = self.root.after(2000, self._sync_with_clash)
    
    def _reconnect(self):
        """重新连接"""
        host = self.host_entry.get() or "127.0.0.1"
        try:
            port = int(self.port_entry.get() or 9097)
        except ValueError:
            self._append_log(t("port_must_be_number"))
            return
        secret = self.secret_entry.get()
        
        self.config.set("clash_host", host)
        self.config.set("clash_port", port)
        self.config.set("clash_secret", secret)
        self.config.save()
        
        self.clash_api.update_config(host, port, secret)
        self._append_log(f"{t('trying_connect')} {host}:{port}...")
        self._init_connection()
    
    def _refresh_groups(self):
        """刷新代理组"""
        groups = self.clash_api.get_proxy_groups()
        names = [g["name"] for g in groups]
        
        if not names:
            self.group_combo.configure(values=[])
            self.group_combo.set(t("no_proxy_group"))
            return
        
        self.group_combo.configure(values=names)
        
        saved = self.config.get("selected_group")
        if saved and saved in names:
            self.group_combo.set(saved)
        else:
            self.group_combo.set(names[0])
        
        self._on_group_selected(None)
    
    def _on_group_selected(self, _):
        """代理组选择变更"""
        group = self.group_combo.get()
        if group and group not in [t("loading"), t("please_connect"), t("no_proxy_group")]:
            current = self.clash_api.get_current_proxy(group)
            self.current_proxy_label.configure(text=current or "-")
            self._last_proxy = current
            self.config.set("selected_group", group)
            self.config.save()
    
    def _toggle_auto_switch(self):
        """切换自动切换"""
        if self.switcher.is_running():
            self.switcher.stop_auto_switch()
            self.start_btn.configure(text=t("start_auto"), fg_color="#3B8ED0")
            self.countdown_label.configure(text="--:--", text_color="#555555")
        else:
            group = self.group_combo.get()
            if group in [t("loading"), t("please_connect"), t("no_proxy_group")]:
                self._append_log(t("please_select_group"))
                return
            
            try:
                interval = int(self.interval_entry.get() or 30)
            except ValueError:
                self._append_log(t("interval_must_be_number"))
                return
            
            self.config.set("interval_minutes", interval)
            self.config.set("check_before_switch", self.check_var.get())
            self.config.save()
            
            self.switcher.start_auto_switch()
            self.start_btn.configure(text=t("stop"), fg_color="#E53935")
            self.countdown_label.configure(text_color="#3B8ED0")
    
    def _switch_now(self):
        """立即切换"""
        group = self.group_combo.get()
        if group in [t("loading"), t("please_connect"), t("no_proxy_group")]:
            self._append_log(t("please_select_group"))
            return
        
        self.config.set("check_before_switch", self.check_var.get())
        
        def do_switch():
            self.switcher.switch_proxy(group)
            self.root.after(100, self._on_group_selected, None)
        
        threading.Thread(target=do_switch, daemon=True).start()
    
    def _test_all_proxies(self):
        """测试所有代理"""
        group = self.group_combo.get()
        if group in [t("loading"), t("please_connect"), t("no_proxy_group")]:
            self._append_log(t("please_select_group"))
            return
        
        proxies = self.clash_api.get_group_proxies(group)
        if not proxies:
            return
        
        self._append_log(t("testing_proxies", count=len(proxies)))
        self.test_btn.configure(state="disabled")
        
        def do_test():
            results = self.proxy_checker.get_all_proxy_delays(proxies)
            ok = sum(1 for r in results.values() if r[0])
            
            for name, (available, delay, msg) in results.items():
                icon = "✓" if available else "✗"
                self._append_log(f"  {icon} {name}: {msg}")
            
            self._append_log(t("test_complete", ok=ok, total=len(proxies)))
            self.root.after(0, lambda: self.test_btn.configure(state="normal"))
        
        threading.Thread(target=do_test, daemon=True).start()
    
    def _on_tick(self, seconds: int):
        """定时器回调"""
        m, s = divmod(seconds, 60)
        text = f"{m:02d}:{s:02d}"
        self.root.after(0, lambda: self.countdown_label.configure(text=text))
    
    def _update_status(self, status: str):
        """更新状态"""
        pass
    
    def _append_log(self, message: str):
        """添加日志"""
        def do_append():
            time_str = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{time_str}] {message}\n")
            self.log_text.see("end")
        
        if threading.current_thread() is threading.main_thread():
            do_append()
        else:
            self.root.after(0, do_append)
    
    def _clear_log(self):
        """清空日志"""
        self.log_text.delete("1.0", "end")
    
    def _on_closing(self):
        """关闭窗口"""
        self._stop_sync()
        if self.switcher.is_running():
            self.switcher.stop_auto_switch()
        self.config.save()
        self.root.destroy()
    
    def run(self):
        """运行"""
        self._append_log(t("detecting_clash"))
        self.root.mainloop()


def main():
    app = IntervalProxyGUI()
    app.run()


if __name__ == "__main__":
    main()
