"""
GUI 界面模块
使用 customtkinter 创建现代化 Material 风格界面

支持两种模式:
- clash : 通过 Clash Verge 的 RESTful API 切换代理组中的节点
- ajiasu: 通过文件 IPC 桥控制 AJiaSu (爱加速),切换其节点

两种模式共用同一套调度器/倒计时/日志面板。
"""

import customtkinter as ctk
import threading
import logging
import sys
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

from clash_api import ClashAPI
from proxy_checker import ProxyChecker
from config import Config
from scheduler import ProxySwitcher, AJiaSuProxySwitcher
from clash_detector import auto_detect_and_connect

import ajiasu_api
import ajiasu_detector
import ajiasu_patcher
import win_admin
from ajiasu_api import AJiaSuAPI
from i18n import t, init_language, set_language, get_language, SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

# 设置主题 - 渐变现代风格
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

MODE_CLASH = "clash"
MODE_AJIASU = "ajiasu"


class IntervalProxyGUI:
    """代理切换工具主界面 - Material 风格"""

    def __init__(self):
        # 初始化配置
        self.config = Config()
        # 初始化语言
        init_language(self.config.get("language"))

        self.mode = self.config.get("mode", MODE_CLASH)
        if self.mode not in (MODE_CLASH, MODE_AJIASU):
            self.mode = MODE_CLASH

        # 自动检测 Clash 设置(只在 clash 模式)
        if self.mode == MODE_CLASH:
            self._auto_detect_clash()
        else:
            self._auto_detect_ajiasu()

        # 创建两套 backend / switcher,按 mode 切换 alias
        self.clash_api = ClashAPI(
            host=self.config.get("clash_host"),
            port=self.config.get("clash_port"),
            secret=self.config.get("clash_secret"),
        )
        self.proxy_checker = ProxyChecker(self.clash_api)
        self.clash_switcher = ProxySwitcher(self.clash_api, self.proxy_checker, self.config)

        self.ajiasu_api = AJiaSuAPI(
            ipc_dir=self.config.get("ajiasu_ipc_dir") or None,
        )
        self.ajiasu_switcher = AJiaSuProxySwitcher(self.ajiasu_api, self.config)

        # 当前激活的 backend / switcher
        self.backend = self.clash_api if self.mode == MODE_CLASH else self.ajiasu_api
        self.switcher = self.clash_switcher if self.mode == MODE_CLASH else self.ajiasu_switcher

        # 创建主窗口
        self.root = ctk.CTk()
        self.root.title(t("app_title"))
        self.root.geometry("520x780")
        self.root.minsize(460, 620)

        # 设置面板是否展开
        self._settings_expanded = False
        # 同步定时器 ID
        self._sync_timer_id = None
        self._last_proxy = None

        # 创建界面
        self._create_widgets()

        # 设置回调
        for sw in (self.clash_switcher, self.ajiasu_switcher):
            sw.set_log_callback(self._append_log)
            sw.set_status_callback(self._update_status)
            sw.scheduler.set_on_tick(self._on_tick)

        # 绑定关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # AJiaSu 模式启动时刷新一次横幅(未打补丁会立刻提示)
        self._update_ajiasu_banner()

        # 初始化连接
        self._init_connection()

    # ====================== 自动探测 ======================

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

    def _auto_detect_ajiasu(self):
        """自动检测 AJiaSu 安装目录"""
        saved = self.config.get("ajiasu_install_path", "")
        if saved and Path(saved).exists() and ajiasu_detector.is_install_dir(Path(saved)):
            return
        d = ajiasu_detector.detect_install_dir()
        if d:
            self.config.set("ajiasu_install_path", str(d))
            self.config.save()

    # ====================== UI 构造 ======================

    def _create_widgets(self):
        # 头部
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 6))

        ctk.CTkLabel(
            header, text=t("app_title"),
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#6B46FF",
        ).pack(side="left")

        self.lang_btn = ctk.CTkButton(
            header,
            text="EN" if get_language() == "zh_CN" else "中",
            width=32, height=32, corner_radius=16,
            fg_color="#2D2D3D", hover_color="#3D3D4D",
            font=ctk.CTkFont(size=11, weight="bold"),
            border_width=2, border_color="#4D4D5D",
            command=self._toggle_language,
        )
        self.lang_btn.pack(side="right", padx=(4, 0))

        self.status_indicator = ctk.CTkLabel(
            header, text=t("status_detecting"),
            font=ctk.CTkFont(size=11), text_color="#999999",
        )
        self.status_indicator.pack(side="right", padx=(0, 8))

        self.settings_btn = ctk.CTkButton(
            header, text="⚙",
            width=32, height=32, corner_radius=16,
            fg_color="transparent", hover_color="#2D2D3D",
            font=ctk.CTkFont(size=16),
            border_width=2, border_color="#3D3D4D",
            command=self._toggle_settings,
        )
        self.settings_btn.pack(side="right")

        # 模式切换
        mode_row = ctk.CTkFrame(self.root, fg_color="transparent")
        mode_row.pack(fill="x", padx=24, pady=(2, 6))
        ctk.CTkLabel(
            mode_row, text=t("mode_label"),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#8B8B9B",
        ).pack(side="left", padx=(2, 8))

        self.mode_seg = ctk.CTkSegmentedButton(
            mode_row,
            values=[t("mode_clash"), t("mode_ajiasu")],
            command=self._on_mode_changed,
            corner_radius=8,
            selected_color="#6B46FF",
            selected_hover_color="#7B56FF",
            unselected_color="#2D2D3D",
            unselected_hover_color="#3D3D4D",
        )
        self.mode_seg.pack(side="left", fill="x", expand=True)
        self.mode_seg.set(t("mode_clash") if self.mode == MODE_CLASH else t("mode_ajiasu"))

        # 设置卡片(可隐藏);内部按 mode 切换
        self.settings_frame = ctk.CTkFrame(
            self.root, corner_radius=16, fg_color="#1E1E2E",
            border_width=2, border_color="#2D2D3D",
        )
        self._build_clash_settings()
        self._build_ajiasu_settings()
        self._show_settings_for_mode()

        # 主设置卡片
        self.main_card = ctk.CTkFrame(
            self.root, corner_radius=16, fg_color="#1E1E2E",
            border_width=2, border_color="#2D2D3D",
        )
        self.main_card.pack(fill="x", padx=24, pady=10)
        main_inner = ctk.CTkFrame(self.main_card, fg_color="transparent")
        main_inner.pack(fill="x", padx=20, pady=18)

        # AJiaSu 状态横幅(未打补丁/未配置路径时显示);默认不 pack
        self.ajiasu_banner = ctk.CTkButton(
            main_inner,
            text=t("ajiasu_banner_unpatched"),
            height=36, corner_radius=8,
            fg_color="#5C3A12", hover_color="#7A4D18",
            border_width=1, border_color="#FFB454",
            text_color="#FFB454",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="center",
            command=self._on_ajiasu_banner_click,
        )

        group_row = ctk.CTkFrame(main_inner, fg_color="transparent")
        # 记下 group_row 给横幅做 pack 锚点
        self._main_inner_first_row = group_row
        group_row.pack(fill="x", pady=6)
        ctk.CTkLabel(
            group_row, text=t("proxy_group"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#CCCCDD",
        ).pack(side="left")

        self.refresh_btn = ctk.CTkButton(
            group_row, text="↻", width=32, height=32, corner_radius=16,
            fg_color="#2D2D3D", hover_color="#3D3D4D",
            font=ctk.CTkFont(size=16),
            border_width=2, border_color="#4D4D5D",
            command=self._refresh_groups,
        )
        self.refresh_btn.pack(side="right")

        self.group_combo = ctk.CTkComboBox(
            group_row, values=[], width=210, height=32, corner_radius=8,
            border_width=2, border_color="#3D3D4D",
            button_color="#6B46FF", button_hover_color="#7B56FF",
            command=self._on_group_selected,
        )
        self.group_combo.pack(side="right", padx=8)
        self.group_combo.set(t("loading"))

        current_row = ctk.CTkFrame(main_inner, fg_color="transparent")
        current_row.pack(fill="x", pady=6)
        ctk.CTkLabel(
            current_row, text=t("current_node"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#CCCCDD",
        ).pack(side="left")
        self.current_proxy_label = ctk.CTkLabel(
            current_row, text="-",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#6B46FF",
        )
        self.current_proxy_label.pack(side="right")

        ctk.CTkFrame(main_inner, height=2, fg_color="#2D2D3D").pack(fill="x", pady=12)

        interval_row = ctk.CTkFrame(main_inner, fg_color="transparent")
        interval_row.pack(fill="x", pady=6)
        ctk.CTkLabel(
            interval_row, text=t("interval"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#CCCCDD",
        ).pack(side="left")
        interval_input = ctk.CTkFrame(interval_row, fg_color="transparent")
        interval_input.pack(side="right")
        self.interval_entry = ctk.CTkEntry(
            interval_input, width=60, height=32, justify="center",
            corner_radius=8, border_width=2, border_color="#3D3D4D",
        )
        self.interval_entry.pack(side="left")
        self.interval_entry.insert(0, str(self.config.get("interval_seconds", 60)))
        ctk.CTkLabel(
            interval_input, text=t("minutes"),
            font=ctk.CTkFont(size=13), text_color="#8B8B9B",
        ).pack(side="left", padx=(8, 0))

        check_row = ctk.CTkFrame(main_inner, fg_color="transparent")
        check_row.pack(fill="x", pady=6)
        ctk.CTkLabel(
            check_row, text=t("check_before_switch"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#CCCCDD",
        ).pack(side="left")
        self.check_var = ctk.BooleanVar(value=self.config.get("check_before_switch", True))
        self.check_switch = ctk.CTkSwitch(
            check_row, text="", variable=self.check_var, width=44,
            progress_color="#6B46FF", button_color="#FFFFFF",
            button_hover_color="#EEEEEE",
        )
        self.check_switch.pack(side="right")

        # 控制区
        control_card = ctk.CTkFrame(
            self.root, corner_radius=16, fg_color="#1E1E2E",
            border_width=2, border_color="#2D2D3D",
        )
        control_card.pack(fill="x", padx=24, pady=10)
        control_inner = ctk.CTkFrame(control_card, fg_color="transparent")
        control_inner.pack(fill="x", padx=20, pady=18)

        self.countdown_label = ctk.CTkLabel(
            control_inner, text="--:--",
            font=ctk.CTkFont(size=48, weight="bold"),
            text_color="#4D4D5D",
        )
        self.countdown_label.pack(pady=(0, 16))

        self.start_btn = ctk.CTkButton(
            control_inner, text=t("start_auto"),
            font=ctk.CTkFont(size=15, weight="bold"),
            height=48, corner_radius=12,
            fg_color="#6B46FF", hover_color="#7B56FF",
            border_width=0, command=self._toggle_auto_switch,
        )
        self.start_btn.pack(fill="x", pady=4)

        btn_row = ctk.CTkFrame(control_inner, fg_color="transparent")
        btn_row.pack(fill="x", pady=4)
        btn_row.grid_columnconfigure((0, 1), weight=1)

        self.switch_now_btn = ctk.CTkButton(
            btn_row, text=t("switch_now"),
            height=40, corner_radius=10,
            fg_color="#2D2D3D", hover_color="#3D3D4D",
            border_width=2, border_color="#4D4D5D",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._switch_now,
        )
        self.switch_now_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.test_btn = ctk.CTkButton(
            btn_row, text=t("test_all"),
            height=40, corner_radius=10,
            fg_color="#2D2D3D", hover_color="#3D3D4D",
            border_width=2, border_color="#4D4D5D",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._test_all_proxies,
        )
        self.test_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        # 日志区
        log_frame = ctk.CTkFrame(
            self.root, corner_radius=16, fg_color="#1E1E2E",
            border_width=2, border_color="#2D2D3D",
        )
        log_frame.pack(fill="both", expand=True, padx=24, pady=(10, 20))
        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(
            log_header, text=t("log"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#CCCCDD",
        ).pack(side="left")
        ctk.CTkButton(
            log_header, text=t("clear"), width=50, height=24, corner_radius=6,
            fg_color="transparent", hover_color="#2D2D3D",
            border_width=1, border_color="#3D3D4D",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#8B8B9B", command=self._clear_log,
        ).pack(side="right")
        self.log_text = ctk.CTkTextbox(
            log_frame, font=ctk.CTkFont(family="Menlo", size=11),
            corner_radius=10, fg_color="#0D0D1D",
            border_width=1, border_color="#2D2D3D",
        )
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(6, 12))

    def _build_clash_settings(self):
        """Clash 设置面板"""
        self.clash_settings = ctk.CTkFrame(self.settings_frame, fg_color="transparent")

        row1 = ctk.CTkFrame(self.clash_settings, fg_color="transparent")
        row1.pack(fill="x", pady=4, padx=18)
        ctk.CTkLabel(
            row1, text=t("host"), width=50, anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#8B8B9B",
        ).pack(side="left")
        self.host_entry = ctk.CTkEntry(
            row1, width=110, height=32, corner_radius=8,
            border_width=2, border_color="#3D3D4D",
        )
        self.host_entry.pack(side="left", padx=(0, 12))
        ctk.CTkLabel(
            row1, text=t("port"), width=40, anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#8B8B9B",
        ).pack(side="left")
        self.port_entry = ctk.CTkEntry(
            row1, width=70, height=32, corner_radius=8,
            border_width=2, border_color="#3D3D4D",
        )
        self.port_entry.pack(side="left")

        row2 = ctk.CTkFrame(self.clash_settings, fg_color="transparent")
        row2.pack(fill="x", pady=4, padx=18)
        ctk.CTkLabel(
            row2, text=t("secret"), width=50, anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#8B8B9B",
        ).pack(side="left")
        self.secret_entry = ctk.CTkEntry(
            row2, width=150, height=32, show="•",
            placeholder_text=t("secret_placeholder"),
            corner_radius=8, border_width=2, border_color="#3D3D4D",
        )
        self.secret_entry.pack(side="left", padx=(0, 12))

        self.connect_btn = ctk.CTkButton(
            row2, text=t("reconnect"), width=85, height=32, corner_radius=8,
            fg_color="#6B46FF", hover_color="#7B56FF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._reconnect,
        )
        self.connect_btn.pack(side="right")

        self.host_entry.insert(0, self.config.get("clash_host", "127.0.0.1"))
        self.port_entry.insert(0, str(self.config.get("clash_port", 9097)))
        self.secret_entry.insert(0, self.config.get("clash_secret", ""))

        # 撑开一点高度
        ctk.CTkLabel(self.clash_settings, text="", height=4).pack()

    def _build_ajiasu_settings(self):
        """AJiaSu 设置面板"""
        self.ajiasu_settings = ctk.CTkFrame(self.settings_frame, fg_color="transparent")

        row1 = ctk.CTkFrame(self.ajiasu_settings, fg_color="transparent")
        row1.pack(fill="x", pady=4, padx=18)
        ctk.CTkLabel(
            row1, text=t("ajiasu_path"), width=80, anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#8B8B9B",
        ).pack(side="left")
        self.ajiasu_path_entry = ctk.CTkEntry(
            row1, height=32, corner_radius=8,
            border_width=2, border_color="#3D3D4D",
        )
        self.ajiasu_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.ajiasu_path_entry.insert(0, self.config.get("ajiasu_install_path", ""))
        ctk.CTkButton(
            row1, text="…", width=32, height=32, corner_radius=8,
            fg_color="#2D2D3D", hover_color="#3D3D4D",
            font=ctk.CTkFont(size=14, weight="bold"),
            border_width=2, border_color="#4D4D5D",
            command=self._browse_ajiasu_path,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            row1, text=t("ajiasu_detect"), width=70, height=32, corner_radius=8,
            fg_color="#2D2D3D", hover_color="#3D3D4D",
            font=ctk.CTkFont(size=11, weight="bold"),
            border_width=2, border_color="#4D4D5D",
            command=self._auto_detect_ajiasu_clicked,
        ).pack(side="left")

        row2 = ctk.CTkFrame(self.ajiasu_settings, fg_color="transparent")
        row2.pack(fill="x", pady=4, padx=18)

        self.ajiasu_bridge_status = ctk.CTkLabel(
            row2, text=t("ajiasu_bridge_unknown"),
            font=ctk.CTkFont(size=11),
            text_color="#999999",
        )
        self.ajiasu_bridge_status.pack(side="left")

        ctk.CTkButton(
            row2, text=t("ajiasu_unpatch"), width=80, height=32, corner_radius=8,
            fg_color="#2D2D3D", hover_color="#3D3D4D",
            font=ctk.CTkFont(size=11, weight="bold"),
            border_width=2, border_color="#4D4D5D",
            command=self._unpatch_ajiasu,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            row2, text=t("ajiasu_patch"), width=110, height=32, corner_radius=8,
            fg_color="#6B46FF", hover_color="#7B56FF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._patch_ajiasu,
        ).pack(side="right")

        ctk.CTkLabel(self.ajiasu_settings, text="", height=4).pack()

    def _show_settings_for_mode(self):
        """根据当前 mode 在设置卡片里显示对应面板。"""
        for child in (self.clash_settings, self.ajiasu_settings):
            try:
                child.pack_forget()
            except Exception:
                pass
        if self.mode == MODE_CLASH:
            self.clash_settings.pack(fill="x", pady=(8, 8))
        else:
            self.ajiasu_settings.pack(fill="x", pady=(8, 8))

    # ====================== 模式切换 ======================

    def _on_mode_changed(self, value):
        new_mode = MODE_AJIASU if value == t("mode_ajiasu") else MODE_CLASH
        if new_mode == self.mode:
            return
        # 停止当前切换
        if self.switcher.is_running():
            self.switcher.stop_auto_switch()
            self.start_btn.configure(text=t("start_auto"), fg_color="#6B46FF", hover_color="#7B56FF")
            self.countdown_label.configure(text="--:--", text_color="#4D4D5D")

        self._stop_sync()
        self.mode = new_mode
        self.config.set("mode", new_mode)
        self.config.save()
        self.backend = self.clash_api if new_mode == MODE_CLASH else self.ajiasu_api
        self.switcher = self.clash_switcher if new_mode == MODE_CLASH else self.ajiasu_switcher
        self._show_settings_for_mode()

        self.group_combo.set(t("loading"))
        self.current_proxy_label.configure(text="-")
        self._last_proxy = None

        # 切到 AJiaSu:如果路径还没配置/失效,顺手自动找一次
        if new_mode == MODE_AJIASU:
            saved = self.config.get("ajiasu_install_path", "")
            if not saved or not Path(saved).exists() or not ajiasu_detector.is_install_dir(Path(saved)):
                self._auto_detect_ajiasu()
                # 把检测结果回写到 entry
                detected = self.config.get("ajiasu_install_path", "")
                if detected and hasattr(self, "ajiasu_path_entry"):
                    self.ajiasu_path_entry.delete(0, "end")
                    self.ajiasu_path_entry.insert(0, detected)
                if detected:
                    self._append_log(t("ajiasu_detected", path=detected))
            self._refresh_ajiasu_bridge_status()

        self._update_ajiasu_banner()

        self._append_log(t("mode_switched", mode=value))
        self._init_connection()

    # ====================== 连接 / 探活 ======================

    def _init_connection(self):
        if self.mode == MODE_CLASH:
            self._init_clash_connection()
        else:
            self._init_ajiasu_connection()

    def _init_clash_connection(self):
        def do_connect():
            if self.clash_api.test_connection():
                version = self.clash_api.get_version()
                v = version.get("version", "?") if version else "?"
                self.root.after(0, lambda: self.status_indicator.configure(
                    text=f"{t('status_connected')} v{v}", text_color="#5FD068"
                ))
                self.root.after(0, self._refresh_groups)
                self.root.after(0, lambda: self._append_log(t("auto_connected")))
                self.root.after(0, self._start_sync)
            else:
                self.root.after(0, lambda: self.status_indicator.configure(
                    text=t("status_disconnected"), text_color="#FF4757"
                ))
                self.root.after(0, lambda: self._append_log(t("connect_failed_tip")))
                self.root.after(0, lambda: self.group_combo.set(t("please_connect")))
                self.root.after(0, self._stop_sync)

        threading.Thread(target=do_connect, daemon=True).start()

    def _init_ajiasu_connection(self):
        def do_connect():
            ok = self.ajiasu_api.test_connection()
            self.root.after(0, self._refresh_ajiasu_bridge_status)
            self.root.after(0, self._update_ajiasu_banner)
            if ok:
                self.root.after(0, lambda: self.status_indicator.configure(
                    text=t("ajiasu_bridge_online"), text_color="#5FD068"
                ))
                self.root.after(0, self._refresh_groups)
                self.root.after(0, lambda: self._append_log(t("ajiasu_bridge_online")))
                self.root.after(0, self._start_sync)
            else:
                self.root.after(0, lambda: self.status_indicator.configure(
                    text=t("ajiasu_bridge_offline"), text_color="#FF4757"
                ))
                self.root.after(0, lambda: self._append_log(t("ajiasu_bridge_offline_tip")))
                self.root.after(0, lambda: self.group_combo.set(t("please_connect")))
                self.root.after(0, self._stop_sync)

        threading.Thread(target=do_connect, daemon=True).start()

    def _start_sync(self):
        self._stop_sync()
        self._sync_with_backend()

    def _stop_sync(self):
        if self._sync_timer_id:
            self.root.after_cancel(self._sync_timer_id)
            self._sync_timer_id = None

    def _sync_with_backend(self):
        def do_sync():
            try:
                # AJiaSu 模式:每次同步先用 mtime 心跳判桥是否在线,
                # 把状态指示同步到顶部状态栏。这样掉线能即时变红。
                if self.mode == MODE_AJIASU:
                    alive = self.ajiasu_api.is_alive()
                    if alive:
                        self.root.after(0, lambda: self.status_indicator.configure(
                            text=t("ajiasu_bridge_online"), text_color="#5FD068"
                        ))
                    else:
                        self.root.after(0, lambda: self.status_indicator.configure(
                            text=t("ajiasu_bridge_offline"), text_color="#FF4757"
                        ))
                        # 桥不在线就别再去 IPC,免得 8s 超时阻塞 sync 线程
                        return

                group = self.group_combo.get()
                placeholders = (t("loading"), t("please_connect"), t("no_proxy_group"))
                if group in placeholders:
                    return

                current = self.backend.get_current_proxy(group)
                if current and current != self._last_proxy:
                    self._last_proxy = current
                    self.root.after(0, lambda: self.current_proxy_label.configure(text=current))

                groups = self.backend.get_proxy_groups()
                if groups:
                    names = [g["name"] for g in groups]
                    current_values = list(self.group_combo.cget("values") or [])
                    if names != current_values:
                        self.root.after(0, lambda: self.group_combo.configure(values=names))
            except Exception as e:
                logger.debug(f"Sync failed: {e}")

        threading.Thread(target=do_sync, daemon=True).start()
        self._sync_timer_id = self.root.after(2000, self._sync_with_backend)

    # ====================== Clash 设置交互 ======================

    def _reconnect(self):
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
        self._init_clash_connection()

    # ====================== AJiaSu 设置交互 ======================

    def _browse_ajiasu_path(self):
        d = filedialog.askdirectory(
            title=t("ajiasu_path"),
            initialdir=self.ajiasu_path_entry.get() or str(Path.home()),
        )
        if d:
            self.ajiasu_path_entry.delete(0, "end")
            self.ajiasu_path_entry.insert(0, d)
            self.config.set("ajiasu_install_path", d)
            self.config.save()
            self._refresh_ajiasu_bridge_status()
            self._update_ajiasu_banner()

    def _auto_detect_ajiasu_clicked(self):
        d = ajiasu_detector.detect_install_dir()
        if d:
            self.ajiasu_path_entry.delete(0, "end")
            self.ajiasu_path_entry.insert(0, str(d))
            self.config.set("ajiasu_install_path", str(d))
            self.config.save()
            self._append_log(t("ajiasu_detected", path=str(d)))
            self._refresh_ajiasu_bridge_status()
            self._update_ajiasu_banner()
        else:
            self._append_log(t("ajiasu_not_detected"))

    def _ajiasu_install_dir(self) -> Optional[Path]:
        p = self.ajiasu_path_entry.get().strip() if hasattr(self, "ajiasu_path_entry") \
            else self.config.get("ajiasu_install_path", "")
        if not p:
            return None
        path = Path(p)
        return path if ajiasu_detector.is_install_dir(path) else None

    def _refresh_ajiasu_bridge_status(self):
        d = self._ajiasu_install_dir()
        if not hasattr(self, "ajiasu_bridge_status"):
            return
        if d is None:
            self.ajiasu_bridge_status.configure(
                text=t("ajiasu_path_invalid"), text_color="#FF4757"
            )
            return
        res = d / "res.fvr"
        try:
            patched = ajiasu_patcher.is_patched(res)
        except Exception:
            patched = False
        if patched:
            self.ajiasu_bridge_status.configure(
                text=t("ajiasu_bridge_patched"), text_color="#5FD068"
            )
        else:
            self.ajiasu_bridge_status.configure(
                text=t("ajiasu_bridge_not_patched"), text_color="#FFB454"
            )

    def _patch_ajiasu(self):
        d = self._ajiasu_install_dir()
        if d is None:
            self._append_log(t("ajiasu_path_invalid"))
            return
        if ajiasu_detector.is_running():
            self._append_log(t("ajiasu_running_warn"))
            return
        # 先做权限预检,装在 Program Files 时这里会拦下
        if not ajiasu_patcher.can_write(d) and not win_admin.is_admin():
            self._prompt_relaunch_as_admin(d / "res.fvr")
            return
        ok, msg = ajiasu_patcher.patch(d)
        self._append_log(("✓ " if ok else "✗ ") + msg)
        # 写失败也可能是权限问题(并发场景);兜底再问一次
        if not ok and not win_admin.is_admin() and not ajiasu_patcher.can_write(d):
            self._prompt_relaunch_as_admin(d / "res.fvr")
            return
        self._refresh_ajiasu_bridge_status()
        self._update_ajiasu_banner()
        if ok:
            self._append_log(t("ajiasu_patch_done_tip"))

    def _prompt_relaunch_as_admin(self, target_path: Path):
        """弹窗提示用户以管理员身份重启,确认则提权重启并退出当前进程。"""
        self._append_log(f"{t('ajiasu_no_write_perm')}: {target_path}")
        try:
            yes = messagebox.askyesno(
                title=t("ajiasu_need_admin_title"),
                message=t("ajiasu_need_admin_msg", path=str(target_path)),
            )
        except Exception:
            yes = False
        if not yes:
            return
        if win_admin.relaunch_as_admin():
            try:
                self.config.save()
            except Exception:
                pass
            # 退出当前(非管理员)进程,新进程会带管理员上下文起来
            self.root.destroy()
            sys.exit(0)
        else:
            self._append_log(t("ajiasu_relaunch_failed"))

    def _unpatch_ajiasu(self):
        d = self._ajiasu_install_dir()
        if d is None:
            self._append_log(t("ajiasu_path_invalid"))
            return
        if ajiasu_detector.is_running():
            self._append_log(t("ajiasu_running_warn"))
            return
        if not ajiasu_patcher.can_write(d) and not win_admin.is_admin():
            self._prompt_relaunch_as_admin(d / "res.fvr")
            return
        ok, msg = ajiasu_patcher.unpatch(d)
        self._append_log(("✓ " if ok else "✗ ") + msg)
        self._refresh_ajiasu_bridge_status()
        self._update_ajiasu_banner()

    def _update_ajiasu_banner(self):
        """根据 mode + 路径 + 补丁状态,显示/隐藏 + 设置横幅文案。"""
        if not hasattr(self, "ajiasu_banner"):
            return

        def hide():
            try: self.ajiasu_banner.pack_forget()
            except Exception: pass

        def show(text):
            self.ajiasu_banner.configure(text=text)
            try:
                self.ajiasu_banner.pack(
                    fill="x", pady=(0, 10), before=self._main_inner_first_row
                )
            except Exception:
                self.ajiasu_banner.pack(fill="x", pady=(0, 10))

        if self.mode != MODE_AJIASU:
            hide()
            return
        d = self._ajiasu_install_dir()
        if d is None:
            show(t("ajiasu_banner_no_path"))
            return
        try:
            patched = ajiasu_patcher.is_patched(d / "res.fvr")
        except Exception:
            patched = False
        if patched:
            hide()
        else:
            show(t("ajiasu_banner_unpatched"))

    def _on_ajiasu_banner_click(self):
        d = self._ajiasu_install_dir()
        if d is None:
            # 没路径就展开设置面板让用户配置
            if not self._settings_expanded:
                self._toggle_settings()
            return
        # 有路径,直接走打补丁流程(里面会处理权限)
        self._patch_ajiasu()

    # ====================== 主面板交互 ======================

    def _refresh_groups(self):
        try:
            groups = self.backend.get_proxy_groups()
        except Exception as e:
            self._append_log(f"刷新分组失败: {e}")
            return
        names = [g["name"] for g in groups] if groups else []
        if not names:
            self.group_combo.configure(values=[])
            self.group_combo.set(t("no_proxy_group"))
            return

        self.group_combo.configure(values=names)
        saved_key = "selected_group" if self.mode == MODE_CLASH else "ajiasu_selected_group"
        saved = self.config.get(saved_key)
        if saved and saved in names:
            self.group_combo.set(saved)
        else:
            self.group_combo.set(names[0])
        self._on_group_selected(None)

    def _on_group_selected(self, _):
        group = self.group_combo.get()
        placeholders = (t("loading"), t("please_connect"), t("no_proxy_group"))
        if not group or group in placeholders:
            return
        try:
            current = self.backend.get_current_proxy(group)
        except Exception:
            current = None
        self.current_proxy_label.configure(text=current or "-")
        self._last_proxy = current
        saved_key = "selected_group" if self.mode == MODE_CLASH else "ajiasu_selected_group"
        self.config.set(saved_key, group)
        self.config.save()

    def _toggle_auto_switch(self):
        if self.switcher.is_running():
            self.switcher.stop_auto_switch()
            self.start_btn.configure(text=t("start_auto"), fg_color="#6B46FF", hover_color="#7B56FF")
            self.countdown_label.configure(text="--:--", text_color="#4D4D5D")
            return

        group = self.group_combo.get()
        placeholders = (t("loading"), t("please_connect"), t("no_proxy_group"))
        if group in placeholders:
            self._append_log(t("please_select_group"))
            return

        try:
            interval = int(self.interval_entry.get() or 60)
        except ValueError:
            self._append_log(t("interval_must_be_number"))
            return
        if interval < 1:
            interval = 1

        self.config.set("interval_seconds", interval)
        self.config.set("check_before_switch", self.check_var.get())
        # 持久化当前选中的 group
        saved_key = "selected_group" if self.mode == MODE_CLASH else "ajiasu_selected_group"
        self.config.set(saved_key, group)
        self.config.save()

        self.switcher.start_auto_switch()
        self.start_btn.configure(text=t("stop"), fg_color="#FF4757", hover_color="#FF6B7A")
        self.countdown_label.configure(text_color="#6B46FF")

    def _switch_now(self):
        group = self.group_combo.get()
        placeholders = (t("loading"), t("please_connect"), t("no_proxy_group"))
        if group in placeholders:
            self._append_log(t("please_select_group"))
            return
        self.config.set("check_before_switch", self.check_var.get())

        def do_switch():
            self.switcher.switch_proxy(group)
            self.root.after(100, self._on_group_selected, None)

        threading.Thread(target=do_switch, daemon=True).start()

    def _test_all_proxies(self):
        group = self.group_combo.get()
        placeholders = (t("loading"), t("please_connect"), t("no_proxy_group"))
        if group in placeholders:
            self._append_log(t("please_select_group"))
            return

        proxies = self.backend.get_group_proxies(group)
        if not proxies:
            return

        self._append_log(t("testing_proxies", count=len(proxies)))
        self.test_btn.configure(state="disabled")

        def do_test():
            try:
                if self.mode == MODE_CLASH:
                    results = self.proxy_checker.get_all_proxy_delays(proxies)
                    ok = sum(1 for r in results.values() if r[0])
                    for name, (available, _delay, msg) in results.items():
                        icon = "✓" if available else "✗"
                        self._append_log(f"  {icon} {name}: {msg}")
                else:
                    # AJiaSu: 一次性 ping 整组,然后读 reports
                    api = self.ajiasu_api
                    ids = [api._name_to_id(p) for p in proxies]
                    ids = [i for i in ids if i]
                    if not ids:
                        self._append_log("没有可测速的节点")
                        return
                    api.ping_servers(ids)
                    import time as _t
                    _t.sleep(min(5.0, 0.05 * len(ids) + 1.0))
                    reports = api.get_ping_reports() or []
                    id2delay = {}
                    for r in reports:
                        rid = ajiasu_api._pick(r or {}, ["ServerId", "serverId", "Id", "id"])
                        d = ajiasu_api._pick(
                            r, ["Delay", "delay", "Ping", "ping", "Latency", "latency", "Ms", "ms"]
                        )
                        try:
                            di = int(d)
                        except (TypeError, ValueError):
                            continue
                        if rid is not None:
                            id2delay[str(rid)] = di
                    ok = 0
                    for name in proxies:
                        sid = api._name_to_id(name)
                        delay = id2delay.get(str(sid)) if sid else None
                        if delay is not None and delay > 0:
                            ok += 1
                            self._append_log(f"  ✓ {name}: {delay}ms")
                        else:
                            self._append_log(f"  ✗ {name}: 无响应")
                self._append_log(t("test_complete", ok=ok, total=len(proxies)))
            except Exception as e:
                self._append_log(f"测速失败: {e}")
            finally:
                self.root.after(0, lambda: self.test_btn.configure(state="normal"))

        threading.Thread(target=do_test, daemon=True).start()

    # ====================== 杂项 ======================

    def _toggle_language(self):
        current = get_language()
        new_lang = "en_US" if current == "zh_CN" else "zh_CN"
        set_language(new_lang)
        self.config.set("language", new_lang)
        self.config.save()
        self._append_log("Language changed. Please restart the app. / 语言已更改,请重启应用。")
        self.lang_btn.configure(text="EN" if new_lang == "zh_CN" else "中")

    def _toggle_settings(self):
        if self._settings_expanded:
            self.settings_frame.pack_forget()
            self._settings_expanded = False
        else:
            self.settings_frame.pack(fill="x", padx=24, pady=(0, 8), before=self.main_card)
            self._settings_expanded = True
            if self.mode == MODE_AJIASU:
                self._refresh_ajiasu_bridge_status()

    def _on_tick(self, seconds: int):
        m, s = divmod(seconds, 60)
        text = f"{m:02d}:{s:02d}"
        self.root.after(0, lambda: self.countdown_label.configure(text=text))

    def _update_status(self, status: str):
        # 当前实现没有专门的"切换状态"标签;保留接口以兼容回调
        pass

    def _append_log(self, message: str):
        def do_append():
            time_str = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{time_str}] {message}\n")
            self.log_text.see("end")

        if threading.current_thread() is threading.main_thread():
            do_append()
        else:
            self.root.after(0, do_append)

    def _clear_log(self):
        self.log_text.delete("1.0", "end")

    def _on_closing(self):
        self._stop_sync()
        for sw in (self.clash_switcher, self.ajiasu_switcher):
            if sw.is_running():
                sw.stop_auto_switch()
        self.config.save()
        self.root.destroy()

    def run(self):
        if self.mode == MODE_CLASH:
            self._append_log(t("detecting_clash"))
        else:
            self._append_log(t("ajiasu_starting"))
        self.root.mainloop()


def main():
    app = IntervalProxyGUI()
    app.run()


if __name__ == "__main__":
    main()
