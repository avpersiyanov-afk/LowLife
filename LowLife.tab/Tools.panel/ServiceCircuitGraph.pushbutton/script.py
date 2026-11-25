# -*- coding: utf-8 -*-
from pyrevit import revit, forms, script
from lowlife.service_circuit_runtime import build_document_graph, collect_electrical_circuits

doc = revit.doc
try:
    graph = build_document_graph(doc)
    circuits = collect_electrical_circuits(doc)
    output = script.get_output()
    output.print_md("### Служебный граф цепей")
    output.print_md("Вершин: **{}**, рёбер: **{}**, электрических цепей: **{}**".format(len(graph.nodes), len(graph.edges), len(circuits)))
    forms.alert("Граф построен. Вершин: {}\nРёбер: {}\nЦепей: {}".format(len(graph.nodes), len(graph.edges), len(circuits)))
except Exception as error:
    forms.alert("Не удалось построить служебный граф:\n{}".format(error), exitscript=True)
