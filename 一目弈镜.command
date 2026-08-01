#!/bin/bash
# 双击启动「一目弈镜 · 对局复盘」网页版。
# 会在本机起一个只监听 127.0.0.1 的小服务器，并自动打开浏览器；
# 报告本身和「管理 / 分析」面板在同一个页面里。
# 第一次双击若被 macOS 拦截：右键 → 打开，或在「系统设置 → 隐私与安全性」里点「仍要打开」。
# 用完关闭这个终端窗口即可停止服务。

cd "$(dirname "$0")" || exit 1

# 优先用 python3；找不到就提示
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  echo "未找到 python3。请先安装 Python 3（python.org 或 Xcode 命令行工具）。"
  echo "按回车关闭…"; read -r _; exit 1
fi

echo "启动一目弈镜 · 网页版… (使用 $PY)"
"$PY" "go_review/web_app.py"
code=$?
if [ $code -ne 0 ]; then
  echo ""
  echo "程序退出，错误码 $code。"
  echo "若端口被占用，可改端口：python3 go_review/web_app.py --port 9000"
  echo "按回车关闭…"; read -r _
fi
