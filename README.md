# srun-login

> 跨平台校园网自动登录工具 · 支持所有使用深澜（Srun/BigSrun）认证系统的高校

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)

---

## ⚠️ 重要声明（请务必阅读）

> **本项目仅供学习交流与个人正常使用，严禁用于任何商业用途或非法途径。**
>
> 使用本项目所造成的任何后果（包括但不限于账号被封禁、网络访问受限、学校纪律处分等）均由使用者自行承担，本项目开发者不承担任何法律及连带责任。
>
> 请遵守所在机构的校园网使用规范，合理使用自动化工具。

---

## 🎯 项目简介

本工具用于自动化登录采用 **深澜软件（Srun/BigSrun）** 认证系统的校园网。

> **适用范围**：不局限于特定学校。任何使用深澜 Srun Portal 认证系统的校园网环境均可使用，只需填入对应网关地址和 `ac_id` 参数。

### 功能特性

- **自动登录 / 登出** — 调用 Srun Portal API 完成身份认证，支持在线状态查询
- **跨平台** — Windows · macOS · Linux 完整支持
- **图形界面** — CustomTkinter 卡片式 GUI，简洁现代，支持 Light/Dark 主题
- **命令行向导** — 无显示器环境（Linux 服务器、树莓派等）可用 CLI 交互式配置
- **定时模式** — 后台持续监控网络状态，断线自动重连，支持自定义活跃时段
- **结构化错误反馈** — 24 种错误码覆盖网络/认证/配置/系统层，精准定位问题
- **网络预检** — 登录前自动检测网卡状态、网关可达性、DNS 解析
- **安全存储** — 密码通过 OS 原生密钥链 + PBKDF2 加密存储，不以明文落盘
- **开机自启** — 注册系统自启项（注册表 / launchd / XDG autostart）
- **系统托盘** — 最小化到托盘，右键菜单快捷操作
- **单实例锁** — 防止重复启动，第二次运行自动激活已有窗口

### 适用场景

- 多设备需要手动打开网页登录的桌面环境
- 希望开机后自动保持网络连接，无需人工干预
- 在服务器、树莓派、香橙派等长期运行设备上自动联网
- 校园网频繁掉线，需要自动重连

> ⚠️ **如果你只需要偶尔上网，且校园网连接稳定，直接打开浏览器登录即可。** 本工具最适合有自动化需求的用户。

---

## 📦 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动图形界面
python main.py

# 静默登录（用于开机自启脚本）
python main.py --background

# 交互式 CLI 配置向导（无显示器环境）
python main.py --cli

# 定时模式（后台持续监控，断线自动重连）
python main.py --timed

# 停止定时模式 / 断开连接
python stop.py
```

### 启动参数

| 参数 | 说明 |
|------|------|
| `--minimized` | 启动后最小化到系统托盘 |
| `--background` | 后台静默登录，完成后自动退出 |
| `--cli` | 强制 CLI 交互式配置向导 |
| `--timed` | 启动定时模式（持续监控网络，自动重连） |
| `--configure` | 强制显示配置界面 |
| `--quit` | 通知已运行的实例退出 |
| `--stop` | 停止正在运行的定时模式 |
| `--skip-preflight` | 跳过网络环境预检（故障排查时使用） |

---

## 🛠️ 技术栈

| 模块 | 技术 |
|------|------|
| 核心协议 | `requests` + 自实现 `xencode`（XXTEA）+ HMAC-MD5 + SHA1 |
| GUI | `customtkinter`（Minimalism & Swiss Style 卡片式布局）|
| 系统托盘 | `pystray` + `Pillow` |
| 密钥链 | `keyring`（跨平台 OS 原生密钥链）|
| 本地加密 | `cryptography`（Fernet + PBKDF2-SHA256，100k 迭代）|
| 网络检测 | `netifaces` + socket 预检 |

---

## 🛑 停止与断开

### 命令行

```bash
python stop.py              # 交互式菜单：停止定时 / 断开连接 / 取消
python stop.py --disconnect # 直接断开连接并停止所有任务
```

### GUI

- **停止定时** — 终止定时监控，保持已登录状态
- **断开连接** — 登出校园网并停止所有任务
- 点击窗口 X 最小化到系统托盘，托盘菜单可快捷操作

---

## ⚙️ 配置说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `gateway` | 校园网认证网关地址 | `10.0.0.3` |
| `ac_id` | 运营商编号 | `1` |
| `username` | 校园网账号 | 学号/工号 |
| `password` | 校园网密码 | — |

> 密码通过系统密钥链 + PBKDF2 加密存储，**不以明文写入任何配置文件**。

### 凭证优先级

1. **环境变量** `SRUN_USERNAME` / `SRUN_PASSWORD` — 最高优先级，不落盘
2. **OS 密钥链** — Windows 凭据管理器 / macOS 钥匙串 / Linux Secret Service
3. **Fernet 加密文件** — 机器绑定的 PBKDF2 加密回退方案

### 数据存储位置

| 操作系统 | 配置路径 |
|----------|----------|
| Windows | `%APPDATA%\srun_login\config.json` |
| macOS | `~/Library/Application Support/srun_login/config.json` |
| Linux | `~/.config/srun_login/config.json` |

### 定时模式配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `false` | 是否启用 |
| `start_time` | `07:00` | 活跃时段开始 |
| `end_time` | `23:59` | 活跃时段结束 |
| `check_interval_connected` | `600` | 已连接时的检查间隔（秒） |
| `check_interval_disconnected` | `120` | 断线时的重试间隔（秒） |
| `check_interval_retry` | `180` | 登录失败后的重试间隔（秒） |
| `max_retries_per_session` | `5` | 单轮最大重试次数 |

---

## 📁 项目结构

```
srun_login/
├── README.md              # 项目说明文档
├── main.py                # 程序入口（参数解析、IPC、路由）
├── srun_login.py          # 核心登录协议（XXTEA 加密、HMAC-MD5、Srun API）
├── config_manager.py      # 配置与凭证管理（keyring + PBKDF2 + Fernet）
├── gui.py                 # 图形界面（CustomTkinter 卡片式布局 + 系统托盘）
├── cli_wizard.py          # 交互式 CLI 配置向导
├── timed_mode.py          # 定时模式后台守护进程
├── auto_start.py          # 跨平台开机自启（注册表 / launchd / XDG）
├── stop.py                # 停止定时模式 / 断开连接
├── environment.py         # 平台检测与网络接口查询
├── errors.py              # 结构化错误码（5 大类 24 种场景）
├── network_checker.py     # 登录前网络预检（网卡 / 网关 / DNS）
├── shared.py              # 共享常量、IPC 工具、单实例锁
├── smoke_test.py          # 快速自检脚本
├── requirements.txt       # Python 依赖
├── config.example.json    # 配置文件模板
├── icon.png               # 应用图标
└── docs/
    └── error_codes.md     # 错误码详细说明
