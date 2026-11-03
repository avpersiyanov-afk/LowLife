# -*- coding: utf-8 -*-
"""Контракт адаптера связей, без установленного Revit API."""
from lowlife import equipment_tags_links as links


class Obj(object):
    def __init__(self, **values):
        self.__dict__.update(values)


class Id(object):
    def __init__(self, value):
        self.Value = value


class Vec(object):
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z


class Transform(object):
    def __init__(self, fn):
        self.fn = fn

    def OfPoint(self, p):
        return self.fn(p)

    def Multiply(self, other):
        return Transform(lambda p: self.OfPoint(other.OfPoint(p)))


class Family(object):
    def __init__(self, value=7, box=None):
        self.Id = Id(value)
        self.Category = Obj(CategoryType='model')
        self.Symbol = Obj(FamilyName='Equipment')
        self.box = box

    def get_BoundingBox(self, view):
        assert view is None  # Never pass a host view into the link document.
        return self.box


def link(value=20, element=None, transform=None):
    return Obj(Id=Id(value), GetTotalTransform=lambda: transform,
               GetLinkDocument=lambda: Obj(GetElement=lambda eid: element))


def test_keys_distinguish_host_and_multiple_instances():
    equipment = Family()
    a = links.LinkedEquipment(link(20), equipment)
    b = links.LinkedEquipment(link(21), equipment)
    assert len(set([links.equipment_key(equipment), links.equipment_key(a),
                    links.equipment_key(b)])) == 3
    assert links.equipment_key(a) == (20, 7)


def test_bbox_composes_box_and_link_transforms_and_all_corners(monkeypatch):
    monkeypatch.setattr(links, '_db', lambda: Obj(XYZ=Vec, BoundingBoxXYZ=Obj))
    # Offset in box coordinates, then reflected 45-degree rotation + translation.
    box = Obj(Min=Vec(0, 0, 0), Max=Vec(2, 4, 3),
              Transform=Transform(lambda p: Vec(p.X + 1, p.Y, p.Z)))
    transform = Transform(lambda p: Vec(10 - p.X - p.Y, 20 - p.X + p.Y, p.Z + 5))
    target = links.LinkedEquipment(link(transform=transform), Family(box=box))
    result = target.get_BoundingBox(Obj())
    assert (result.Min.X, result.Min.Y, result.Min.Z) == (3, 17, 5)
    assert (result.Max.X, result.Max.Y, result.Max.Z) == (9, 23, 8)


def test_missing_bbox_is_skipped():
    assert links.LinkedEquipment(link(), Family()).get_BoundingBox(Obj()) is None


def test_reference_is_created_in_selected_link_instance(monkeypatch):
    target = Family()
    instance = link()
    calls = []

    def reference(element):
        calls.append(element)
        return Obj(CreateLinkReference=lambda chosen: (element, chosen))

    monkeypatch.setattr(links, '_db', lambda: Obj(Reference=reference))
    assert links.equipment_reference(links.LinkedEquipment(instance, target)) == (target, instance)
    assert calls == [target]


def test_visibility_uses_host_view_and_link_not_whole_document(monkeypatch):
    doc, view, instance = Obj(), Obj(Id=Id(3)), link()
    target = Family()
    annotation = Family(8)
    annotation.Category = Obj(CategoryType='annotation')
    calls = []

    def collector(*args):
        calls.append(args)
        return Obj(OfClass=lambda cls: [target, annotation])

    monkeypatch.setattr(links, '_db', lambda: Obj(
        FilteredElementCollector=collector, FamilyInstance=Family,
        CategoryType=Obj(Model='model')))
    result = links.visible_equipment(doc, view, instance)
    assert calls == [(doc, view.Id, instance.Id)]
    assert len(result) == 1
    assert result[0].element is target
    assert result[0].link is instance


def test_tag_targets_resolve_host_and_link_and_unloaded_link(monkeypatch):
    invalid = Obj()
    target = Family()
    instance = link(element=target)
    unloaded = Obj(GetLinkDocument=lambda: None)
    host = Family(7)
    elements = {20: instance, 21: unloaded, 7: host}
    doc = Obj(GetElement=lambda eid: elements[eid.Value])
    ids = [Obj(LinkInstanceId=Id(20), LinkedElementId=target.Id),
           Obj(LinkInstanceId=invalid, HostElementId=host.Id),
           Obj(LinkInstanceId=Id(21), LinkedElementId=target.Id)]
    monkeypatch.setattr(links, '_db', lambda: Obj(
        FamilyInstance=Family, ElementId=Obj(InvalidElementId=invalid)))
    result = links.tagged_equipment(doc, Obj(GetTaggedElementIds=lambda: ids))
    assert links.equipment_key(result[0]) == (20, 7)
    assert result[1] is host
    assert result[2] is None
    # Unresolved targets are retained, so a multi-target tag isn't moved as a single-target one.
    assert len(result) == 3


def test_legacy_tag_target_api(monkeypatch):
    invalid = Obj()
    target = Family()
    monkeypatch.setattr(links, '_db', lambda: Obj(
        FamilyInstance=Family, ElementId=Obj(InvalidElementId=invalid)))
    doc = Obj(GetElement=lambda eid: target)
    tag = Obj(TaggedElementId=Obj(LinkInstanceId=invalid, HostElementId=target.Id))
    assert links.tagged_equipment(doc, tag) == [target]
