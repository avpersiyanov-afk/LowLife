# -*- coding: utf-8 -*-
def mark_text(result):
    circuit = result["circuit"]
    status = result.get("status")
    if status == "ok":
        return u"{} | {:.1f} м".format(circuit.circuit_id, result["length"] * 0.3048)
    if status == "no_path":
        return u"{} | ПУТЬ НЕ НАЙДЕН".format(circuit.circuit_id)
    return u"{} | НЕТ ПОДКЛЮЧЕНИЯ".format(circuit.circuit_id)

def mark_key(system_kind, circuit_id, view_id):
    return u"ServiceCircuit:{}:{}:{}".format(system_kind, circuit_id, view_id)
