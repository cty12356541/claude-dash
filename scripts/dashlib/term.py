"""终端输入 shim:Unix(termios+select)与 Windows(msvcrt)统一接口。

watch 模式需要 cbreak(按键即达,不等 ⏎)、带超时的输入就绪探测、字符级读
(含 SGR 鼠标序列)。Windows 无 termios,改用 msvcrt(kbhit+getwch),并对经典
conhost 尽力开启 VT 处理(Windows Terminal 默认支持,失败静默)。两个实现
共享同一最小面:enter / exit / wait / read。
"""
from __future__ import annotations

import sys
import time


class UnixTerm:
    def __init__(self, stdin):
        self._in = stdin
        self._old = None

    def enter(self):
        import termios
        import tty
        self._old = termios.tcgetattr(self._in.fileno())
        # canonical 模式下按键要等 ⏎ 才送达,且 f 后 readline 会吞残留换行
        tty.setcbreak(self._in.fileno())

    def exit(self):
        if self._old is not None:
            import termios
            termios.tcsetattr(self._in.fileno(), termios.TCSADRAIN, self._old)
            self._old = None

    def wait(self, timeout: float) -> bool:
        import select
        return bool(select.select([self._in], [], [], timeout)[0])

    def read(self, n: int) -> str:
        import os
        return os.read(self._in.fileno(), n).decode("utf-8", "replace")


class WindowsTerm:
    def __init__(self, stdin):
        self._in = stdin

    def enter(self):
        self._enable_vt()

    def exit(self):
        pass

    @staticmethod
    def _enable_vt():
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING(0x0004);无控制台/已支持时静默。
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            handle = k32.GetStdHandle(-11)   # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if k32.GetConsoleMode(handle, ctypes.byref(mode)):
                k32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            pass

    def wait(self, timeout: float) -> bool:
        import msvcrt
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                return True
            time.sleep(0.01)
        return False

    def read(self, n: int) -> str:
        import msvcrt
        buf: list[str] = []
        while len(buf) < n and msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):   # 特殊键前缀:吞随后的扫描码,不当输入
                if msvcrt.kbhit():
                    msvcrt.getwch()
                continue
            buf.append(ch)
        return "".join(buf)


def make_term(stdin) -> UnixTerm | WindowsTerm:
    """按平台选择实现;UnixTerm 仅在此处(非模块级)import termios。"""
    return WindowsTerm(stdin) if sys.platform == "win32" else UnixTerm(stdin)
