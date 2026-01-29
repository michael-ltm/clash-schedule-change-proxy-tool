@echo off
REM Windows 打包脚本

echo === 开始打包 Windows 版本 ===

REM 进入项目目录
cd /d "%~dp0\.."

REM 确保依赖已安装
echo 安装依赖...
uv sync
uv pip install pyinstaller

REM 清理旧的构建
echo 清理旧的构建文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM 打包
echo 开始打包...
uv run pyinstaller build.spec

echo === 打包完成 ===
echo 输出文件位于: dist\

REM 列出打包结果
dir dist\
