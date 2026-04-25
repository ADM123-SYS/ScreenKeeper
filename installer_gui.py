#!/usr/bin/env python3
import os
import shutil
import subprocess
import tkinter as tk
from tkinter import messagebox


APP_TITLE = "Screen Guardian 自动化安装界面"
INSTALL_DIR = "/root/sll"
GUARDIAN_PATH = f"{INSTALL_DIR}/screen_guardian.sh"
SERVICE_PATH = "/etc/systemd/system/screen-guardian.service"


DEFAULTS = {
    "check_interval": "30",
    "napcat_name": "napcat",
    "napcat_dir": "/root/sll/bot/napcat",
    "napcat_cmd": "bash ./launcher.sh",
    "onebot_name": "onebot",
    "onebot_dir": "/root/sll/bot/onbot",
    "onebot_cmd": "nb run",
    "gscore_name": "gscore",
    "gscore_dir": "/root/sll/bot/gsuid_core",
    "gscore_cmd": "uv run core",
    "extra_sessions": "",
}


def build_guardian_script(cfg):
    return f"""#!/usr/bin/env bash
set -u

CHECK_INTERVAL={cfg["check_interval"]}
LOG_FILE="/var/log/screen-guardian.log"

NAPCAT_SESSION_NAME="{cfg["napcat_name"]}"
NAPCAT_WORKDIR="{cfg["napcat_dir"]}"
NAPCAT_START_CMD="{cfg["napcat_cmd"]}"

ONEBOT_SESSION_NAME="{cfg["onebot_name"]}"
ONEBOT_WORKDIR="{cfg["onebot_dir"]}"
ONEBOT_START_CMD="{cfg["onebot_cmd"]}"

GSCORE_SESSION_NAME="{cfg["gscore_name"]}"
GSCORE_WORKDIR="{cfg["gscore_dir"]}"
GSCORE_START_CMD="{cfg["gscore_cmd"]}"

EXTRA_SESSIONS="{cfg["extra_sessions"]}"

timestamp() {{
  date "+%Y-%m-%d %H:%M:%S"
}}

log() {{
  local level="$1"
  shift
  local msg="$*"
  local line
  line="$(timestamp) [$level] $msg"
  echo "$line"
  if [[ -n "${{LOG_FILE}}" ]]; then
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
    echo "$line" >> "$LOG_FILE"
  fi
}}

trim() {{
  local s="$*"
  s="${{s#"${{s%%[![:space:]]*}}"}}"
  s="${{s%"${{s##*[![:space:]]}}"}}"
  printf "%s" "$s"
}}

session_exists() {{
  local name="$1"
  screen -ls 2>/dev/null | awk -v n="$name" '
    /^[[:space:]]*[0-9]+\\./ {{
      split($1, a, ".")
      if (a[2] == n) found=1
    }}
    END {{ exit(found ? 0 : 1) }}
  '
}}

cleanup_dead_sockets() {{
  screen -wipe >/dev/null 2>&1 || true
}}

start_session() {{
  local name="$1"
  local workdir="$2"
  local cmd="$3"
  local full_cmd
  cleanup_dead_sockets
  if session_exists "$name"; then
    log "INFO" "会话已存在: $name"
    return 0
  fi
  full_cmd="cd \"$workdir\" && $cmd"
  # 先创建命名会话，再向会话发送启动命令
  if ! screen -dmS "$name"; then
    log "ERROR" "会话创建失败: $name"
    return 1
  fi
  sleep 1
  if screen -S "$name" -X stuff "$full_cmd"$'\\n'; then
    log "INFO" "会话已创建并发送命令: $name | $full_cmd"
  else
    log "ERROR" "启动失败: $name | $full_cmd"
    return 1
  fi
}}

restart_session() {{
  local name="$1"
  local workdir="$2"
  local cmd="$3"
  log "WARN" "检测异常，重建会话: $name"
  screen -S "$name" -X quit >/dev/null 2>&1 || true
  sleep 1
  start_session "$name" "$workdir" "$cmd"
}}

validate_config() {{
  if ! command -v screen >/dev/null 2>&1; then
    log "ERROR" "缺少 screen，请先安装"
    exit 1
  fi
  if [[ -z "$(trim "$NAPCAT_WORKDIR")" || -z "$(trim "$ONEBOT_WORKDIR")" || -z "$(trim "$GSCORE_WORKDIR")" ]]; then
    log "ERROR" "核心会话工作目录不能为空"
    exit 1
  fi
  if [[ -z "$(trim "$NAPCAT_START_CMD")" || -z "$(trim "$ONEBOT_START_CMD")" || -z "$(trim "$GSCORE_START_CMD")" ]]; then
    log "ERROR" "核心会话启动命令不能为空"
    exit 1
  fi
}}

build_sessions() {{
  local core
  core="${{NAPCAT_SESSION_NAME}}|${{NAPCAT_WORKDIR}}|${{NAPCAT_START_CMD}};${{ONEBOT_SESSION_NAME}}|${{ONEBOT_WORKDIR}}|${{ONEBOT_START_CMD}};${{GSCORE_SESSION_NAME}}|${{GSCORE_WORKDIR}}|${{GSCORE_START_CMD}}"
  if [[ -n "$(trim "$EXTRA_SESSIONS")" ]]; then
    printf "%s;%s" "$core" "$EXTRA_SESSIONS"
  else
    printf "%s" "$core"
  fi
}}

for_each_session() {{
  local sessions="$1"
  local handler="$2"
  IFS=';' read -r -a entries <<< "$sessions"
  for raw in "${{entries[@]}}"; do
    local entry
    entry="$(trim "$raw")"
    [[ -z "$entry" ]] && continue
    local name="${{entry%%|*}}"
    local rest="${{entry#*|}}"
    local workdir="${{rest%%|*}}"
    local cmd="${{rest#*|}}"
    name="$(trim "$name")"
    workdir="$(trim "$workdir")"
    cmd="$(trim "$cmd")"
    if [[ -z "$name" || -z "$workdir" || -z "$cmd" || "$entry" != *"|"* ]]; then
      log "ERROR" "配置格式错误(应为 会话名|目录|命令): $entry"
      continue
    fi
    "$handler" "$name" "$workdir" "$cmd"
  done
}}

init_handler() {{
  start_session "$1" "$2" "$3"
}}

watch_handler() {{
  local name="$1"
  local workdir="$2"
  local cmd="$3"
  if session_exists "$name"; then
    log "INFO" "巡检正常: $name"
  else
    restart_session "$name" "$workdir" "$cmd"
  fi
}}

main() {{
  validate_config
  log "INFO" "守护进程启动，间隔=${{CHECK_INTERVAL}}s"
  while true; do
    sessions="$(build_sessions)"
    for_each_session "$sessions" init_handler
    sleep "$CHECK_INTERVAL"
    for_each_session "$sessions" watch_handler
  done
}}

main "$@"
"""


