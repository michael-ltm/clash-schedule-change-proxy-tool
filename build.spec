# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置文件
使用命令: pyinstaller build.spec
"""

import sys
import platform

# 根据平台设置参数
is_mac = sys.platform == 'darwin'
is_windows = sys.platform == 'win32'

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('ajiasu_bridge.js', '.'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'customtkinter',
        'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ClashProxyTimer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 设为 False 隐藏控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# macOS 打包为 .app
if is_mac:
    app = BUNDLE(
        exe,
        name='定时更改Clash代理.app',
        icon=None,  # 可以设置 icon='icon.icns'
        bundle_identifier='com.clash-proxy-timer.app',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'CFBundleShortVersionString': '1.1.3',
        },
    )
