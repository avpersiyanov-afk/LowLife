# -*- coding: utf-8 -*-
import copy
import pytest
from lowlife import opening_levels_core as levels
from lowlife import opening_tasks_core as tasks


def test_floor_level_identity_wins_over_closer_auxiliary_or_other_building_levels():
    candidates=[dict(name=u'Корпус 2',elevation=10.1),
                dict(name=u'Вспомогательный',elevation=10.9),
                dict(name=u'Корпус 1',elevation=10)]
    assert levels.match_level(candidates,u'Корпус 1',10)==candidates[2]
    with pytest.raises(ValueError):levels.match_level(candidates,u'Нет такого',10.9)
    with pytest.raises(ValueError):levels.match_level(candidates,u'Корпус 1',0)


def test_mapping_uses_transformed_source_elevation_and_rejects_ambiguity():
    candidates=[dict(name='L1',elevation=105),dict(name='L1',elevation=5)]
    assert levels.match_level(candidates,'L1',105)['elevation']==105
    with pytest.raises(ValueError):levels.match_level(candidates+[dict(candidates[0])],'L1',105)
    with pytest.raises(ValueError):levels.match_level(candidates,'L1',105.01)


def test_downward_ray_uses_first_physical_hit_not_lowest_assigned_level():
    hits=[dict(distance=10,host_uid='lower',level_uid='other-building'),
          dict(distance=2,host_uid='upper',level_uid='correct')]
    assert levels.first_hit(hits)['level_uid']=='correct'
    # No bounding-box-only hit is supplied: a ray through a hole reaches the next slab.
    assert levels.first_hit(hits[:1])['host_uid']=='lower'


def test_no_fallback_when_ray_misses_or_first_hit_has_no_level():
    with pytest.raises(ValueError):levels.first_hit([])
    with pytest.raises(ValueError):levels.first_hit([
        dict(distance=1,host_uid='unassigned',level_uid=None),
        dict(distance=2,host_uid='deeper',level_uid='valid')])


def test_overlapping_surfaces_with_conflicting_levels_require_review():
    with pytest.raises(ValueError):levels.first_hit([
        dict(distance=1,host_uid='a',level_uid='L1'),
        dict(distance=1,host_uid='b',level_uid='L2')])
    assert levels.first_hit([dict(distance=1,host_uid='b',level_uid='L'),
                             dict(distance=1,host_uid='a',level_uid='L')])['host_uid']=='a'


def test_corrected_level_is_a_new_release_without_moving_opening():
    draft=dict(task_id='a',source_model='vis',source_uid='route',owner_uid='box',
               geometry=dict(kind='wall',center_mm=[0,0,1000],size_mm=[400,200,300],
                             x_dir=[1,0,0],host_uid='wall',host_model='kr'))
    registry,_=tasks.issue(tasks.empty_registry(),[draft],'P','OV','who','t1')
    draft['level']=dict(name='L1',source_level_uid='level',support_uid='slab',method='downward_ray')
    updated,changed=tasks.issue(registry,[draft],'P','OV','who','t2')
    assert changed[0]['revision']==2
    assert tasks.change_kinds(registry['tasks']['a'],updated['tasks']['a'])==['level']
    same,changed=tasks.issue(updated,[copy.deepcopy(draft)],'P','OV','who','t3')
    assert not changed and same==updated
