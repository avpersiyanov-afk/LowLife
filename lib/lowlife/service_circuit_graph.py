# -*- coding: utf-8 -*-
import heapq, math

class PathResult(object):
    def __init__(self, node_ids, length, edge_ids=None):
        self.node_ids = node_ids
        self.length = length
        self.edge_ids = list(edge_ids or [])

class Graph(object):
    def __init__(self):
        self.nodes = {}
        self.edges = {}
        self.neighbors = {}

def _key(point):
    return tuple(round(float(v), 6) for v in point)

def _distance(a, b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1]) + abs(a[2]-b[2])

def build_graph(curves, tolerance=0.01):
    graph = Graph()
    for curve in curves:
        a = _key(curve["p0"]); b = _key(curve["p1"])
        if a == b:
            continue
        graph.nodes.setdefault(a, a); graph.nodes.setdefault(b, b)
        edge_id = curve.get("id")
        length = float(curve.get("length", _distance(a, b)))
        edge = {"id": edge_id, "a": a, "b": b, "length": length, "install": curve.get("install")}
        graph.edges[(a, b, edge_id)] = edge
        graph.neighbors.setdefault(a, []).append((b, edge))
        graph.neighbors.setdefault(b, []).append((a, edge))
    return graph

def find_path(graph, start, end):
    start = _key(start); end = _key(end)
    if start not in graph.nodes or end not in graph.nodes:
        return PathResult([], None)
    queue = [(0.0, start)]
    costs = {start: 0.0}; previous = {}
    while queue:
        cost, node = heapq.heappop(queue)
        if node == end:
            break
        if cost != costs.get(node):
            continue
        for neighbor, edge in graph.neighbors.get(node, []):
            candidate = cost + edge["length"]
            if candidate < costs.get(neighbor, float("inf")):
                costs[neighbor] = candidate
                previous[neighbor] = (node, edge)
                heapq.heappush(queue, (candidate, neighbor))
    if end not in costs:
        return PathResult([], None)
    nodes = [end]; edges = []; current = end
    while current != start:
        parent, edge = previous[current]
        nodes.append(parent); edges.append(edge["id"]); current = parent
    nodes.reverse(); edges.reverse()
    return PathResult(nodes, costs[end], edges)

def nearest_node(graph, point):
    point = _key(point)
    if not graph.nodes:
        return None
    return min(graph.nodes, key=lambda node: _distance(node, point))

def nearest_node_with_distance(graph, point):
    node = nearest_node(graph, point)
    return (node, _distance(node, _key(point))) if node is not None else (None, None)

def attach_point(graph, point, tolerance=5.0):
    """Snap an element to the nearest point on a route segment, not only an endpoint."""
    p = tuple(float(v) for v in point)
    best = None
    for edge in list(graph.edges.values()):
        a, b = edge["a"], edge["b"]
        dx, dy, dz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
        denom = dx*dx + dy*dy + dz*dz
        t = 0.0 if denom == 0 else max(0.0, min(1.0, ((p[0]-a[0])*dx + (p[1]-a[1])*dy + (p[2]-a[2])*dz) / denom))
        q = (a[0]+t*dx, a[1]+t*dy, a[2]+t*dz)
        distance = _distance(p, q)
        if best is None or distance < best[0]:
            best = (distance, q, a, b, edge, t)
    if best is None or best[0] > tolerance:
        return None, best[0] if best else None
    _, q, a, b, edge, t = best
    q = _key(q)
    if q not in graph.nodes:
        graph.nodes[q] = q
        for endpoint, fraction in ((a, t), (b, 1.0-t)):
            if fraction <= 0.0:
                continue
            part = dict(edge)
            part["a"], part["b"] = endpoint, q
            part["length"] = edge["length"] * fraction
            graph.neighbors.setdefault(endpoint, []).append((q, part))
            graph.neighbors.setdefault(q, []).append((endpoint, part))
    return q, best[0]

