# -*- coding: utf-8 -*-
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest


def guard(doc, protected, states=None):
    path=Path(__file__).parents[1]/'lib/lowlife/opening_tasks_revit.py'
    fn=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='assert_safe_replacement')
    class Probe:
        def __init__(self,document):self.doc=document
        def Start(self):self.before=dict(self.doc.elements)
        def RollBack(self):self.doc.elements=self.before;self.doc.restored=True
    ns=dict(annotation_states=states or (lambda d:{}),SubTransaction=Probe,protected_annotations=lambda d,o:set(protected),
            CategoryType=NS(Annotation='annotation'),boxes=NS(_id_int=lambda eid:eid),
            tr=lambda ru,en=None:ru,unicode=str)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
    ns['assert_safe_replacement'](doc,NS(Id=1))


class Document:
    def __init__(self,cascade):
        self.elements={1:NS(Category=None),2:NS(Category=NS(CategoryType='annotation'))}
        self.cascade=cascade
        self.restored=False
    def Delete(self,eid):
        deleted=[eid,2] if self.cascade else [eid]
        for key in deleted:self.elements.pop(key)
        return deleted
    def GetElement(self,eid):return self.elements.get(eid)
    def Regenerate(self):pass


def test_existing_dimensions_block_replacement_without_deleting_anything():
    doc=Document(False)
    with pytest.raises(ValueError):guard(doc,[2])
    assert doc.restored and set(doc.elements)=={1,2}


def test_cascaded_annotation_deletion_is_detected_and_rolled_back():
    doc=Document(True)
    with pytest.raises(ValueError):guard(doc,[])
    assert doc.restored and set(doc.elements)=={1,2}


def test_unannotated_opening_probe_also_rolls_back():
    doc=Document(False)
    guard(doc,[])
    assert doc.restored and 1 in doc.elements


def test_dimension_reference_damage_blocks_replacement_even_without_deletion():
    doc=Document(False)
    with pytest.raises(ValueError):
        guard(doc,[],states=lambda d:{2:('references_available',1 in d.elements)})
    assert doc.restored and set(doc.elements)=={1,2}