def build_service_file():
    return f"""[Unit]
Description=Screen Session Guardian
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={INSTALL_DIR}
ExecStart={GUARDIAN_PATH}
Restart=always
RestartSec=5
StandardOutput=append:/var/log/screen-guardian.log
StandardError=append:/var/log/screen-guardian.log

[Install]
WantedBy=multi-user.target
"""


class InstallerUI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("860x720")
        self.root.configure(bg="#0f172a")

        self.vars = {k: tk.StringVar(value=v) for k, v in DEFAULTS.items()}
        self._build_layout()

    def _build_layout(self):
        header = tk.Frame(self.root, bg="#0f172a")
        header.pack(fill="x", padx=14, pady=(12, 8))

        canvas = tk.Canvas(header, width=120, height=80, bg="#0f172a", highlightthickness=0)
        canvas.pack(side="left")
        canvas.create_oval(14, 14, 66, 66, fill="#22c55e", outline="")
        canvas.create_rectangle(74, 22, 112, 58, fill="#38bdf8", outline="")
        canvas.create_text(40, 40, text="S", fill="#0f172a", font=("Segoe UI", 20, "bold"))
        canvas.create_text(93, 40, text="G", fill="#0f172a", font=("Segoe UI", 20, "bold"))

        title_box = tk.Frame(header, bg="#0f172a")
        title_box.pack(side="left", padx=10)
        tk.Label(
            title_box,
            text="Screen Guardian 一键安装",
            bg="#0f172a",
            fg="#e2e8f0",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="图形化配置 + 自动部署到 /root/sll + systemd 开机自启",
            bg="#0f172a",
            fg="#94a3b8",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 0))

        form = tk.Frame(self.root, bg="#111827", bd=1, relief="solid")
        form.pack(fill="x", padx=14, pady=8)

        self._row(form, "巡检间隔(秒)", "check_interval")
        self._row(form, "napcat 会话名", "napcat_name")
        self._row(form, "napcat 工作目录", "napcat_dir")
        self._row(form, "napcat 启动命令", "napcat_cmd")
        self._row(form, "onebot 会话名", "onebot_name")
        self._row(form, "onebot 工作目录", "onebot_dir")
        self._row(form, "onebot 启动命令", "onebot_cmd")
        self._row(form, "gscore 会话名", "gscore_name")
        self._row(form, "gscore 工作目录", "gscore_dir")
        self._row(form, "gscore 启动命令", "gscore_cmd")
        self._row(form, "扩展会话(可空)", "extra_sessions")

        btns = tk.Frame(self.root, bg="#0f172a")
        btns.pack(fill="x", padx=14, pady=8)
        tk.Button(
            btns,
            text="一键安装/修复",
            command=self.install,
            bg="#22c55e",
            fg="#0f172a",
            font=("Segoe UI", 11, "bold"),
            width=16,
        ).pack(side="left")
        tk.Button(
            btns,
            text="仅生成预览",
            command=self.preview,
            bg="#38bdf8",
            fg="#0f172a",
            font=("Segoe UI", 11, "bold"),
            width=12,
        ).pack(side="left", padx=10)

        self.log_text = tk.Text(self.root, height=18, bg="#020617", fg="#cbd5e1", insertbackground="#cbd5e1")
        self.log_text.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        self._log("等待操作。请在 Linux 服务器上以 root 运行本安装界面。")

    def _row(self, parent, label, key):
        row = tk.Frame(parent, bg="#111827")
        row.pack(fill="x", padx=10, pady=6)
        tk.Label(row, text=label, width=18, anchor="w", bg="#111827", fg="#e5e7eb").pack(side="left")
        tk.Entry(row, textvariable=self.vars[key], bg="#1f2937", fg="#f8fafc", insertbackground="#f8fafc").pack(
            side="left", fill="x", expand=True
        )

    def _log(self, text):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def _cfg(self):
        return {k: v.get().strip() for k, v in self.vars.items()}

    def _ensure_install_dir(self):
        if not os.path.isdir(INSTALL_DIR):
            self._log(f"目录不存在，自动创建: {INSTALL_DIR}")
            os.makedirs(INSTALL_DIR, exist_ok=True)
        else:
            self._log(f"目录已存在: {INSTALL_DIR}")

    def _ensure_screen_global(self):
        screen_path = shutil.which("screen")
        if screen_path:
            self._log(f"检测到全局 screen 命令: {screen_path}")
            return
        self._log("未检测到全局 screen，开始安装...")
        self._run(["apt-get", "update", "-y"])
        self._run(["apt-get", "install", "-y", "screen"])
        screen_path = shutil.which("screen")
        if not screen_path:
            raise RuntimeError("screen 安装后仍未找到全局命令，请手动检查 PATH。")
        self._log(f"全局 screen 命令已可用: {screen_path}")

    def _run(self, cmd):
        self._log(f"$ {' '.join(cmd)}")
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        if proc.stdout:
            self._log(proc.stdout.rstrip())
        if proc.returncode != 0:
            raise RuntimeError(f"命令执行失败: {' '.join(cmd)}")

    def preview(self):
        cfg = self._cfg()
        self._log("==== screen_guardian.sh 预览 ====")
        self._log(build_guardian_script(cfg))
        self._log("==== screen-guardian.service 预览 ====")
        self._log(build_service_file())

    def install(self):
        if os.geteuid() != 0:
            messagebox.showerror("权限不足", "请使用 root 运行本程序，例如：sudo -E python3 installer_gui.py")
            return

        cfg = self._cfg()
        if not cfg["check_interval"].isdigit():
            messagebox.showerror("参数错误", "巡检间隔必须为数字。")
            return

        try:
            self._log("开始环境检测...")
            self._ensure_screen_global()
            self._ensure_install_dir()

            self._log("写入守护脚本与服务文件...")
            with open(GUARDIAN_PATH, "w", encoding="utf-8", newline="\n") as f:
                f.write(build_guardian_script(cfg))
            os.chmod(GUARDIAN_PATH, 0o755)

            with open(SERVICE_PATH, "w", encoding="utf-8", newline="\n") as f:
                f.write(build_service_file())

            self._run(["systemctl", "daemon-reload"])
            self._run(["systemctl", "enable", "screen-guardian.service"])
            self._run(["systemctl", "restart", "screen-guardian.service"])
            self._run(["systemctl", "status", "screen-guardian.service", "--no-pager"])
            self._run(["screen", "-ls"])

            messagebox.showinfo("完成", "安装成功，守护服务已启动。")
            self._log("安装完成。查看日志: journalctl -u screen-guardian.service -f")
        except Exception as e:
            messagebox.showerror("安装失败", str(e))
            self._log(f"安装失败: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    InstallerUI(root)
    root.mainloop()
