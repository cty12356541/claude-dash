"""终端字符 DAG:拓扑分层布局 + box-drawing 连接符 + 鼠标命中几何。

分层 = 最长路径层号(同车道序 + 屏障边);环保险:迭代上限后剩余节点
并入末层并列,不崩溃(spec §9 同精神:结构缺陷降级不白屏)。
layout_layers 是几何唯一源:render 画图与 hit_test 点击命中共用同一 Cell 表。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .model import Model, Task
from .render_panel import C, MARK

_BARRIER_RE = re.compile(r"屏障\s*\S+\s*:\s*(\S+)\s*→\s*(.+)")
_MOUSE_RE = re.compile(r"^\x1b\[<(\d+);(\d+);(\d+)M$")
_MOUSE_PREFIX_RE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)M")   # 块级:无尾锚
_CELL_LABEL = 16          # 节点单元格内 label 截断宽
_CELL_GAP = 2             # 同层节点列间距
_HEAD_LINES = 2           # 标题 + 分隔线


@dataclass
class Cell:
    id: str
    label: str
    x: int                  # 起始列(0 基,ANSI 剥离后坐标)
    width: int              # 纯文本宽
    line: int               # 节点所在输出行(0 基)


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


def _cell_text(t: Task) -> str:
    return f"{MARK[t.state]} {t.id} {t.label[:_CELL_LABEL]}"


def layout_layers(model: Model) -> Tuple[List[List[Task]], List[List[Cell]]]:
    """几何唯一源:每层节点的 (x, width, line)。line 计入头部两行与层间两行空档。"""
    layers = compute_layers(model)
    rows: List[List[Cell]] = []
    line = _HEAD_LINES
    for i, layer in enumerate(layers):
        cells, col = [], 0
        for t in layer:
            text = _cell_text(t)
            cells.append(Cell(t.id, t.label, col, len(text), line))
            col += len(text) + _CELL_GAP
        rows.append(cells)
        line += 1 + (0 if i + 1 == len(layers) else 2)   # 节点行 + (gap1+gap2)
    return layers, rows


def _colored(t: Task) -> str:
    return f"{C[t.state]}{_cell_text(t)}{C['end']}"


def render_graph(model: Model, now_iso: str, width: int = 72) -> str:
    layers, rows = layout_layers(model)
    edges = _edges(model)
    out = [f"{model.project} · DAG", "─" * width]
    for i in range(len(layers)):
        line = ""
        for cell in rows[i]:
            t = next(t for t in layers[i] if t.id == cell.id)
            line += " " * (cell.x - len(re.sub(r"\033\[[0-9;]*m", "", line))) + _colored(t)
        out.append(line.rstrip())
        if i + 1 == len(layers):
            break
        row_ids = {c.id: c.x for c in rows[i]}
        next_row = {c.id: c.x for c in rows[i + 1]}
        l1 = [" "] * (width * 2)
        for cid in next_row:                        # 垂直段:每个有边父节点列
            for p in edges.get(cid, ()):
                if p in row_ids:
                    l1[row_ids[p] + 1] = "│"
        out.append("".join(l1).rstrip())
        l2 = [" "] * (width * 2)
        for cid, cx in next_row.items():            # 汇入箭头 ▼
            l2[cx + 1] = "▼"
        for cid, cx in next_row.items():            # 水平路由:父列 ── 到子列
            for p in edges.get(cid, ()):
                if p in row_ids:
                    for x in range(min(row_ids[p], cx) + 1, max(row_ids[p], cx) + 2):
                        if l2[x] == " ":
                            l2[x] = "─"
        out.append("".join(l2).rstrip())
    out.append("─" * width)
    return "\n".join(out)


def parse_mouse(seq: str) -> Optional[Tuple[int, int, int]]:
    """SGR 鼠标序列 → (button, col, row);仅左键单击(button 0),其余/非鼠标 None。"""
    m = _MOUSE_RE.match(seq)
    if m and m.group(1) == "0":
        return 0, int(m.group(2)), int(m.group(3))
    return None


def hit_test(model: Model, col: int, row_1based: int) -> Optional[str]:
    """终端 1 基 (col,row) → 命中的任务 id;空白处 None。"""
    row = row_1based - 1
    for cells in layout_layers(model)[1]:
        for cell in cells:
            if cell.line == row and cell.x <= col < cell.x + cell.width:
                return cell.id
    return None


def parse_events(chunk: str, pending: str = "") -> Tuple[List[Tuple], str]:
    """os.read 整块 → 事件序列 + 未竟尾巴。

    TextIO 缓冲教训:read(1) 会把整段鼠标序列吞进 Python 缓冲,select
    再也看不到;必须 os.read 拿整块,在块级解析。左键单击出
    ("mouse", col, row);普通键逐个 ("key", ch);其他 ESC 序列吞弃;
    半截鼠标序列挂起等下一块。
    """
    buf = pending + chunk
    events: List[Tuple] = []
    while buf:
        if buf.startswith("\x1b"):
            m = _MOUSE_PREFIX_RE.match(buf)
            if m:
                if m.group(1) == "0":
                    events.append(("mouse", int(m.group(2)), int(m.group(3))))
                buf = buf[m.end():]
                continue
            if re.match(r"\x1b\[(?:<\d+(?:;\d*)*)?$", buf):   # 半截:挂起
                return events, buf
            m2 = re.match(r"\x1b\[[0-9;]*[A-Za-z]", buf)        # 其他 ESC 序列
            buf = buf[m2.end():] if m2 else buf[1:]
            continue
        events.append(("key", buf[0]))
        buf = buf[1:]
    return events, ""


def next_view(view: str, key: str) -> str:
    """watch 视图切换:g 在 panel/graph 间翻转,其余键不改变视图。"""
    if key == "g":
        return "graph" if view == "panel" else "panel"
    return view
