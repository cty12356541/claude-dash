"""Windows 兼容修复的钉死测试(2026-09-13 本地试跑发现)。

覆盖四项:
1. GBK stdio(PYTHONIOENCODING=gbk 模拟中文 Windows 默认)下 oneline 不崩
2. 打开器平台分支(Windows 用 os.startfile)
3. 终端 shim 在 Windows 可导入且无输入时 wait() 快速返回 False
4. watch --once 在管道 stdin + GBK 环境下渲染一帧退出(不 import termios)
5. 台账解析 complete 优先于更早的 fix-round 历史行
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DASH = str(Path(__file__).resolve().parent / "dash")


def _run(args, cwd, extra_env=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, DASH, *args], cwd=cwd,
                          capture_output=True, timeout=60, env=env)


class TestUtf8Stdio(unittest.TestCase):
    def test_oneline_survives_gbk_stdio(self):
        with tempfile.TemporaryDirectory() as d:
            r = _run(["oneline"], d, {"PYTHONIOENCODING": "gbk"})
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
            self.assertNotIn(b"UnicodeError", r.stderr)
            self.assertIn(b"[dash]", r.stdout)


class TestOpener(unittest.TestCase):
    def test_open_path_uses_startfile_on_windows(self):
        from dashlib.opener import open_path
        if sys.platform != "win32":
            self.skipTest("windows-only")
        calls = []
        import os as _os
        import dashlib.opener as op
        orig = getattr(_os, "startfile", None)
        if orig is not None:
            op.os.startfile = lambda p: calls.append(p)
        try:
            open_path(Path("Z:/nonexistent-snapshot.html"))
        finally:
            if orig is not None:
                op.os.startfile = orig
        self.assertEqual(calls, [str(Path("Z:/nonexistent-snapshot.html"))])


class TestTermShim(unittest.TestCase):
    def test_make_term_importable_and_idle_wait_false(self):
        from dashlib.term import make_term
        t = make_term(sys.stdin)
        self.assertFalse(t.wait(0.05))   # 无输入:快速返回 False,不抛、不挂

    def test_windows_term_needs_no_termios(self):
        if sys.platform != "win32":
            self.skipTest("windows-only")
        import dashlib.term as term_mod
        self.assertNotIn("termios", vars(term_mod))   # 模块级零 Unix 依赖


class TestWatchOnce(unittest.TestCase):
    def test_watch_once_piped_gbk_env(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, DASH, "watch", "--once"], cwd=d,
                               stdin=subprocess.DEVNULL, capture_output=True,
                               timeout=60,
                               env={**os.environ, "PYTHONIOENCODING": "gbk"})
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
            self.assertNotIn(b"termios", r.stderr)
            self.assertIn(b"[dash watch]", r.stdout)


class TestResolverPrecedence(unittest.TestCase):
    def test_complete_beats_earlier_fix_round_history(self):
        from dashlib.adapters import _resolve
        ledger = ("Task 1: fix round 1/5 (3/3 addressed; aaa..bbb)\n"
                  "Task 1: complete (commits ccc..ddd, review clean)\n")
        state, _note = _resolve(ledger, 1)
        self.assertEqual(state, "done")

    def test_active_word_without_complete_stays_active(self):
        from dashlib.adapters import _resolve
        state, _ = _resolve("Task 2: dispatched to lane-b\n", 2)
        self.assertEqual(state, "active")


if __name__ == "__main__":
    unittest.main()
