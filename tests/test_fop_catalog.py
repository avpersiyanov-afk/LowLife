# -*- coding: utf-8 -*-
"""Тесты для lowlife.fop_catalog — каталог параметров кнопки «Параметры в ФОП»."""

import io
import os

from lowlife import fop_catalog as fc


LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib", "lowlife")

SETTINGS_MODULES = {
    "SCS": "scs_settings.py",
    "SKUD": "skud_settings.py",
    "SPS": "fire_alarm_settings.py",
    "SOUE": "fire_alarm_settings.py",
    "SPA": "fire_alarm_settings.py",
    "SOT": "sot_settings.py",
}


def _source(name):
    with io.open(os.path.join(LIB, name), encoding="utf-8") as f:
        return f.read()


def _row(rows, key):
    return [r for r in rows if r.key == key][0]


def test_every_key_is_a_settings_field_of_its_systems():
    for spec in fc.CATALOG:
        assert spec.categories, spec.key
        for system in spec.categories:
            assert system in fc.SYSTEM_IDS
            src = _source(SETTINGS_MODULES[system])
            for key in spec.keys_for(system):
                assert u'("{}",'.format(key) in src, (key, system)
        for system in spec.system_keys:
            assert system in spec.categories, (spec.key, system)


def test_each_settings_key_belongs_to_one_role():
    seen = {}
    for spec in fc.CATALOG:
        for system in spec.categories:
            for key in spec.keys_for(system):
                assert (system, key) not in seen, (system, key, seen.get((system, key)))
                seen[(system, key)] = spec.key


def test_same_role_under_other_keys_shares_one_name():
    settings = {"SKUD": {"schematic_address_param": u"Адрес на значке"}}
    rows = fc.build_rows(["SCS", "SKUD", "SOT"], settings)
    assert _row(rows, "device_address_param").Name == u"Адрес на значке"
    keys = {r.key for r in rows}
    assert not keys & {"schematic_address_param", "controller_marking_param"}

    _row(rows, "device_address_param").Name = u"Адрес"
    _row(rows, "device_marking_param").Name = u"Марка"
    updates = fc.settings_updates(rows, settings)
    assert updates["SOT"]["device_address_param"] == u"Адрес"
    assert updates["SKUD"]["device_address_param"] == u"Адрес"
    assert updates["SKUD"]["schematic_address_param"] == u"Адрес"
    assert updates["SKUD"]["device_marking_param"] == u"Марка"
    assert updates["SKUD"]["controller_marking_param"] == u"Марка"


def test_catalog_is_consistent():
    keys = [s.key for s in fc.CATALOG]
    assert len(keys) == len(set(keys))
    examples = [s.example.lower() for s in fc.CATALOG]
    assert len(examples) == len(set(examples))
    for spec in fc.CATALOG:
        assert spec.data_type in fc.DATA_TYPE_TITLES
        assert spec.kind in fc.KIND_TITLES
        assert fc.name_error(fc.example_name(spec, fc.DEFAULT_PREFIX)) is None
        for cats in spec.categories.values():
            assert cats
            for c in cats:
                assert c in fc.CATEGORY_TITLES


def test_rows_only_for_chosen_systems_with_merged_categories():
    rows = fc.build_rows(["SOT"])
    assert {r.key for r in rows} == {s.key for s in fc.CATALOG if "SOT" in s.categories}

    row = _row(fc.build_rows(["SCS", "SPS"]), "device_address_param")
    assert row.systems == ["SCS", "SPS"]
    assert row.categories == fc.LV_DEVICES + [fc.FIRE_DEVICES, fc.EQUIPMENT]

    assert fc.build_rows([]) == []


def test_names_from_settings_then_shared_then_example():
    settings = {"SKUD": {"addr_param_name": u"Мой адрес"}, "SCS": {"addr_param_name": u"  "}}
    rows = fc.build_rows(["SCS", "SKUD"], settings, {"route_param_name": u"Общий тип"}, u"PR_")
    assert _row(rows, "addr_param_name").Name == u"Мой адрес"
    assert _row(rows, "route_param_name").Name == u"Общий тип"
    assert _row(rows, "segment_loads_param").Name == u"PR_Цепи узла"
    assert _row(rows, "segment_loads_param").Example == u"PR_Цепи узла"


def test_list_setting_uses_first_name():
    rows = fc.build_rows(["SCS"], {"SCS": {"offset_param_names": u"Отм1, Отм2"}})
    assert _row(rows, "offset_param_names").Name == u"Отм1"


def test_designation_is_one_type_param_for_all_systems():
    spec = dict((s.key, s) for s in fc.CATALOG)["designation_param"]
    assert spec.kind == fc.TYPE
    assert set(spec.categories) == {"SCS", "SKUD", "SPS", "SOUE", "SPA"}
    assert "type_code_param" not in {s.key for s in fc.CATALOG}


def test_builtin_revit_params_are_not_in_catalog():
    keys = {s.key for s in fc.CATALOG}
    assert not keys & {"circuit_panel_param", "load_name_param", "cable_type_param"}


