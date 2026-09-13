"""框化节点 DAG 渲染 v2 的钉死测试(unittest 收集,pytest 兼容)。

设计承诺(README"节点+边真图"/render_graph 文档串):
1. 节点带单线框(┌─┐│└┘),出线桩 ┬、入线箭头 ▼ 嵌框顶
2. 任意跨层边都路由:竖穿 + └─┐/┌─┘ 角折——T3(层0)→T4(层2) 必须可见
3. hit_test 命中区覆盖框三行
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dashlib.model import Model, Task  # noqa: E402
from dashlib.render_graph import (  # noqa: E402
    layout_layers, render_graph, hit_test)

NOW = "2026-09-13T21:00:00+08:00"
ANSI = re.compile(r"\033\[[0-9;]*m")


def _w25_like():
    """T1→T2→T4 链 + T3 并行跨层汇入 T4(屏障 T2+T3→T4)——复刻 W25 形态。"""
    return Model(project="w25", tasks=[
        Task(id="T1", label="fiber join 即回收", state="done", lane="A"),
        Task(id="T2", label="scope by_id 索引", state="done", lane="B"),
        Task(id="T3", label="orphan 上界", state="done", lane="C"),
        Task(id="T4", label="集成收尾", state="done", lane="D"),
    ], barriers=["屏障 B1: T1 → T2", "屏障 B2: T2+T3 → T4"])


def _plain(out: str):
    return [ANSI.sub("", ln) for ln in out.splitlines()]


def _cell(model, tid):
    for cells in layout_layers(model)[1]:
        for c in cells:
            if c.id == tid:
                return c
    return None


class TestBoxFrames(unittest.TestCase):
    def test_every_task_has_framed_box(self):
        m = _w25_like()
        rows = _plain(render_graph(m, NOW))
        for tid in ("T1", "T2", "T3", "T4"):
            c = _cell(m, tid)
            top, txt, bot = rows[c.line - 1], rows[c.line], rows[c.line + 1]
            self.assertEqual(top[c.x], "┌", f"{tid} 框顶左")
            self.assertEqual(top[c.x + c.width - 1], "┐", f"{tid} 框顶右")
            self.assertEqual(bot[c.x], "└", f"{tid} 框底左")
            self.assertEqual(bot[c.x + c.width - 1], "┘", f"{tid} 框底右")
            self.assertIn(f"✓ {tid} ", txt)

    def test_parent_bottom_has_out_stub(self):
        m = _w25_like()
        rows = _plain(render_graph(m, NOW))
        c1 = _cell(m, "T1")                      # T1 有出边(T1→T2)
        self.assertEqual(rows[c1.line + 1][c1.center], "┬")
        c4 = _cell(m, "T4")                      # T4 无出边:框底纯 ─
        self.assertEqual(rows[c4.line + 1][c4.center], "─")


class TestEdgeRouting(unittest.TestCase):
    def test_adjacent_aligned_edge_straight_drop(self):
        m = _w25_like()
        rows = _plain(render_graph(m, NOW))
        c1, c2 = _cell(m, "T1"), _cell(m, "T2")
        self.assertEqual(c2.center, c1.center)   # 同列直落
        self.assertEqual(rows[c1.line + 2][c1.center], "│")   # 竖穿行
        self.assertEqual(rows[c2.line - 2][c1.center], "│")   # 入线行
        self.assertEqual(rows[c2.line - 1][c2.center], "▼")   # 箭头嵌框顶

    def test_cross_layer_edge_is_routed(self):
        """核心:T3(层0)→T4(层2) 的跨层汇入边必须画出来。"""
        m = _w25_like()
        rows = _plain(render_graph(m, NOW))
        c3, c4 = _cell(m, "T3"), _cell(m, "T4")
        self.assertGreater(c4.line, c3.line + 5)               # 确为跨层
        self.assertEqual(rows[c3.line + 1][c3.center], "┬")    # T3 出线桩
        # 竖穿:T2 文字行(中间层)在 T3 中心列上是 │(该列不在任何框内)
        c2 = _cell(m, "T2")
        self.assertEqual(rows[c2.line][c3.center], "│")
        # 入线:折线行从 T3 中心折向 T4 中心
        z = c4.line - 2
        self.assertEqual(rows[z][c3.center], "└" if c3.center < c4.center else "┌")
        self.assertEqual(rows[z][c4.center], "┐" if c3.center < c4.center else "┘")
        self.assertEqual(rows[c4.line - 1][c4.center], "▼")    # 箭头嵌 T4 框顶

    def test_t4_receives_two_arrows(self):
        m = _w25_like()
        rows = _plain(render_graph(m, NOW))
        c4 = _cell(m, "T4")
        self.assertEqual(rows[c4.line - 1].count("▼"), 1)      # 单箭头位(两入边同点)


class TestHitRegion(unittest.TestCase):
    def test_box_three_rows_clickable(self):
        m = _w25_like()
        c = _cell(m, "T2")
        for row in (c.line - 1, c.line, c.line + 1):
            self.assertEqual(hit_test(m, c.x + 2, row + 1), "T2")
        self.assertIsNone(hit_test(m, c.x - 1, c.line + 1))    # 框左一列不命中


class TestOldContractKept(unittest.TestCase):
    def test_previous_loose_assertions_still_hold(self):
        out = render_graph(_w25_like(), NOW)
        self.assertIn("T1", out)
        self.assertIn("▼", out) and self.assertIn("│", out)
        self.assertIn("\033[32m", out)                          # done 绿


if __name__ == "__main__":
    unittest.main()
