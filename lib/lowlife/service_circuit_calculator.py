# -*- coding: utf-8 -*-
from lowlife.service_circuit_graph import attach_point
from lowlife.service_circuit_routes import route_sequence

def calculate_circuit_paths(graph, circuits, point_by_id, snap_tolerance=1.0):
    results=[]
    for circuit in circuits:
        source=point_by_id.get(circuit.source_id)
        devices=[point_by_id[i] for i in circuit.device_ids if i in point_by_id]
        if source is None or not devices:
            results.append({"circuit": circuit, "paths": [], "length": None, "status": "missing_endpoint"})
            continue
        source_node, source_gap=attach_point(graph, source)
        device_snap=[attach_point(graph, p) for p in devices]
        if source_gap is None or source_gap > snap_tolerance or any(gap is None or gap > snap_tolerance for node, gap in device_snap):
            results.append({"circuit": circuit, "paths": [], "length": None, "status": "off_route"})
            continue
        device_nodes=[node for node, gap in device_snap]
        if circuit.route_mode == "sequence":
            paths,total=route_sequence(graph, source_node, device_nodes, circuit.ring)
        else:
            paths=[]; total=0.0
            for node in device_nodes:
                part=route_sequence(graph, source_node, [node], False)[1]
                if part is None:
                    total=None; break
                total += part
        status = "ok" if total is not None and total > 0.0 else ("no_path" if total is None else "zero_path")
        results.append({"circuit": circuit, "paths": paths, "length": total, "status": status})
    return results
