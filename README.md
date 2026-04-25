# Screen Guardian Installer

一个面向 Linux 服务器的 **Screen 会话自动守护安装器**，提供图形化界面配置，并自动部署为 `systemd` 服务，实现开机自启与异常自动恢复。

> 适用场景：`napcat`、`onebot`、`gscore` 等需要长期运行的多进程/多会话服务。

---

## 功能特性

- 图形化安装界面（Tkinter），可视化配置会话与命令
- 自动安装/检测全局 `screen` 命令
- 自动写入守护脚本到 `/root/sll/screen_guardian.sh`
- 自动写入并启用 `systemd` 服务：`screen-guardian.service`
- 支持多会话并行管理（内置 `napcat` / `onebot` / `gscore`）
- 异常自动恢复：会话不存在时自动重建并重启命令
- 开机自动启动守护程序及全部会话

---

## 工作原理

每个会话使用以下流程启动：

1. 先创建命名会话：`screen -dmS <session_name>`
2. 再向该会话发送命令：
   - `cd "<workdir>" && <start_cmd>`
3. 守护脚本循环巡检会话状态（默认每 30 秒）
4. 会话丢失时自动执行重建

---

## 项目结构

```text
.
├── installer_gui.py    # 图形化安装器（唯一入口）
└── README.md
```

---

## 环境要求

- Linux（推荐 Ubuntu）
- Python 3.8+
- `systemd`
- root 权限（安装阶段需要）
- 图形环境（运行 GUI 需要）

> 若服务器无桌面环境，可先在有 GUI 的环境完成配置，或自行改造为 CLI 安装。

---

## 安装与使用

### 1) 安装 Python Tk（如未安装）

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-tk
```

### 2) 运行安装器

在项目目录下执行：

```bash
sudo -E python3 installer_gui.py
```

### 3) 在界面中配置

为每个会话填写：

- 会话名（如：`napcat`）
- 工作目录（建议绝对路径）
- 启动命令（不要再手写 `screen -S ...`）

点击 **一键安装/修复**，安装器会自动：

- 检测/安装 `screen`
- 生成 `/root/sll/screen_guardian.sh`
- 生成 `/etc/systemd/system/screen-guardian.service`
- `daemon-reload` + `enable` + `restart`

---

## 重启后验证

```bash
# 服务是否运行
systemctl is-active screen-guardian.service

# 查看详细状态
systemctl status screen-guardian.service --no-pager -l

# 查看 Screen 会话
screen -ls

# 查看本次开机日志
journalctl -u screen-guardian.service -b --no-pager
```

成功标准：

- 服务状态为 `active (running)`
- `screen -ls` 中出现目标会话（如 `napcat`、`onebot`、`gscore`）
- 日志无持续 `203/EXEC` / `exit-code` 错误

---

## 常见问题

### 1) `status=203/EXEC`

通常是服务执行目标不可执行（路径错误、权限问题、行尾格式错误）。

建议检查：

- `ExecStart` 路径是否正确
- 脚本是否有执行权限：`chmod +x`
- 脚本是否为 Unix 行尾（LF）

### 2) 会话创建了但程序没起来

通常是工作目录或命令错误。请在服务器上手动验证：

```bash
cd <workdir>
<start_cmd>
```

### 3) 日志命令报错

正确命令是：

```bash
journalctl -u screen-guardian.service -f
```

---

## 安全与建议

- 当前安装目标目录为 `/root/sll`，服务以 `root` 运行
- 建议启动命令中避免再次使用 `sudo`
- 生产环境建议将业务进程降权到专用用户运行（可在后续版本增强）

---

## License

可按你的仓库策略补充（例如 MIT）。
