# Clash Proxy Timer

[English](#english) | [简体中文](#简体中文)

---

## English

A cross-platform GUI tool for automatically switching Clash proxies at scheduled intervals.

### Features

- ⏰ **Scheduled Switching** - Automatically switch proxies at customizable intervals
- ✅ **Availability Check** - Verify proxy connectivity before switching
- 🔄 **Real-time Sync** - Sync with Clash Verge in real-time
- 🌍 **Multi-language** - Supports English and Simplified Chinese
- 💾 **Persistent Config** - Settings are saved automatically
- 🖥️ **Cross-platform** - Works on Windows and macOS

### Screenshots

<img src="docs/screenshot.png" width="400" alt="Screenshot">

### Installation

#### Download Binary

Download the latest release for your platform from [Releases](https://github.com/fengyiyang/clash-proxy-timer/releases):

- **Windows**: `ClashProxyTimer.exe`
- **macOS (Apple Silicon)**: `ClashProxyTimer-macOS-arm64.zip`
- **macOS (Intel)**: `ClashProxyTimer-macOS-x64.zip`

#### Run from Source

```bash
# Clone the repository
git clone https://github.com/fengyiyang/clash-proxy-timer.git
cd clash-proxy-timer

# Install dependencies (using uv - recommended)
uv sync

# Run
uv run python main.py
```

Or using pip:

```bash
pip install -r requirements.txt
python main.py
```

### Requirements

- Python 3.8+
- Clash Verge (or any Clash-based proxy tool) running
- Clash External Controller API enabled (default port: 9097)

### Usage

1. **Start the app** - It will auto-detect your Clash settings
2. **Select proxy group** - Choose the group you want to auto-switch
3. **Set interval** - Configure how often to switch (in minutes)
4. **Start** - Click "Start Auto Switch" button

The app will:
- Switch to a random available proxy at each interval
- Check proxy availability before switching (optional)
- Show countdown timer until next switch

### Configuration

Settings are stored in:
- **Windows**: `%APPDATA%/clash-proxy-timer/config.json`
- **macOS/Linux**: `~/.clash-proxy-timer/config.json`

### Building

```bash
# Install build dependencies
uv pip install pyinstaller

# Build
uv run pyinstaller build.spec
```

### License

MIT License

---

## 简体中文

一个跨平台的 Clash 代理定时自动切换工具，带有图形界面。

### 功能特点

- ⏰ **定时切换** - 按自定义间隔自动切换代理
- ✅ **可用性检测** - 切换前验证代理连通性
- 🔄 **实时同步** - 与 Clash Verge 实时同步状态
- 🌍 **多语言** - 支持简体中文和英文
- 💾 **配置持久化** - 设置自动保存
- 🖥️ **跨平台** - 支持 Windows 和 macOS

### 截图

<img src="docs/screenshot.png" width="400" alt="截图">

### 安装

#### 下载可执行文件

从 [Releases](https://github.com/fengyiyang/clash-proxy-timer/releases) 下载适合你系统的版本：

- **Windows**: `ClashProxyTimer.exe`
- **macOS (Apple Silicon)**: `ClashProxyTimer-macOS-arm64.zip`
- **macOS (Intel)**: `ClashProxyTimer-macOS-x64.zip`

#### 从源码运行

```bash
# 克隆仓库
git clone https://github.com/fengyiyang/clash-proxy-timer.git
cd clash-proxy-timer

# 安装依赖（使用 uv - 推荐）
uv sync

# 运行
uv run python main.py
```

或使用 pip：

```bash
pip install -r requirements.txt
python main.py
```

### 系统要求

- Python 3.8+
- Clash Verge（或其他基于 Clash 的代理工具）正在运行
- Clash 外部控制 API 已启用（默认端口：9097）

### 使用方法

1. **启动应用** - 程序会自动检测 Clash 设置
2. **选择代理组** - 选择要自动切换的代理组
3. **设置间隔** - 配置切换间隔（分钟）
4. **开始** - 点击"开始自动切换"按钮

程序将会：
- 每隔设定时间随机切换到一个可用代理
- 切换前检测代理可用性（可选）
- 显示距下次切换的倒计时

### 查找 Clash API 端口

在 **Clash Verge** 中：
1. 打开设置
2. 找到 **Clash 设置**
3. 查看 **外部控制** 端口（通常是 9097）

### 配置文件位置

- **Windows**: `%APPDATA%/clash-proxy-timer/config.json`
- **macOS/Linux**: `~/.clash-proxy-timer/config.json`

### 构建

```bash
# 安装构建依赖
uv pip install pyinstaller

# 构建
uv run pyinstaller build.spec
```

### 开源协议

MIT License

---

## Project Structure / 项目结构

```
clash-proxy-timer/
├── main.py              # Entry point / 入口文件
├── gui.py               # GUI module / 界面模块
├── clash_api.py         # Clash API client / Clash API 客户端
├── clash_detector.py    # Auto-detect Clash settings / 自动检测 Clash 设置
├── proxy_checker.py     # Proxy availability checker / 代理检测器
├── scheduler.py         # Task scheduler / 定时任务调度
├── config.py            # Configuration manager / 配置管理
├── i18n.py              # Internationalization / 国际化
├── build.spec           # PyInstaller config / 打包配置
├── pyproject.toml       # Project metadata / 项目元数据
├── requirements.txt     # Dependencies / 依赖列表
└── README.md            # Documentation / 文档
```

## Contributing / 贡献

Contributions are welcome! Please feel free to submit a Pull Request.

欢迎贡献！请随时提交 Pull Request。

## Acknowledgments / 致谢

- [Clash](https://github.com/Dreamacro/clash) - A rule-based tunnel
- [Clash Verge](https://github.com/clash-verge-rev/clash-verge-rev) - Clash GUI client
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - Modern UI for Tkinter
