#!/usr/bin/env python3
"""dash 真图渲染测试:终端字符图(分层/边/环保险)+ HTML mermaid 嵌入 + CLI。"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dashlib.model import Model, Task  # noqa: E402
from dashlib.render_graph import compute_layers, render_graph, next_view  # noqa: E402
from dashlib.render_html import render_html  # noqa: E402

NOW = "2026-09-13T19:00:00+08:00"


def _model():
    return Model(project="t", tasks=[
        Task(id="T1", label="骨架", state="done", lane="A"),
        Task(id="T2", label="适配", state="active", lane="A"),
        Task(id="T3", label="渲染", state="pending", lane="B"),
    ], barriers=["屏障 1: T1 → T3"])


def test_layers_inlane_sequence():
    layers = compute_layers(_model())
    assert [t.id for t in layers[0]] == ["T1"]
    assert {t.id for t in layers[1]} == {"T2", "T3"}


def test_layers_barrier_edge():
    m = Model(project="t", tasks=[
        Task(id="T1", label="a", state="done", lane="A"),
        Task(id="T2", label="b", state="pending", lane="B"),
    ], barriers=["屏障 1: T1 → T2"])
    layers = compute_layers(m)
    assert layers[0][0].id == "T1" and layers[1][0].id == "T2"


def test_render_graph_has_nodes_and_connectors():
    out = render_graph(_model(), NOW)
    assert "T1" in out and "骨架" in out and "T3" in out
    assert "▼" in out or "│" in out          # 层间连接符
    assert "\033[32m" in out                  # done 绿色


def test_cycle_does_not_crash():
    m = Model(project="t", tasks=[
        Task(id="T1", label="a", state="pending", lane="A"),
        Task(id="T2", label="b", state="pending", lane="A"),
    ], barriers=["屏障 1: T2 → T1"])          # 车道边 T1→T2 + 屏障边 T2→T1 成环
    layers = compute_layers(m)                 # 不抛异常
    assert sum(len(l) for l in layers) == 2


def test_next_view_toggles_on_g():
    assert next_view("panel", "g") == "graph"
    assert next_view("graph", "g") == "panel"
    assert next_view("graph", "x") == "graph"
    assert next_view("panel", "f") == "panel"


def test_html_embeds_mermaid_graph():
    html = render_html(_model(), NOW)
    assert 'class="mermaid"' in html
    assert "flowchart" in html                 # 图语法进页面
    assert "cdn.jsdelivr" in html or "mermaid.min.js" in html


def test_cli_render_graph_subcommand():
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        r = subprocess.run([sys.executable, str(Path(__file__).parent / "dash"),
                            "render", "graph"], cwd=d, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_cli_html_open_writes_snapshot():
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        env = dict(os.environ, DASH_NO_OPEN="1")
        r = subprocess.run([sys.executable, str(Path(__file__).parent / "dash"),
                            "render", "html", "--open"], cwd=d, capture_output=True,
                           text=True, env=env)
        assert r.returncode == 0, r.stderr
        snap = Path(d) / ".dash" / "snapshot.html"
        assert snap.exists()
        assert "mermaid" in snap.read_text(encoding="utf-8")


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
