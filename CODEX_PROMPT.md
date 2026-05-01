# AI Codex 提示词 - 校园网自动登录工具

---

## 🎯 项目概述

请为以下项目生成完整的 Python 代码。

**项目名称**：Automatic Login Script for Campus Network
**功能**：校园网自动登录工具，支持深澜（Srun）认证系统，提供图形界面和开机自启
**语言**：Python 3.8+
**目标用户**：高校学生（尤其是江西师范大学）

---

## 📁 项目结构

```
srun_login/
├── README.md              # 项目说明
├── srun_login.py          # 核心登录逻辑
├── config_manager.py      # 配置管理（密钥链）
├── auto_start.py          # 开机自启
├── gui.py                 # 图形界面
├── main.py                # 主入口
├── requirements.txt       # 依赖
└── .gitignore             # Git忽略
```

---

## 🔐 模块一：srun_login.py（核心登录逻辑）

### 基本信息
- 模块名：`SRUNLogin`
- 不可独立运行（无 `if __name__ == "__main__"`）
- 需要被 `gui.py` 和 `main.py` 导入使用

### 构造函数
```python
SRUNLogin(username: str, password: str, gateway: str, ac_id: str, ip: str = None)
```

### 公开方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `login() -> bool` | True/False | 执行完整登录流程 |
| `logout() -> bool` | True/False | 登出校园网 |
| `get_challenge() -> str\|None` | challenge token | 获取动态挑战码 |
| `check_status() -> bool` | True/False | 检查是否已在线 |
| `get_error_message(resp_text: str) -> str` | 错误描述 | 解析响应文本 |

### 加密算法（必须完整实现）

**1. xencode(msg, key)** - TEA变种算法
- 输入：明文字符串 + challenge token
- 输出：加密后的列表（用于后续base64）

**2. get_base64(s)** - 自定义Base64
- 使用深澜专用字符集：`LVoJPiCN2R8G90yg+hmFHuacZ1OWMnrsSTXkYpUq/3dlbfKwv6xztjI7DeBE45QA`
- 不是标准base64

**3. get_md5(password, token) -> str**
- HMAC-MD5，消息是**空字符串**（不是密码原文）
- 格式：`{MD5}` + hex结果

**4. get_sha1(value) -> str**
- 标准SHA1

### 登录流程（API调用顺序）

**Step 1** - GET登录页面，提取user_ip：
```
http://{GATEWAY}/srun_portal_pc?ac_id={AC_ID}&theme=pro
```
正则：`id="user_ip" value="(.*?)"`

**Step 2** - GET获取challenge token：
```
http://{GATEWAY}/cgi-bin/get_challenge?callback={jQuery_timestamp}_{timestamp}&username={USERNAME}&ip={LOCAL_IP}&_={timestamp}
```
响应中提取：`"challenge":"..."`

**Step 3** - 构造info字段（JSON+srun_bx1加密）：
```json
{"username":"...","password":"...","ip":"...","acid":"...","enc_ver":"srun_bx1"}
```
用xencode加密后，prefix `{SRBX1}` + base64

**Step 4** - 构造password字段：HMAC-MD5(空字符串, token)，prefix `{MD5}`

**Step 5** - 构造chksum（SHA1）：
顺序：token+username + token+md5_empty + token+ac_id + token+ip + token+"200" + token+"1" + token+encrypted_info

**Step 6** - POST登录请求：
```
http://{GATEWAY}/cgi-bin/srun_portal
```
参数：callback, action=login, username, password, ac_id, ip, info, chksum, n=200, type=1

**Step 7** - 解析响应：
成功标志：`login_ok` 或 `"error":"ok"` 或 包含`suc`且不含`error`

### 日志格式（print输出）
- 🐾 步骤提示
- 📍 IP/Token信息
- ✨ 成功获取关键数据
- 🚀 发起请求
- 🎉 登录成功
- ❌ 失败/错误
- ⚠️ 警告

### 错误处理要求
- 网络超时：5秒
- 网关无响应：打印错误返回False
- 业务错误（密码错/已在线/余额不足）：解析响应文字，返回人类可读错误

---

## 🔑 模块二：config_manager.py（配置管理）

### 基本信息
- 类名：`ConfigManager`
- 核心原则：**密码永不存明文到磁盘**

### 双重存储机制
| 数据 | 存储位置 |
|------|---------|
| 网关、AC_ID、自启设置 | config.json（~/.config/srun_login/） |
| 账号、密码 | OS密钥链（keyring） |

### 路径规范
- Linux: `~/.config/srun_login/config.json`
- Windows: `%APPDATA%\srun_login\config.json`
- macOS: `~/Library/Application Support/srun_login/config.json`

### 构造函数
```python
ConfigManager(app_name:str = "srun_login")
```

### 公开方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `load_config() -> dict` | 配置字典 | 读取config.json |
| `save_config(data: dict) -> None` | None | 保存到config.json |
| `get_username() -> str\|None` | 用户名 | 从Keychain读取 |
| `get_password() -> str\|None` | 密码 | 从Keychain读取 |
| `set_credentials(username: str, password: str) -> None` | None | 存入Keychain |
| `delete_credentials() -> None` | None | 删除Keychain凭据 |
| `set_auto_start(enabled: bool) -> None` | None | 更新自启配置 |
| `is_auto_start_enabled() -> bool` | bool | 查询自启状态 |
| `is_first_run() -> bool` | bool | 是否首次运行 |
| `mark_first_run_done() -> None` | None | 标记首次运行完成 |
| `reset_all() -> None` | None | 清除所有配置 |

