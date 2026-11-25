# -*- coding: utf-8 -*-
try:
    unicode
except NameError:
    unicode = str
ALIASES = {u"СКС":"SCS",u"SCS":"SCS",u"СКУД":"SKUD",u"SKUD":"SKUD",u"СПС":"SPS",u"SPS":"SPS",u"СОУЭ":"SOUE",u"SOUE":"SOUE"}
class CircuitRecord(object):
    def __init__(self, system_kind, circuit_id, source_id, device_ids, route_mode="per_device", ring=False):
        self.system_kind=normalize_system_kind(system_kind); self.circuit_id=circuit_id; self.source_id=source_id; self.device_ids=list(device_ids or []); self.route_mode=route_mode; self.ring=bool(ring)
def normalize_system_kind(value):
    return ALIASES.get(unicode(value or u"").strip().upper(), unicode(value or u"").strip().upper())
def sequence_mode(system_kind):
    return normalize_system_kind(system_kind) in ("SPS", "SOUE")
def adapt_revit_circuits(doc, system_kind="SCS"):
    from lowlife.service_circuit_runtime import collect_electrical_circuits
    requested=normalize_system_kind(system_kind); records=[]
    for record in collect_electrical_circuits(doc):
        record.system_kind=requested
        record.route_mode="sequence" if sequence_mode(requested) else ("per_device" if len(record.device_ids)>1 else record.route_mode)
        records.append(record)
    return records
def route_points_for_circuit(doc, circuit, point_by_id):
    return point_by_id.get(circuit.source_id), [point_by_id[i] for i in circuit.device_ids if i in point_by_id]
