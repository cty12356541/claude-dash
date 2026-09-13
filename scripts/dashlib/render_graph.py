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
    x: int                  # 节点框左缘列(0 基,ANSI 剥离后坐标)
    width: int              # 框外沿宽(含边框)
    line: int               # 节点文字所在输出行(0 基);框占 line±1

    @property
    def center(self) -> int:
        return self.x + self.width // 2


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


_BOX_ROW = 3        # 每节点框占 3 行(顶/文字/底)
_ZONE_ROW = 2       # 层间空档 2 行
_LAYER_PITCH = _BOX_ROW + _ZONE_ROW
_CANVAS_W = 240     # 画布宽(字符列表行缓冲)


def layout_layers(model: Model) -> Tuple[List[List[Task]], List[List[Cell]]]:
    """几何唯一源:每层节点的 (x, width, line)。

    节点带单线框(┌─┐│└┘):line 指向文字行,框占 line-1..line+1;
    同层节点以 _CELL_GAP 间隔左→右排布。"""
    layers = compute_layers(model)
    rows: List[List[Cell]] = []
    line = _HEAD_LINES + 1          # 首层文字行:标题+分隔线之后,留框顶
    for layer in layers:
        cells, col = [], 0
        for t in layer:
            text = _cell_text(t)
            w = len(text) + 2 * 1 + 2      # 左右内边距各 1 + 边框各 1
            cells.append(Cell(t.id, t.label, col, w, line))
            col += w + _CELL_GAP
        rows.append(cells)
        line += _LAYER_PITCH
    return layers, rows


def _colored(t: Task) -> str:
    return f"{C[t.state]}{_cell_text(t)}{C['end']}"


def render_graph(model: Model, now_iso: str, width: int = 72) -> str:
    """框化节点 DAG:任意跨层边均路由(竖穿 + 角折 + ▼ 入框顶)。

    路由策略(与"节点+边真图"的设计承诺一致):
    - 父框底中心 ┬ 出线;子框顶中心以 ▼ 入线(替换顶框 ─)
    - 相邻层:层间两行,│ 直落或 └─┐/┌─┘ 角折
    - 跨多层:竖线沿父中心列穿过中间层行(仅写入空白,遇节点框让路——
      结构碰撞时该段降级为断线,不覆盖任何节点/已有连线)
    """
    layers, rows = layout_layers(model)
    edges = _edges(model)
    by_id = {t.id: t for layer in layers for t in layer}
    cell_of = {c.id: c for cells in rows for c in cells}
    out_edges: Dict[str, set] = {}
    for cid, parents in edges.items():
        for p in parents:
            out_edges.setdefault(p, set()).add(cid)

    canvas = [[" "] * _CANVAS_W for _ in range(
        _HEAD_LINES + 1 + _LAYER_PITCH * max(1, len(layers)) + 2)]
    overlays: List[Tuple[int, int, str, int]] = []  # (row, col, 着色文字, 纯文本宽)

    def put(row: int, col: int, ch: str, only_space: bool = True) -> bool:
        if 0 <= row < len(canvas) and 0 <= col < _CANVAS_W:
            if not only_space or canvas[row][col] == " ":
                canvas[row][col] = ch
                return True
        return False

    # 1) 节点框
    box_rows: Dict[int, List[Tuple[int, int]]] = {}   # 文字行 → [(x, x+w)]
    for cells in rows:
        for c in cells:
            t = by_id[c.id]
            top, txt, bot = c.line - 1, c.line, c.line + 1
            for x in range(c.x, c.x + c.width):
                put(top, x, "─", only_space=False)
                put(bot, x, "─", only_space=False)
            put(top, c.x, "┌", only_space=False); put(top, c.x + c.width - 1, "┐", only_space=False)
            put(bot, c.x, "└", only_space=False); put(bot, c.x + c.width - 1, "┘", only_space=False)
            if out_edges.get(c.id):
                put(bot, c.center, "┬", only_space=False)   # 出线桩
            put(txt, c.x, "│", only_space=False); put(txt, c.x + c.width - 1, "│", only_space=False)
            overlays.append((txt, c.x + 2, _colored(t),
                             len(_cell_text(t))))             # 内边距 1 + 边框 1
            box_rows.setdefault(txt, []).append((c.x, c.x + c.width))

    def in_box(row: int, col: int) -> bool:
        return any(x0 <= col < x1 for x0, x1 in box_rows.get(row, ()))

    # 2) 边路由(任意层距)
    for cid, parents in edges.items():
        cc = cell_of.get(cid)
        if cc is None:
            continue
        for pid in parents:
            pc = cell_of.get(pid)
            if pc is None:
                continue
            # 竖穿段:父框底下一行 → 子入线行(子框顶上一行)前一格
            z_final = cc.line - 2               # 折线/直落行(紧贴子框顶上方)
            for row in range(pc.line + 2, z_final):
                if not in_box(row, pc.center):
                    put(row, pc.center, "│")
            if pc.center == cc.center:
                put(z_final, pc.center, "│")
            else:
                corner_p = "└" if pc.center < cc.center else "┌"
                corner_c = "┐" if pc.center < cc.center else "┘"
                put(z_final, pc.center, corner_p)
                put(z_final, cc.center, corner_c)
                step = 1 if pc.center < cc.center else -1
                for x in range(pc.center + step, cc.center, step):
                    put(z_final, x, "─")
            put(cc.line - 1, cc.center, "▼", only_space=False)   # 箭头嵌子框顶

    # 3) 输出:纯字符行 + 着色覆盖(canvas 行号即最终输出行号——
    #    行 0/1 由标题/分隔线占据,框从行 2 起,故跳过画布头两行;
    #    覆盖按纯文本宽切片——ANSI 长度会吃掉框右缘)
    lines = [f"{model.project} · DAG", "─" * width]
    ol: Dict[int, List[Tuple[int, str, int]]] = {}
    for r, c, s, plen in overlays:
        ol.setdefault(r, []).append((c, s, plen))
    last = len(canvas) - 1
    while last >= _HEAD_LINES and not "".join(canvas[last]).strip():
        last -= 1                                   # 裁尾部全空行(画布过量分配)
    for r in range(_HEAD_LINES, last + 1):
        line = "".join(canvas[r]).rstrip()
        # 从右往左覆盖:低列插入的 ANSI 会推移高列切片位,反序则互不影响
        for c, s, plen in sorted(ol.get(r, ()), reverse=True):
            line = line[:c] + s + line[c + plen:]
        lines.append(line.rstrip())
    lines.append("─" * width)
    return "\n".join(lines)


def parse_mouse(seq: str) -> Optional[Tuple[int, int, int]]:
    """SGR 鼠标序列 → (button, col, row);仅左键单击(button 0),其余/非鼠标 None。"""
    m = _MOUSE_RE.match(seq)
    if m and m.group(1) == "0":
        return 0, int(m.group(2)), int(m.group(3))
    return None


def hit_test(model: Model, col: int, row_1based: int) -> Optional[str]:
    """终端 1 基 (col,row) → 命中的任务 id;命中区=节点框三行整框;空白 None。"""
    row = row_1based - 1
    for cells in layout_layers(model)[1]:
        for cell in cells:
            if cell.line - 1 <= row <= cell.line + 1 and cell.x <= col < cell.x + cell.width:
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
