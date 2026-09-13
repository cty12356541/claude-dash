"""跨平台"用系统默认程序打开文件/URL"。

Windows 的 os.startfile 是原生路径;此前 dash 用 Unix 的 open/xdg-open,
在 Windows 上 FileNotFoundError(WinError 2)。失败(OSError)静默——快照
已落盘,打开失败不应让命令失败。
"""
from __future__ import annotations

import os
import platform
import subprocess


def open_path(path) -> None:
    s = str(path)
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(s)                      # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.run(["open", s], check=False)
        else:
            subprocess.run(["xdg-open", s], check=False)
    except OSError:
        pass
