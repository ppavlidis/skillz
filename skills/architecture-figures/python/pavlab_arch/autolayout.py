"""Graphviz-driven layout for architecture diagrams.

Uses graphviz purely as a *layout engine* — we hand it nodes (with sizes)
and edges, get back computed (x, y, width, height) for each node plus
Bezier-spline control points for each edge, and then render with our own
matplotlib primitives. The visual style stays pavlab; the geometry comes
from dot/neato/fdp.

Requires: the `graphviz` Python package AND the `dot` binary on PATH
(brew install graphviz).

Typical usage:

    from pavlab_arch.autolayout import GraphSpec, layout_graph

    g = GraphSpec(rankdir="LR", splines="spline", nodesep=0.6, ranksep=1.2)
    g.add_node("a", width=1.6, height=0.8)
    g.add_node("b", width=1.6, height=0.8)
    g.add_edge("a", "b")

    laid = layout_graph(g)
    cx, cy, w, h = laid.nodes["a"]              # data-coordinates
    for src, dst, pts in laid.edge_paths():     # list of (x, y) tuples
        ...

Graphviz parameters worth knowing (interpret from the prompt):

    rankdir : "LR" (left→right pipeline), "TB" (top→bottom workflow),
              "RL", "BT". Default "LR".
    splines : "spline" (curved, default), "ortho" (right-angle),
              "polyline" (segmented), "line" (straight, ignores nodes),
              "curved".
    nodesep : float, inches between nodes in the same rank.
    ranksep : float, inches between ranks.
    engine  : "dot" (hierarchical, default — the right tool for DAGs),
              "neato" / "fdp" / "sfdp" (force-directed, for networks),
              "twopi" (radial), "circo" (circular).

If the prompt says "left-to-right pipeline", use rankdir="LR". "Top-down
workflow" → "TB". "Tighter" → smaller nodesep/ranksep. "Orthogonal
arrows" → splines="ortho". When in doubt, dot + LR + spline is the
publication-grade default.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Iterable, Iterator


# Graphviz emits positions in points (72 per inch); we keep everything in
# inches so it composes with matplotlib figsize without surprises.
_PT_PER_INCH = 72.0


@dataclass
class GraphSpec:
    """Description of a graph to lay out.

    Sizes are in *inches* — the same units as matplotlib figsize — so
    laid-out coordinates can be fed directly into a figure of the
    returned bbox dimensions.
    """
    rankdir: str = "LR"
    splines: str = "spline"
    nodesep: float = 0.6
    ranksep: float = 1.0
    engine: str = "dot"
    # Per-node: {name: (width_in, height_in)} plus per-node attribute dict.
    _nodes: dict[str, tuple[float, float]] = field(default_factory=dict)
    _node_attrs: dict[str, dict[str, str]] = field(default_factory=dict)
    # Per-edge: list of (src, dst, attrs).
    _edges: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)
    # Per-rank grouping: {rank_name: [node, node, ...]} → forces "same"
    # rank. Useful for fork/join lanes that should align.
    _same_rank: list[list[str]] = field(default_factory=list)

    def add_node(self, name: str, *, width: float, height: float,
                 **attrs: str) -> None:
        self._nodes[name] = (width, height)
        if attrs:
            self._node_attrs[name] = {k: str(v) for k, v in attrs.items()}

    def add_edge(self, src: str, dst: str, **attrs: str) -> None:
        self._edges.append((src, dst, {k: str(v) for k, v in attrs.items()}))

    def same_rank(self, *nodes: str) -> None:
        """Force these nodes to share a rank (column for LR, row for TB)."""
        self._same_rank.append(list(nodes))

    def to_dot(self) -> str:
        """Render the spec to DOT source."""
        lines = [f"digraph G {{"]
        lines.append(f'  graph [rankdir="{self.rankdir}", '
                     f'splines="{self.splines}", '
                     f'nodesep={self.nodesep}, ranksep={self.ranksep}];')
        # Use point shape so dot doesn't add visible borders we don't want
        # at layout time. We only need the bounding-box geometry.
        lines.append('  node [shape=box, fixedsize=true];')
        for name, (w, h) in self._nodes.items():
            attrs = {"width": f"{w}", "height": f"{h}"}
            attrs.update(self._node_attrs.get(name, {}))
            attr_str = ", ".join(f'{k}="{v}"' for k, v in attrs.items())
            lines.append(f'  "{name}" [{attr_str}];')
        for src, dst, eattrs in self._edges:
            if eattrs:
                attr_str = ", ".join(f'{k}="{v}"' for k, v in eattrs.items())
                lines.append(f'  "{src}" -> "{dst}" [{attr_str}];')
            else:
                lines.append(f'  "{src}" -> "{dst}";')
        for group in self._same_rank:
            members = " ".join(f'"{n}"' for n in group)
            lines.append(f'  {{ rank=same; {members} }}')
        lines.append("}")
        return "\n".join(lines)


@dataclass
class EdgePath:
    """An edge as graphviz emitted it.

    ``bezier_points`` is the canonical 1+3k cubic-Bezier control sequence
    (point 0 is the curve start; points 1,2,3 are the first cubic; 4,5,6
    the second; and so on, sharing endpoints across segments).

    ``tail_end`` and ``head_end`` are optional explicit endpoints —
    graphviz emits these as ``s,x,y`` and ``e,x,y`` prefixes when the
    arrow tail / head should sit at a point distinct from the natural
    end of the spline (typically a node-boundary extension to the arrow
    tip). Rendered as a straight extension *outside* the Bezier curve.
    """
    bezier_points: list[tuple[float, float]]
    tail_end: tuple[float, float] | None = None
    head_end: tuple[float, float] | None = None


@dataclass
class LaidOut:
    """Result of running graphviz over a `GraphSpec`.

    All coordinates are in **inches**, with the origin at the bottom-left
    of the bounding box (matplotlib data-coordinate convention).
    """
    nodes: dict[str, tuple[float, float, float, float]]
    _edges: list[tuple[str, str, EdgePath]]
    bbox: tuple[float, float]
    dot_source: str

    def edge_paths(self) -> Iterator[tuple[str, str, EdgePath]]:
        yield from self._edges


def layout_graph(spec: GraphSpec) -> LaidOut:
    """Run the chosen graphviz engine over `spec` and parse the result.

    Returns a `LaidOut` with positions in inches, ready to feed to a
    matplotlib axes whose data limits match `LaidOut.bbox`.
    """
    if shutil.which(spec.engine) is None:
        raise RuntimeError(
            f"Graphviz engine '{spec.engine}' not found on PATH. "
            "Install with: brew install graphviz (macOS), "
            "apt install graphviz (Debian/Ubuntu), "
            "or choco install graphviz (Windows)."
        )
    dot_source = spec.to_dot()
    proc = subprocess.run(
        [spec.engine, "-Tjson"],
        input=dot_source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Graphviz failed (engine={spec.engine}):\n{proc.stderr}\n"
            f"--- DOT source ---\n{dot_source}"
        )
    data = json.loads(proc.stdout)

    # bb is "x_min,y_min,x_max,y_max" in points.
    bb_str = data.get("bb", "0,0,0,0")
    x0, y0, x1, y1 = (float(v) for v in bb_str.split(","))
    bbox = ((x1 - x0) / _PT_PER_INCH, (y1 - y0) / _PT_PER_INCH)

    # Nodes: "objects" list. Each has "name", "pos" (centre in points),
    # "width", "height" (in inches as we passed them in).
    name_to_idx: dict[str, int] = {}
    nodes: dict[str, tuple[float, float, float, float]] = {}
    for i, obj in enumerate(data.get("objects", [])):
        name = obj.get("name")
        if name is None or "pos" not in obj:
            continue
        name_to_idx[name] = i
        px, py = (float(v) for v in obj["pos"].split(","))
        cx = (px - x0) / _PT_PER_INCH
        cy = (py - y0) / _PT_PER_INCH
        w = float(obj.get("width", 0.0))
        h = float(obj.get("height", 0.0))
        nodes[name] = (cx, cy, w, h)

    # Edges: "edges" list. Each has "tail", "head" (indices into objects),
    # and a "pos" string we parse into an EdgePath.
    edges: list[tuple[str, str, EdgePath]] = []
    for edge in data.get("edges", []):
        tail_idx = edge.get("tail")
        head_idx = edge.get("head")
        if tail_idx is None or head_idx is None:
            continue
        src = dst = None
        for nm, idx in name_to_idx.items():
            if idx == tail_idx:
                src = nm
            if idx == head_idx:
                dst = nm
        if src is None or dst is None:
            continue
        pos = edge.get("pos", "")
        edges.append((src, dst, _parse_edge_pos(pos, x0, y0)))

    return LaidOut(nodes=nodes, _edges=edges, bbox=bbox, dot_source=dot_source)


def _parse_edge_pos(pos: str, x0: float, y0: float) -> EdgePath:
    """Parse graphviz edge "pos" into an EdgePath.

    Format: "s,sx,sy e,ex,ey x0,y0 x1,y1 x2,y2 ..." (in either order
    for s/e). The non-prefixed tokens form a 1+3k cubic-Bezier control
    sequence; s/e are *extension* points that the arrow tail / head
    sits at, drawn as straight segments outside the spline.
    """
    head_end = tail_end = None
    main_points: list[tuple[float, float]] = []
    for token in pos.split():
        if token.startswith("e,"):
            ex, ey = (float(v) for v in token[2:].split(","))
            head_end = ((ex - x0) / _PT_PER_INCH, (ey - y0) / _PT_PER_INCH)
        elif token.startswith("s,"):
            sx, sy = (float(v) for v in token[2:].split(","))
            tail_end = ((sx - x0) / _PT_PER_INCH, (sy - y0) / _PT_PER_INCH)
        else:
            try:
                x, y = (float(v) for v in token.split(","))
            except ValueError:
                continue
            main_points.append(((x - x0) / _PT_PER_INCH,
                                (y - y0) / _PT_PER_INCH))
    return EdgePath(bezier_points=main_points,
                    tail_end=tail_end, head_end=head_end)


def bezier_polyline(edge: "EdgePath | list[tuple[float, float]]",
                    samples_per_segment: int = 20
                    ) -> list[tuple[float, float]]:
    """Sample a graphviz edge spline into a dense polyline.

    Accepts either an ``EdgePath`` (preferred — the new shape from
    ``_parse_edge_pos``) or a raw list of points (legacy callers).

    For an ``EdgePath``: samples the cubic-Bezier control sequence,
    then prepends ``tail_end`` and appends ``head_end`` as linear
    extensions if present. This is the correct rendering of a graphviz
    edge — the s/e prefixes are arrowhead extensions, not Bezier
    control points.
    """
    if isinstance(edge, EdgePath):
        bez = edge.bezier_points
        tail_end = edge.tail_end
        head_end = edge.head_end
    else:
        bez = list(edge)
        tail_end = head_end = None

    if len(bez) < 4 or (len(bez) - 1) % 3 != 0:
        # Not a clean Bezier sequence — return what we have, with
        # endpoint extensions, so the caller still gets *something*.
        out = list(bez)
        if tail_end is not None:
            out = [tail_end] + out
        if head_end is not None:
            out = out + [head_end]
        return out

    out: list[tuple[float, float]] = [bez[0]]
    for i in range(0, len(bez) - 1, 3):
        p0, p1, p2, p3 = bez[i], bez[i + 1], bez[i + 2], bez[i + 3]
        for s in range(1, samples_per_segment + 1):
            t = s / samples_per_segment
            mt = 1 - t
            x = (mt**3 * p0[0]
                 + 3 * mt**2 * t * p1[0]
                 + 3 * mt * t**2 * p2[0]
                 + t**3 * p3[0])
            y = (mt**3 * p0[1]
                 + 3 * mt**2 * t * p1[1]
                 + 3 * mt * t**2 * p2[1]
                 + t**3 * p3[1])
            out.append((x, y))
    if tail_end is not None:
        out = [tail_end] + out
    if head_end is not None:
        out.append(head_end)
    return out
