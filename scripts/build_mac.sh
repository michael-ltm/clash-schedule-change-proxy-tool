#!/bin/bash
# macOS 打包脚本

set -e

echo "=== 开始打包 macOS 版本 ==="

# 进入项目目录
cd "$(dirname "$0")/.."

# 确保依赖已安装
echo "安装依赖..."
uv sync
uv pip install pyinstaller

# 清理旧的构建
echo "清理旧的构建文件..."
rm -rf build dist

# 打包
echo "开始打包..."
uv run pyinstaller build.spec

echo "=== 打包完成 ==="
echo "输出文件位于: dist/"

# 列出打包结果
ls -la dist/