def test_change_prefix_keeps_edited_names():
    rows = fc.build_rows(["SCS"], {"SCS": {"addr_param_name": u"Свой"}})
    _row(rows, "route_param_name").Name = u"Правка"
    fc.change_prefix(rows, fc.DEFAULT_PREFIX, u"X_")
    assert _row(rows, "segment_loads_param").Name == u"X_Цепи узла"
    assert _row(rows, "route_param_name").Name == u"Правка"
    assert _row(rows, "addr_param_name").Name == u"Свой"
    assert _row(rows, "route_param_name").Example == u"X_Тип трассы"


def test_validate():
    rows = fc.build_rows(["SCS"])
    assert fc.validate(rows) == []
    _row(rows, "addr_param_name").Name = u"  "
    _row(rows, "route_param_name").Name = u"a:b"
    _row(rows, "cable_param_name").Name = u"lL_цепи УЗЛА"
    _row(rows, "segment_loads_param").Name = u"LL_Цепи узла"
    errors = fc.validate(rows)
    assert len(errors) == 3
    assert any(u"пустое имя" in e for e in errors)
    assert any(u":" in e and u"символы" in e for e in errors)
    assert any(u"одно и то же имя" in e for e in errors)

    # неотмеченные строки не проверяются
    for r in rows:
        r.Checked = False
    assert fc.validate(rows) == []


def test_settings_updates():
    settings = {"SCS": {"offset_param_names": u"Старая, Новая, Ещё"}}
    rows = fc.build_rows(["SCS", "SKUD"], settings)
    _row(rows, "offset_param_names").Name = u"Новая"
    _row(rows, "addr_param_name").Name = u" Адрес "
    _row(rows, "route_param_name").Checked = False
    updates = fc.settings_updates(rows, settings)
    assert updates["SCS"]["offset_param_names"] == u"Новая, Старая, Ещё"
    assert updates["SKUD"]["offset_param_names"] == u"Новая"
    assert updates["SCS"]["addr_param_name"] == u"Адрес"
    assert updates["SKUD"]["addr_param_name"] == u"Адрес"
    assert "route_param_name" not in updates["SCS"]


def _defs(*items):
    return [fc.FopDef(name, u"Группа", dtype) for name, dtype in items]


def test_similarity():
    spec = dict((s.key, s) for s in fc.CATALOG)
    assert fc.similarity(spec["wire_length_param"], u"ADSK_Длина проводника") == 1
    assert fc.similarity(spec["wire_length_param"], u"Длина кабеля") == 0
    # лишнее слово, отличающее другую роль, — не похоже
    assert fc.similarity(spec["wire_length_param"], u"Длина проводника в лотке") is None
    assert fc.similarity(spec["tray_length_param"], u"ADSK_Длина проводника в лотке") == 1
    assert fc.similarity(spec["designation_param"], u"ADSK_Обозначение") == 1
    assert fc.similarity(spec["designation_param"], u"Обозначение типа") == 0
    assert fc.similarity(spec["designation_param"], u"Тип прокладки") is None
    assert fc.similarity(spec["device_address_param"], u"Адрес устройства на схеме") is None
    assert fc.similarity(spec["addr_param_name"], u"Номер цепи") is None


def test_match_fop_fills_examples_only():
    defs = _defs((u"ADSK_Длина проводника", fc.NUMBER), (u"ADSK_Длина проводника в трубе", fc.NUMBER),
                 (u"Адрес узла", fc.TEXT), (u"ПР_Отметка", fc.LENGTH), (u"Мой адрес", fc.TEXT))
    rows = fc.build_rows(["SCS"], {"SCS": {"addr_prev_param_name": u"Мой адрес"}})
    _row(rows, "route_param_name").Name = u"Своё"
    fc.match_fop(rows, defs)
    fc.update_status(rows, defs)
    assert _row(rows, "wire_length_param").Name == u"ADSK_Длина проводника"
    assert _row(rows, "pipe_length_param").Name == u"ADSK_Длина проводника в трубе"
    assert _row(rows, "tray_length_param").Name == u"LL_Длина в лотке"
    assert _row(rows, "addr_param_name").Name == u"Адрес узла"
    assert _row(rows, "offset_param_names").Name == u"ПР_Отметка"
    assert _row(rows, "addr_prev_param_name").Name == u"Мой адрес"  # из настроек
    assert _row(rows, "route_param_name").Name == u"Своё"           # правка
    assert u"похожий" in _row(rows, "wire_length_param").FopStatus
    assert u"есть" in _row(rows, "addr_prev_param_name").FopStatus
    assert u"не создаётся" in _row(rows, "tray_length_param").FopStatus
    fc.update_status(rows, defs, write_fop=True)
    assert u"будет создан" in _row(rows, "tray_length_param").FopStatus

    # другой ФОП: подставленное из старого — обратно к примеру
    fc.match_fop(rows, [])
    assert _row(rows, "wire_length_param").Name == u"LL_Длина проводника"


def test_match_fop_one_definition_per_row_prefers_type():
    defs = _defs((u"Длина проводника", fc.LENGTH), (u"Длина кабеля", fc.NUMBER))
    rows = fc.build_rows(["SCS"])
    fc.match_fop(rows, defs)
    fc.update_status(rows, defs)
    assert _row(rows, "wire_length_param").Name == u"Длина кабеля"


def test_status_warns_on_other_type():
    defs = _defs((u"LL_Длина проводника", fc.LENGTH))
    rows = fc.build_rows(["SCS"])
    fc.update_status(rows, defs)
    assert u"тип в ФОП не «Число»" in _row(rows, "wire_length_param").FopStatus
