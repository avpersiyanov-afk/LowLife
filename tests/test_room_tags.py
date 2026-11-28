# -*- coding: utf-8 -*-
"""Room tag reconciliation with a small Revit API substitute."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


@pytest.fixture
def scene():
    path = Path(__file__).parents[1] / 'lib/lowlife/room_tags.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('run', '_tagged_room_key', '_apply_type')]
    view = NS(Id=20, GenLevel=None)
    room = NS(Id=NS(IntegerValue=200))
    link = NS(Id=NS(IntegerValue=100))
    tags, visible, created = [], [], []

    class Collector:
        def __init__(self, doc, view_id=None):
            self.items = visible if view_id is not None else tags

        def OfCategory(self, category):
            return self

        def WhereElementIsNotElementType(self):
            return list(self.items)

    def delete(eid):
        tag = next(t for t in tags if t.Id == eid)
        if tag.fail_delete:
            raise RuntimeError('Cannot delete tag')
        tags.remove(tag)
        if tag in visible:
            visible.remove(tag)

    def create(*args):
        created.append(args)
        return NS(GetTypeId=lambda: 7)

    ns = dict(FilteredElementCollector=Collector,
              BuiltInCategory=NS(OST_RoomTags=1),
              ElementId=NS(InvalidElementId=-1),
              LinkElementId=lambda *args: args, UV=lambda *args: args,
              _suppress_underlay=lambda v: None,
              _restore_underlay=lambda v, saved: None,
              _resolve_tag_room=lambda doc, tag: ('live', room, None),
              _is_orphaned=lambda tag: tag.broken,
              _room_ok=lambda r: True, _tag_anchor=lambda t: None,
              _tag_anchor_in_room=lambda *args: True,
              _iter_link_rooms=lambda doc: [(link, None, room)],
              _room_placed=lambda r: True,
              _room_center_host=lambda *args: NS(X=0, Y=0, Z=0),
              _point_in_view_crop=lambda *args: True)
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), ns)
    doc = NS(Delete=delete, Create=NS(NewRoomTag=create))

    def add(owner=20, shown=True, broken=False, fail_delete=False,
            replace_on_type=False):
        tag = NS(Id=NS(IntegerValue=len(tags) + 1), OwnerViewId=owner,
                 TaggedRoomId=NS(LinkInstanceId=link.Id, LinkedElementId=room.Id),
                 broken=broken, fail_delete=fail_delete, GetTypeId=lambda: 6)

        def change_type(type_id):
            tag.GetTypeId = lambda: type_id
            if replace_on_type:
                del tag.TaggedRoomId

        tag.ChangeTypeId = change_type
        tags.append(tag)
        if shown:
            visible.append(tag)
        return tag

    return NS(add=add, run=lambda: ns['run'](doc, view, 7), created=created)


def test_dependent_view_updates_visible_primary_tag(scene):
    tag = scene.add(owner=10)
    assert scene.run()['retyped'] == 1
    assert tag.GetTypeId() == 7
    assert scene.run()['added'] == 0
    assert not scene.created


def test_other_view_tag_does_not_block_placement(scene):
    scene.add(owner=10, shown=False)
    assert scene.run()['added'] == 1


def test_hidden_owned_tag_blocks_duplicate(scene):
    scene.add(shown=False)
    assert scene.run()['added'] == 0


def test_type_replacement_does_not_lose_room_identity(scene):
    scene.add(replace_on_type=True)
    assert scene.run()['added'] == 0


def test_failed_deletion_does_not_create_overlay(scene):
    scene.add(broken=True, fail_delete=True)
    stats = scene.run()
    assert stats['orphan_unresolved'] == 1
    assert stats['added'] == 0


def test_deleted_broken_tag_is_replaced(scene):
    scene.add(broken=True)
    stats = scene.run()
    assert (stats['deleted'], stats['added']) == (1, 1)


def test_deleting_one_broken_tag_keeps_other_tag_identity(scene):
    scene.add(broken=True)
    scene.add()
    stats = scene.run()
    assert (stats['deleted'], stats['added']) == (1, 0)
