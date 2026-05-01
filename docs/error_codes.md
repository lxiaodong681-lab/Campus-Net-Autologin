# 错误码与业务异常说明

本文件记录常见业务错误、网络错误与配置错误，便于定位问题与快速解决。

| 模块 | 内容说明 | 例子 | 错误码/类型 | 发生原因 | 解决方案 | 日志路径 |
| --- | --- | --- | --- | --- | --- | --- |
| srun_login | 网络超时 | NetworkTimeoutError (Code: 1001) | requests.exceptions.Timeout | 服务器响应超时，通常是因为网络不稳定或代理设置不当。 | 1. 检查网络连接；2. 关闭 VPN 或代理后重试。 | /logs/error.log |
| srun_login | 网关无响应 | GatewayUnreachableError (Code: 1002) | requests.exceptions.ConnectionError | 网关不可达，可能是网关地址错误或网络未连通。 | 1. 核对网关地址；2. 确认网络可访问校园网。 | /logs/error.log |
| srun_login | Challenge 获取失败 | ChallengeFetchError (Code: 1003) | ValueError | Challenge token 未返回或格式异常。 | 1. 检查网关是否异常；2. 稍后重试。 | /logs/error.log |
| srun_login | 账号或密码错误 | AuthFailed (Code: 2001) | 业务错误码 E3001 | 登录失败，账号或密码不正确。 | 1. 核对账号密码；2. 确认运营商后缀是否正确。 | /logs/error.log |
| srun_login | 已在线 | AlreadyOnline (Code: 2002) | 业务错误码 E2616 | 账号已经在线或 IP 已被占用。 | 1. 先断开已在线设备；2. 重新登录。 | /logs/error.log |
| srun_login | 余额不足/受限 | BalanceInsufficient (Code: 2003) | 业务错误码 E2553 | 账号异常或余额不足，导致登录被拒。 | 1. 登录学校门户确认状态；2. 联系网络中心。 | /logs/error.log |
| config_manager | 密钥链不可用 | KeyringUnavailable (Code: 3001) | keyring.errors.InitError | 系统密钥链服务未启动或权限不足。 | 1. 启动系统密钥服务；2. 重启应用。 | /logs/error.log |
| config_manager | 配置不合法 | ConfigInvalid (Code: 3002) | ValueError | 网关地址格式错误或用户名为空。 | 1. 填写合法的网关地址；2. 确认账号不为空。 | /logs/error.log |
| auto_start | 自启失败 | AutoStartFailed (Code: 4001) | OSError | 注册表/文件写入失败或权限不足。 | 1. 以当前用户权限运行；2. 手动清理旧的自启项后重试。 | /logs/error.log |
| main | 单实例锁失败 | SingleInstanceLockError (Code: 5001) | OSError | 已有实例在运行或锁文件占用。 | 1. 使用 `--quit` 退出旧实例；2. 重启系统后再试。 | /logs/error.log |