```

---

## 🔧 如何获取网关地址和 AC_ID

### 通过浏览器开发者工具（推荐）

1. 打开浏览器，按 `F12` → **网络 (Network)** → 勾选「保留日志」
2. 连接校园网，打开任意 HTTP 网站（如 `http://www.baidu.com`），浏览器会自动跳转到认证页面
3. 在 Network 面板找到 `/cgi-bin/get_challenge` 或 `/cgi-bin/srun_portal` 请求
4. 从 URL / Payload 中提取 `ac_id` 和网关地址

### 通过登录页 URL

```
http://10.0.0.3/srun_portal_pc?ac_id=1&theme=pro
```
- `10.0.0.3` = 网关地址
- `ac_id=1` = AC_ID

### 常见默认值

| 参数 | 常见值 |
|------|--------|
| AC_ID | `1` |
| 网关 | `10.0.0.3`、`192.168.168.168`、`172.17.1.2` |

---

## 📋 错误码速查

| 错误码 | 场景 | 含义 |
|--------|------|------|
| E1001 | 无可用网卡 | 请检查无线/有线网卡是否已启用 |
| E1002 | 网关不可达 | 无法连接到校园网网关，检查网络连接 |
| E1003 | DNS 失败 | DNS 解析失败，检查网络设置 |
| E2001 | 密码错误 | 账号或密码错误 |
| E2004 | 已在线 | 账号已在其他设备登录 |
| E2009 | 挑战码失败 | 网关可能不支持该认证方式 |
| E3004 | 缺少凭据 | 未找到登录凭据，请先配置 |
| E4002 | PID 残留 | 残留定时任务 PID 文件已自动清理 |

> 完整列表见 [docs/error_codes.md](docs/error_codes.md)

---

## ❓ 常见问题

### 1. 程序启动时报 `ModuleNotFoundError`
确保已执行 `pip install -r requirements.txt`

### 2. "没有找到校园网，请检查设备是否正常"
网卡被禁用或未安装驱动。检查设备管理器中网络适配器状态，或确认网线/WiFi 已连接。

### 3. "无法连接到校园网网关"
- 核对网关地址是否正确
- 确认设备已连接校园网（有线或 WiFi）
- 检查防火墙是否阻止了到网关 80 端口的连接

### 4. 登录失败但无明确提示
程序现在会输出 `[EXXXX]` 格式的结构化错误码，根据错误码对照上表或 `docs/error_codes.md` 排查。

### 5. 密钥链不可用
启动系统密钥链服务后重试。程序会自动降级到 PBKDF2 加密文件存储。

---

## 🔐 安全说明

1. **密码不落盘** — 优先使用 OS 原生密钥链，回退到 PBKDF2（100k 迭代）+ Fernet 加密
2. **Token 一次性** — 每次登录使用服务器下发的随机 `challenge` token
3. **请求限频** — HTTP 请求内置超时与间隔，不对服务器造成压力
4. **单实例锁** — 文件锁 + Socket IPC 防止重复运行

---

## ⚖️ 法律风险提示

### 合法使用边界

本工具模拟人工打开浏览器、输入账号密码、点击登录的自动化操作。若仅用于**个人账号的正常认证**，通常被视为效率工具：

- ✅ 仅登录自己的账号
- ✅ 不突破访问控制或身份验证机制
- ✅ 不干扰或破坏校园网计费系统
- ✅ 不尝试破解限速、多设备绕过等限制

### 明确禁止

- ❌ 绕过计费、"白嫖"时长、破解多设备限制
- ❌ 对认证服务器发起大规模自动化请求（可能构成 DDoS）
- ❌ 破解或篡改校园网认证算法

> 违规后果包括：账号封禁、IP 被封、网络访问权限撤销、学校纪律处分。

---

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE)

---

## 👤 作者

[爱好摸鱼真君] — GitHub: [@lxiaodong681-lab](https://github.com/lxiaodong681-lab)
