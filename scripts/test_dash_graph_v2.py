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


def _at(rows, line: int, col: int) -> str:
    """按显示列取字符(宽字符占 2 列:命中其首列返回该字符,次列视作空白)。"""
    import unicodedata
    x = 0
    for ch in rows[line]:
        w = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if x <= col < x + w:
            return ch if col == x else " "
        x += w
    return " "


def _cell(model, tid):
    for cells in layout_layers(model)[1]:
        for c in cells:
            if c.id == tid:
                return c
    return None


class TestWideChars(unittest.TestCase):
    def test_cjk_label_fits_box(self):
        """东亚宽字符占 2 列:框宽必须按显示宽算,右框缘不被顶穿。"""
        m = Model(project="t", tasks=[
            Task(id="T1", label="中文标签宽字符测试", state="done", lane="A"),
        ], barriers=[])
        rows = _plain(render_graph(m, NOW))
        c = _cell(m, "T1")
        self.assertEqual(_at(rows, c.line, c.x), "│")
        self.assertEqual(_at(rows, c.line, c.x + c.width - 1), "│")   # 右框缘完好
        # 框宽 = 显示宽 + 4(内边距 2 + 边框 2)
        from dashlib.render_graph import _dw, _cell_text
        self.assertEqual(c.width, _dw(_cell_text(m.tasks[0])) + 4)


class TestBoxFrames(unittest.TestCase):
    def test_every_task_has_framed_box(self):
        m = _w25_like()
        rows = _plain(render_graph(m, NOW))
        for tid in ("T1", "T2", "T3", "T4"):
            c = _cell(m, tid)
            top, txt, bot = rows[c.line - 1], rows[c.line], rows[c.line + 1]
            self.assertEqual(_at([top], 0, c.x), "┌", f"{tid} 框顶左")
            self.assertEqual(top[c.x + c.width - 1], "┐", f"{tid} 框顶右")
            self.assertEqual(bot[c.x], "└", f"{tid} 框底左")
            self.assertEqual(bot[c.x + c.width - 1], "┘", f"{tid} 框底右")
            self.assertIn(f"✓ {tid} ", txt)

    def test_parent_bottom_has_out_stub(self):
        m = _w25_like()
        rows = _plain(render_graph(m, NOW))
        c1 = _cell(m, "T1")                      # T1 有出边(T1→T2)
        self.assertEqual(_at(rows, c1.line + 1, c1.center), "┬")
        c4 = _cell(m, "T4")                      # T4 无出边:框底纯 ─
        self.assertEqual(_at(rows, c4.line + 1, c4.center), "─")


class TestEdgeRouting(unittest.TestCase):
    UP_STROKES = ("└", "┘", "┴", "│")            # 接合符须含上笔承接父竖线

    def test_adjacent_edge_joins_parent_drop(self):
        m = _w25_like()
        rows = _plain(render_graph(m, NOW))
        c1, c2 = _cell(m, "T1"), _cell(m, "T2")
        self.assertEqual(_at(rows, c1.line + 2, c1.center), "│")   # 父框下竖线
        self.assertIn(_at(rows, c2.line - 2, c1.center), self.UP_STROKES)  # 汇流行接合
        self.assertEqual(_at(rows, c2.line - 1, c2.center), "▼")   # 箭头嵌框顶

    def test_cross_layer_edge_is_routed(self):
        """核心:T3(层0)→T4(层2) 的跨层汇入边必须画出来。"""
        m = _w25_like()
        rows = _plain(render_graph(m, NOW))
        c3, c4 = _cell(m, "T3"), _cell(m, "T4")
        self.assertGreater(c4.line, c3.line + 5)               # 确为跨层
        self.assertEqual(_at(rows, c3.line + 1, c3.center), "┬")    # T3 出线桩
        # 竖穿:T2 文字行(中间层)在 T3 中心列上是 │(该列不在任何框内)
        c2 = _cell(m, "T2")
        self.assertEqual(_at(rows, c2.line, c3.center), "│")
        # 入线:汇流行上 T3 中心处有含上笔的接合符,水平段连通到 T4 中心列
        z = c4.line - 2
        self.assertIn(_at(rows, z, c3.center), self.UP_STROKES)
        lo, hi = sorted((c3.center, c4.center))
        self.assertTrue(all(rows[z][x] in "─└┘┴│" for x in range(lo, hi + 1)))
        self.assertEqual(_at(rows, c4.line - 1, c4.center), "▼")    # 箭头嵌 T4 框顶

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
