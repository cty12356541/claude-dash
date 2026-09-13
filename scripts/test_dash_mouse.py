#!/usr/bin/env python3
"""dash watch 鼠标支持:SGR 序列解析 + 节点命中测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dashlib.model import Model, Task  # noqa: E402
from dashlib.render_graph import hit_test, layout_layers, parse_mouse  # noqa: E402


def _model():
    return Model(project="t", tasks=[
        Task(id="T1", label="骨架", state="done", lane="A"),
        Task(id="T2", label="适配", state="active", lane="A"),
        Task(id="T3", label="渲染", state="pending", lane="B"),
    ], barriers=["屏障 1: T1 → T3"])


def test_parse_mouse_sgr_click():
    assert parse_mouse("\x1b[<0;12;5M") == (0, 12, 5)
    assert parse_mouse("\x1b[<0;40;9M") == (0, 40, 9)


def test_parse_mouse_rejects_non_mouse():
    assert parse_mouse("f") is None
    assert parse_mouse("\x1b[A") is None            # 方向键,非鼠标
    assert parse_mouse("\x1b[<64;1;1M") is None      # 滚轮/其他按钮,非左键单击


def test_layout_exposes_node_cells():
    layers, rows = layout_layers(_model())
    cells = [c for row in rows for c in row]
    assert {c.id for c in cells} == {"T1", "T2", "T3"}
    first = rows[0][0]
    assert first.x >= 0 and first.width > 3 and first.line >= 0


def test_hit_test_returns_task_at_click():
    m = _model()
    layers, rows = layout_layers(m)
    cell = rows[0][0]                                # T1 的单元格
    assert hit_test(m, cell.x + 2, cell.line + 1) == cell.id   # +1:终端 1 基
    assert hit_test(m, 0, 1) is None                 # 头部行,未命中


def test_hit_test_second_row():
    m = _model()
    layers, rows = layout_layers(m)
    cell = rows[1][0] if rows[1][0].line < rows[1][-1].line else rows[1][-1]
    assert hit_test(m, cell.x + 1, cell.line + 1) == cell.id


def test_parse_events_chunk_semantics():
    """os.read 整块语义:一次返回的混合块要能拆出鼠标事件+普通键。"""
    from dashlib.render_graph import parse_events
    ev, pend = parse_events("\x1b[<0;4;3M")
    assert ev == [("mouse", 4, 3)] and pend == ""
    ev, pend = parse_events("gq")
    assert ev == [("key", "g"), ("key", "q")] and pend == ""
    ev, pend = parse_events("\x1b[<0;4;3Mg")     # 鼠标+键同块
    assert ev == [("mouse", 4, 3), ("key", "g")] and pend == ""
    ev, pend = parse_events("\x1b[<0;4;")        # 半截序列:挂起等下一块
    assert ev == [] and pend == "\x1b[<0;4;"
    ev2, pend2 = parse_events("3Mf", pend)        # 续上
    assert ev2 == [("mouse", 4, 3), ("key", "f")] and pend2 == ""


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted({k: v for k, v in globals().items() if k.startswith("test_")}.items()):
        try:
            fn()
            print(f"{name} OK")
        except AssertionError as e:
            fails += 1
            print(f"{name} FAIL: {e}")
        except Exception as e:  # noqa: BLE001
            fails += 1
            print(f"{name} ERROR: {type(e).__name__}: {e}")
    sys.exit(1 if fails else 0)