### config.json格式
```json
{
  "username": "202526204010@cmcc",
  "gateway": "172.17.1.2",
  "ac_id": "1",
  "default_ip": "10.129.198.6",
  "auto_start": true,
  "auto_connect_on_start": false,
  "start_minimized": false,
  "first_run": true
}
```

### 安全要求
- config.json文件权限：0o600（仅所有者可读写）
- Keychain不可用时，提示用户，不要降级到明文文件
- 保存前验证：网关地址格式、账号非空

### 平台差异
- Linux：优先SecretService(GNOME)，fallback到KWallet，再失败则警告
- Windows：默认Windows Credential Manager
- macOS：默认Keychain

---

## ⚡ 模块三：auto_start.py（开机自启）

### 基本信息
- 类名：`AutoStartManager`
- 支持平台：Windows、macOS、Linux

### 构造函数
```python
AutoStartManager(app_name: str = "srun_login", app_path: str = None)
```

### 公开方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `enable() -> bool` | 是否成功 | 注册开机自启 |
| `disable() -> bool` | 是否成功 | 取消开机自启 |
| `is_enabled() -> bool` | bool | 查询当前状态 |
| `get_platform() -> str` | "windows"/"darwin"/"linux" | 获取平台 |

### Windows实现
- 注册表路径：`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
- 使用`winreg`模块
- fallback：Startup文件夹快捷方式

### macOS实现
- plist路径：`~/Library/LaunchAgents/com.srun.login.plist`
- RunAtLoad=true, KeepAlive=false

### Linux实现
- .desktop路径：`~/.config/autostart/srun_login.desktop`
- X-GNOME-Autostart-enabled=true
- fallback：systemd user service

### 命令行参数
main.py需要支持：`--minimized`、`--background`、`--configure`、`--quit`

---

## 🖼️ 模块四：gui.py（图形界面）

### 基本信息
- 使用customtkinter（不是tkinter默认样式）
- 支持深色/浅色模式跟随系统

### 窗口属性
- 标题：校园网自动连接工具
- 默认尺寸：400×520px
- 可调整、最小化、最大化

### 界面布局

```
┌──────────────────────────────────────┐
│  🐾 校园网自动连接工具              _□X │
├──────────────────────────────────────┤
│         [网络状态图标：大号]           │
│         状态文字                      │
│                                      │
│  账号：  [__________________]        │
│  密码：  [__________________] 🔒    │
│                                      │
│  网关：  [__________________]       │
│  AC_ID： [__________________]       │
│                                      │
│  ☑ 开机自动启动                      │
│  ☑ 启动时自动连接                    │
│  ☑ 连接成功后最小化到托盘             │
│                                      │
│  [ 保存配置 ]  [ 立即连接 ]           │
│                                      │
│  ─────────────────────────────────   │
│  日志输出区（只读Text，带滚动）        │
└──────────────────────────────────────┘
```

### 系统托盘
- 托盘图标状态：🟢已连接 🔴未连接 🟡连接中
- 右键菜单：打开主界面、立即连接、断开、设置、退出
- 窗口关闭时最小化到托盘（不退出程序）
- 托盘双击恢复窗口

### 单实例保证
- 使用文件锁（fcntl.flock）
- 第二个实例激活第一个窗口后退出

### 事件绑定
- 保存配置 → config_manager + auto_start
- 立即连接 → 子线程调用srun_login.login()，主线程更新UI
- 开机自启复选框 → auto_start.enable/disable
- 窗口关闭 → 最小化到托盘

### 线程安全
- 网络请求必须在子线程
- UI更新用root.after()回到主线程

### 依赖
- customtkinter（现代化GUI）
- threading（后台登录）

---

## 🚀 模块五：main.py（主入口）

### 基本信息
- 程序主入口
- 单实例控制
- 命令行参数解析
- 信号处理（优雅退出）

### 命令行参数

| 参数 | 说明 |
|------|------|
| 无参数 | 显示完整GUI |
| `--minimized` | 启动到托盘，auto_connect_on_start则自动连接 |
| `--background` | 后台静默登录，连接后退出（用于脚本场景） |
| `--configure` | 强制显示配置界面 |
| `--quit` | 退出已运行的实例 |
| `--help` | 显示帮助 |

### 单实例实现
- 锁文件：`~/.config/srun_login/srun_login.lock`
- 文件锁：fcntl.flock(LOCK_EX | LOCK_NB)
- 获取不到锁时检查--quit参数

### 信号处理
- SIGINT（Ctrl+C）：优雅退出
- SIGTERM（kill）：优雅退出
- 退出时释放锁文件

### 启动流程
1. 获取单实例锁
2. 解析命令行参数
3. 加载配置
4. 根据参数决定启动模式
5. 进入GUI事件循环

---

## 📦 模块六：requirements.txt

```
requests>=2.28.0
customtkinter>=5.0.0
keyring>=23.0.0
cryptography>=41.0.0
```

Linux额外依赖：
```bash
sudo apt install libsecret-1-dev python3-dev
pip install secretstorage
```

---

## ⚠️ 重要约束

1. **密码不能明文存储** - 任何时候都不能把密码写进文件
2. **跨平台兼容** - Windows/macOS/Linux三端都要能用
3. **线程安全** - GUI中网络操作必须走子线程
4. **错误处理** - 所有网络操作都要有超时和异常处理
5. **日志输出** - 每一步操作都要有清晰的日志，方便排查
6. **不要引入额外依赖** - 只用requirements.txt里列出的库
7. **代码风格** - 中文注释，变量命名清晰，带类型提示（type hints）

---

## 📋 输出要求

请为每个模块生成完整代码，共6个.py文件：
1. srun_login.py
2. config_manager.py
3. auto_start.py
4. gui.py
5. main.py
6. requirements.txt（保持原样即可）

每个文件的开头加上简短模块说明（英文）。
