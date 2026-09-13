"""终端字符 DAG:拓扑分层布局 + box-drawing 连接符。真正的"图",不是清单。

分层 = 最长路径层号(同车道序 + 屏障边);环保险:迭代上限后剩余节点
并入末层并列,不崩溃(spec §9 同精神:结构缺陷降级不白屏)。
"""
from __future__ import annotations

import re
from typing import Dict, List

from .model import Model, Task
from .render_panel import C, MARK

_BARRIER_RE = re.compile(r"屏障\s*\S+\s*:\s*(\S+)\s*→\s*(.+)")
_CELL_LABEL = 16          # 节点单元格内 label 截断宽
_CELL_GAP = 2             # 同层节点列间距


def _edges(model: Model) -> Dict[str, set]:
    """child_id -> {parent_id}。同车道按 id 序为链;屏障串解析 after→unlocks。"""
    edges: Dict[str, set] = {}
    lanes: Dict[str, List[Task]] = {}
    for t in model.tasks:
        lanes.setdefault(t.lane, []).append(t)
    for members in lanes.values():                 # 同车道 id 序 = 依赖链
        members = sorted(members, key=lambda t: t.id)
        for a, b in zip(members, members[1:]):
            edges.setdefault(b.id, set()).add(a.id)
    ids = {t.id for t in model.tasks}
    for b in model.barriers:
        m = _BARRIER_RE.match(b.strip())
        if not m:
            continue
        for parent in m.group(1).split("+"):
            for child in m.group(2).split():
                if parent in ids and child in ids:
                    edges.setdefault(child, set()).add(parent)
    return edges


def compute_layers(model: Model) -> List[List[Task]]:
    """最长路径分层;环内节点(迭代上限未解析)并入末层,保证全量输出。"""
    by_id = {t.id: t for t in model.tasks}
    edges = _edges(model)
    layer: Dict[str, int] = {}
    for _ in range(len(model.tasks) + 1):
        progressed = False
        for tid in by_id:
            if tid in layer:
                continue
            pend = [p for p in edges.get(tid, ()) if p in by_id and p not in layer]
            if not pend:
                layer[tid] = 0 if not edges.get(tid) else 1 + max(
                    layer[p] for p in edges[tid] if p in layer)
                progressed = True
        if not progressed:
            break
    last = max(layer.values()) + 1 if layer else 0
    for tid in by_id:                              # 环残余 → 末层并列
        layer.setdefault(tid, last)
    layers: List[List[Task]] = [[] for _ in range(last + 1)]
    for tid, lv in layer.items():
        layers[lv].append(by_id[tid])
    return [l for l in layers if l] or [[t] for t in model.tasks] or [[]]


def _cell(t: Task) -> str:
    label = t.label[:_CELL_LABEL]
    return f"{C[t.state]}{MARK[t.state]} {t.id} {label}{C['end']}"


def _plain(cell: str) -> int:
    return len(re.sub(r"\033\[[0-9;]*m", "", cell))


def render_graph(model: Model, now_iso: str, width: int = 72) -> str:
    layers = compute_layers(model)
    edges = _edges(model)
    rows = [[_cell(t) for t in layer] for layer in layers]
    xs: List[List[int]] = []                        # 每层每节点的起始列
    for row in rows:
        col = 0
        pos = []
        for cell in row:
            pos.append(col)
            col += _plain(cell) + _CELL_GAP
        xs.append(pos)
    out = [f"{model.project} · DAG", "─" * width]
    next_ids = [{t.id for t in layers[i + 1]} for i in range(len(layers) - 1)]
    for i, row in enumerate(rows):
        line = ""
        for cell, x in zip(row, xs[i]):
            line += " " * (x - _plain(line[:0]) - len(re.sub(r"\033\[[0-9;]*m", "", line))) + cell \
                if line else cell
        out.append(line.rstrip())
        if i + 1 == len(rows):
            break
        gap1 = []                                   # 垂直段:父节点列
        gap2 = []                                   # 水平段 + ▼ 汇入
        parents_in_row = {t.id: xs[i][j] for j, t in enumerate(layers[i])}
        for cid in next_ids[i]:
            for p in edges.get(cid, ()):  # noqa: SIM118
                if p in parents_in_row:
                    gap1.append(parents_in_row[p])
                    gap2.append(("h", parents_in_row[p]))
        for cid in next_ids[i]:
            j = next(k for k, t in enumerate(layers[i + 1]) if t.id == cid)
            gap2.append(("v", xs[i + 1][j]))
        l1 = [" "] * (width + 8)
        for x in gap1:
            l1[x + 1] = "│"
        out.append("".join(l1).rstrip())
        l2 = [" "] * (width + 8)
        for kind, x in gap2:
            if kind == "v":
                l2[x + 1] = "▼" if l2[x + 1] == " " else "▼"
        horiz = [(x, y) for kind, x in [g for g in gap2 if g[0] == "h"] for y in
                 [next((xs[i + 1][j] for j, t in enumerate(layers[i + 1])
                        if t.id == cid), x) for cid in
                  [t.id for t in layers[i + 1] if any(p in parents_in_row for p in edges.get(t.id, ()))]]]
        for x1, x2 in horiz:
            for x in range(min(x1, x2) + 1, max(x1, x2) + 2):
                if l2[x] == " ":
                    l2[x] = "─"
        out.append("".join(l2).rstrip())
    out.append("─" * width)
    return "\n".join(out)


def next_view(view: str, key: str) -> str:
    """watch 视图切换:g 在 panel/graph 间翻转,其余键不改变视图。"""
    if key == "g":
        return "graph" if view == "panel" else "panel"
    return view
