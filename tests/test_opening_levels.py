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
    assert levels.match_level(candidates,u'Нет такого',10.9)==candidates[1]
    assert levels.match_level(candidates,u'Корпус 1',0)==candidates[2]


def test_mapping_uses_transformed_source_elevation_and_rejects_ambiguity():
    candidates=[dict(name='L1',elevation=105),dict(name='L1',elevation=5)]
    assert levels.match_level(candidates,'L1',105)['elevation']==105
    with pytest.raises(ValueError):levels.match_level(candidates+[dict(candidates[0])],'L1',105)
    assert levels.match_level(candidates,'L1',105.01)['elevation']==105


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


def test_ar_fallback_rejects_different_buildings_at_same_elevation():
    candidates=[dict(name='AR building 1',elevation=10),dict(name='AR building 2',elevation=10)]
    with pytest.raises(ValueError):levels.match_level(candidates,'KR level',10)
    assert levels.match_level([dict(name='AR',elevation=11)],'KR',10)['name']=='AR'


def test_nearest_ar_level_is_relative_to_kr_elevation_not_opening_height():
    candidates=[dict(name='AR lower',elevation=0),dict(name='AR upper',elevation=10),
                dict(name='KR roof',elevation=30)]
    assert levels.match_level(candidates,'KR slab',9.5)['name']=='AR upper'
    assert levels.match_level(candidates,'KR slab',0.5)['name']=='AR lower'
    with pytest.raises(ValueError):levels.match_level(candidates,'KR slab',5)
    with pytest.raises(ValueError):levels.match_level([],'KR slab',10)


def test_floor_and_building_from_existing_mask_override_distant_kr_elevation():
    candidates=[dict(name=u'АР_К1_+0.000_01',elevation=0),
                dict(name=u'АР_К1_+3.000_02',elevation=3),
                dict(name=u'АР_К2_+0.000_01',elevation=10),
                dict(name=u'КР_К1_+3.000_01_доп',elevation=3)]
    assert levels.match_level(candidates,u'КР_К1_+3.000_01_плита',3) is candidates[0]
    with pytest.raises(ValueError):
        levels.match_level(candidates,u'КР_К1_+3.000_03',3)


def test_custom_mask_is_used_without_an_additional_floor_parser():
    from lowlife.level_name_template import LevelNameTemplate
    mask=LevelNameTemplate(u'{Корпус}_{Этаж}_{Дисциплина}_{Комментарий}')
    candidates=[dict(name=u'К1_07_АР',elevation=0),dict(name=u'К1_08_АР',elevation=100)]
    assert levels.match_level(candidates,u'К1_07_КР_плита',100,template=mask) is candidates[0]


def test_identity_only_ignores_elevation_and_prefers_primary_ar_level():
    candidates=[dict(name=u'АР_К1_+0.000_01',elevation=0),
                dict(name=u'АР_К1_+99.000_01_вспомогательный',elevation=99),
                dict(name=u'АР_К2_+99.000_01',elevation=99),
                dict(name=u'АР_К1_+99.000_02',elevation=99)]
    assert levels.match_level(candidates,u'КР_К1_+99.000_1_доп',99,identity_only=True) is candidates[0]
    with pytest.raises(ValueError):
        levels.match_level(candidates,u'КР_К1_+99.000_03',99,identity_only=True)


def test_identity_only_does_not_guess_between_two_primary_floor_levels():
    candidates=[dict(name=u'АР_К1_+0.000_01',elevation=0),dict(name=u'АР_К1_+3.000_01',elevation=3)]
    with pytest.raises(ValueError):levels.match_level(candidates,u'КР_К1_+3.000_01',3,identity_only=True)


@pytest.mark.parametrize('building',[u'1 и 2',u'3',u'4'])
def test_auxiliary_kr_floor_matches_real_ar_names_from_report(building):
    source=u'КР_{}_+100,000_Этаж 1 (вспомогательный)'.format(building)
    main=dict(name=u'АР_{}_+0,330_Этаж 1'.format(building),elevation=0)
    auxiliary=dict(name=u'АР_{}_+99,000_Этаж 1 (вспомогательный)'.format(building),elevation=99)
    wrong=dict(name=u'АР_{}_+100,000_Этаж 2'.format(building),elevation=100)
    # Existing primary method still fails, enabling only the fallback.
    with pytest.raises(ValueError):levels.match_level([main,wrong],source,100)
    assert levels.match_level([auxiliary,main,wrong],source,100,identity_only=True) is main


def test_auxiliary_suffix_never_converts_aboveground_floor_to_basement():
    candidates=[dict(name=u'АР_0_-2,350_Этаж П1',elevation=-2.35),
                dict(name=u'АР_0_-4,150_Этаж П1',elevation=-4.15),
                dict(name=u'АР_0_-8,050_Этаж П2',elevation=-8.05)]
    with pytest.raises(ValueError):
        levels.match_level(candidates,u'КР_0_+0,000_Этаж 1 (вспомогательный)',0,identity_only=True)
