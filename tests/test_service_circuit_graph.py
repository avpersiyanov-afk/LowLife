from lowlife.service_circuit_graph import build_graph, find_path

def test_graph_keeps_shared_edge_and_length():
    curves = [
        {"id": 1, "p0": (0, 0, 0), "p1": (10, 0, 0), "length": 10, "install": "tray"},
        {"id": 2, "p0": (10, 0, 0), "p1": (20, 0, 0), "length": 10, "install": "tray"},
    ]
    graph = build_graph(curves, 0.01)
    path = find_path(graph, (0, 0, 0), (20, 0, 0))
    assert path.node_ids[0] == (0, 0, 0)
    assert path.length == 20
