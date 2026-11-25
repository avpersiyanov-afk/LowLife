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
