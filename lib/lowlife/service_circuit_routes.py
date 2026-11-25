# -*- coding: utf-8 -*-
try:
    unicode
except NameError:
    unicode = str

def route_sequence(graph, source_point, device_points, ring=False):
    from lowlife.service_circuit_graph import find_path
    points = [source_point] + list(device_points or [])
    paths = []
    total = 0.0
    for start, end in zip(points, points[1:]):
        result = find_path(graph, start, end)
        paths.append(result)
        if result.length is None:
            return paths, None
        total += result.length
    if ring and len(points) > 1:
        result = find_path(graph, points[-1], source_point)
        paths.append(result)
        if result.length is None:
            return paths, None
        total += result.length
    return paths, total
