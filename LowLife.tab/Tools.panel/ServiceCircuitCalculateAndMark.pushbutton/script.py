# -*- coding: utf-8 -*-
from pyrevit import revit, forms, script
from lowlife.service_circuit_runtime import build_document_graph, collect_element_points
from lowlife.service_circuit_adapters import adapt_revit_circuits, element_point
from lowlife.service_circuit_calculator import calculate_circuit_paths

doc = revit.doc
try:
    graph = build_document_graph(doc)
    circuits = adapt_revit_circuits(doc, "SCS")
    points = collect_element_points(doc)
    for circuit in circuits:
        for element_id in [circuit.source_id] + list(circuit.device_ids):
            element = doc.GetElement(element_id)
            point = element_point(element) if element is not None else None
            if point is not None:
                points[element_id] = point
    results = calculate_circuit_paths(graph, circuits, points)
    output = script.get_output()
    output.print_md("### Служебный расчёт цепей")
    output.print_md("Граф: **{}** вершин, **{}** рёбер".format(len(graph.nodes), len(graph.edges)))
    output.print_md("Цепей найдено: **{}**".format(len(results)))
    ok = no_path = missing = 0
    for result in results:
        circuit = result["circuit"]
        if result["status"] == "ok":
            ok += 1
            output.print_md("- Цепь `{}`: **{:.2f} м**".format(circuit.circuit_id, result["length"] * 0.3048))
        elif result["status"] == "no_path":
            no_path += 1
            output.print_md("- Цепь `{}`: **путь не найден**".format(circuit.circuit_id))
        else:
            missing += 1
            output.print_md("- Цепь `{}`: **нет точки подключения**".format(circuit.circuit_id))
    forms.alert("Расчёт выполнен.\nУспешно: {}\nПуть не найден: {}\nНет точки подключения: {}".format(ok, no_path, missing))
except Exception as error:
    forms.alert("Ошибка служебного расчёта:\n{}".format(error), exitscript=True)
