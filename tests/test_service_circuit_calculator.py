from lowlife.service_circuit_graph import build_graph
from lowlife.service_circuit_adapters import CircuitRecord
from lowlife.service_circuit_calculator import calculate_circuit_paths

def test_calculate_sequence_path():
    graph=build_graph([{"id":1,"p0":(0,0,0),"p1":(10,0,0),"length":10},{"id":2,"p0":(10,0,0),"p1":(20,0,0),"length":10}])
    c=CircuitRecord("SPS",1,100,[101],"sequence")
    result=calculate_circuit_paths(graph,[c],{100:(0,0,0),101:(20,0,0)})[0]
    assert result["status"]=="ok"
    assert result["length"]==20
