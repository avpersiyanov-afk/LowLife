# -*- coding: utf-8 -*-
from lowlife.service_circuit_graph import nearest_node
from lowlife.service_circuit_routes import route_sequence

def calculate_circuit_paths(graph, circuits, point_by_id):
    results=[]
    for circuit in circuits:
        source=point_by_id.get(circuit.source_id)
        devices=[point_by_id[i] for i in circuit.device_ids if i in point_by_id]
        if source is None or not devices:
            results.append({"circuit": circuit, "paths": [], "length": None, "status": "missing_endpoint"})
            continue
        source_node=nearest_node(graph, source)
        device_nodes=[nearest_node(graph, p) for p in devices]
        if circuit.route_mode == "sequence":
            paths,total=route_sequence(graph, source_node, device_nodes, circuit.ring)
        else:
            paths=[]; total=0.0
            for node in device_nodes:
                part=route_sequence(graph, source_node, [node], False)[1]
                if part is None:
                    total=None; break
                total += part
        results.append({"circuit": circuit, "paths": paths, "length": total, "status": "ok" if total is not None else "no_path"})
    return results
