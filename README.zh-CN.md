# Muse Bridge — 连接 Muse、Codex 和 Claude Code 的 CLI

让 muse.ai 个人助手向你的 Mac 提交项目任务，本机调用 Codex 或 Claude Code，再把结果传回同一个 Muse 聊天。也支持读取 Muse 数据和只读 MCP。

这是独立编写的开源工具，面向 macOS / Python 3.11+。不是官方 Muse Code CLI，也不属于 Meta、OpenAI 或 Anthropic。

## 安装和登录

```bash
uv tool install https://github.com/buzhidaosm/muse-cli-bridge/releases/download/v0.3.0/muse_bridge_cli-0.3.0-py3-none-any.whl
muse-bridge doctor
muse-bridge login
muse-bridge identity
```

登录在独立临时 Chrome 窗口中由你完成，验证后保存在 macOS 钥匙串，不读取原有浏览器配置。Mac 需要安装 Google Chrome。

## 把一个项目交给 Muse

```bash
muse-bridge bridge init --project /你的项目绝对路径
muse-bridge bridge start --background
muse-bridge bridge notify
```

在收到说明的同一个 Muse 聊天里说：

> 用 Codex 只读审阅 `/我的项目绝对路径`，通过 Muse Bridge 交给本机执行，等返回结果后再总结。

允许修改，需要明确启用：

```bash
muse-bridge bridge stop
muse-bridge bridge init --project /你的项目绝对路径 --allow-write
muse-bridge bridge start --background
muse-bridge bridge notify
```

可以重复 `--project` 授权多个项目；`--all-projects` 是单独的全项目选项，不是默认权限。Mac 保持开机联网即可，不需要开放公共端口。

## 常用命令

```bash
muse-bridge history --limit 5
muse-bridge threads
muse-bridge goals
muse-bridge ideas
muse-bridge feed --limit 10
muse-bridge send '你好' --allow-write
muse-bridge mcp
muse-bridge bridge status
muse-bridge bridge job TASK_ID
muse-bridge bridge stop
```

任务 id 去重、持久化状态、进程组超时和不确定投递状态均已实现。重启不自动重跑中断任务。完整流程已用真实账号验证，也验证了两个助手修改独立测试项目的实际内容。

## 真实边界

文件写入受到 macOS OS 沙箱限制，但不是完整的读取或网络隔离。它启动新的 CLI 任务，不会向既有桌面聊天插入消息，也不会点击屏幕。内部 Muse 接口未经版本化，随时可能改变；只支持标准 NON_TEE / 旧式标准握手。

[英文首页](README.md) · [任务桥说明](TASK_BRIDGE.md) · [验证记录](VALIDATION.md) · [权限边界](SECURITY.md) · [协议来源](PROVENANCE.md)
