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

import os as _os
_dll_dir = _os.path.join(_os.path.dirname(_os.path.abspath(SPEC)), 'bridge_inject', 'dist')
_dll_datas = []
if is_windows and _os.path.isdir(_dll_dir):
    for _name in ('sciter_bridge_x64.dll', 'sciter_bridge_x86.dll'):
        _p = _os.path.join(_dll_dir, _name)
        if _os.path.isfile(_p):
            _dll_datas.append((_p, '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('ajiasu_bridge.js', '.'),
    ] + _dll_datas,
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
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
            'CFBundleShortVersionString': '1.2.2',
        },
    )
