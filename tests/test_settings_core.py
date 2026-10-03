# -*- coding: utf-8 -*-
"""Тесты для lowlife.settings_core — общее хранилище настроек кнопок
(JsonStore) и данные типового окна из текстовых полей (TextSettings).
Окно (WPF) и forms.alert вне Revit не проверяются: pyrevit здесь не
импортируется, _alert молча ничего не делает."""

import io
import json
import os

import pytest

from lowlife import settings_core
from lowlife.settings_core import JsonStore, NumberField, TextField, TextSettings


@pytest.fixture
def appdata(tmpdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmpdir))
    return str(tmpdir)


def _write_raw(appdata, name, text):
    folder = os.path.join(appdata, "pyRevit")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(text)


def test_path_is_in_appdata_pyrevit_and_folder_is_created(appdata):
    store = JsonStore("LowLifeTest_settings.json")
    assert store.path() == os.path.join(appdata, "pyRevit", "LowLifeTest_settings.json")
    assert os.path.isdir(os.path.join(appdata, "pyRevit"))


def test_read_missing_empty_broken_or_non_dict_file_gives_empty_dict(appdata):
    store = JsonStore("LowLifeTest_settings.json")
    assert store.read() == {}
    for text in (u"", u"   \n", u"{не json", u"[1, 2]"):
        _write_raw(appdata, "LowLifeTest_settings.json", text)
        assert store.read() == {}


def test_write_then_read_roundtrip_keeps_cyrillic_and_format(appdata):
    store = JsonStore("LowLifeTest_settings.json")
    assert store.write({u"b": u"Помещение", u"a": [1, 2]}) is True
    assert store.read() == {u"b": u"Помещение", u"a": [1, 2]}

    with io.open(store.path(), "r", encoding="utf-8") as f:
        text = f.read()
    # Формат тот же, что был в *_settings.py: кириллица как есть, ключи по
    # алфавиту, отступ 2 — файлы пользователей читаются без миграции.
    assert u"Помещение" in text
    assert text == json.dumps({u"b": u"Помещение", u"a": [1, 2]},
                              ensure_ascii=False, indent=2, sort_keys=True)


def test_update_keeps_other_keys(appdata):
    store = JsonStore("LowLifeTest_settings.json")
    store.write({"a": u"1", "b": u"2"})
    store.update({"b": u"3", "c": u"4"})
    assert store.read() == {"a": u"1", "b": u"3", "c": u"4"}


def test_write_failure_returns_false(appdata):
    store = JsonStore("LowLifeTest_settings.json")
    os.makedirs(store.path())  # на месте файла — папка, записать нельзя
    assert store.write({"a": 1}) is False


def test_callable_file_name_is_resolved_on_every_call(appdata):
    current = {"name": "A.json"}
    store = JsonStore(lambda: current["name"])
    store.write({"x": 1})
    current["name"] = "B.json"
    assert store.read() == {}
    store.write({"y": 2})
    current["name"] = "A.json"
    assert store.read() == {"x": 1}


def _settings(migrate=None):
    return TextSettings(
        file_name="LowLifeTest_settings.json",
        button_name=u"Кнопка",
        heading=u"Заголовок",
        transfer_label=u"теста",
        fields=[
            TextField("param", u"① Параметр", u"Имя параметра", required=True),
            TextField("mask", u"② Маска", u"Маска", default=u"Имя (Номер)"),
        ],
        migrate=migrate,
    )


def test_load_saved_values_uses_defaults_then_saved(appdata):
    settings = _settings()
    assert settings.load_saved_values() == {"param": u"", "mask": u"Имя (Номер)"}

    settings.save_values({"param": u"Этаж"})
    assert settings.load_saved_values() == {"param": u"Этаж", "mask": u"Имя (Номер)"}
    assert settings.get_settings_silent() == settings.load_saved_values()


def test_load_ignores_unknown_keys_but_save_keeps_them(appdata):
    _write_raw(appdata, "LowLifeTest_settings.json", u'{"old": "x", "param": "P"}')
    settings = _settings()
    assert settings.load_saved_values() == {"param": u"P", "mask": u"Имя (Номер)"}
    settings.save_values({"mask": u"Номер"})
    assert settings.store.read() == {"old": u"x", "param": u"P", "mask": u"Номер"}


def test_migrate_gets_raw_saved_and_edits_values(appdata):
    def migrate(saved, values):
        if not saved.get("mask") and saved.get("old_param"):
            values["mask"] = u"Имя ({})".format(saved["old_param"])

    _write_raw(appdata, "LowLifeTest_settings.json", u'{"old_param": "Номер_АР"}')
    assert _settings(migrate).load_saved_values()["mask"] == u"Имя (Номер_АР)"


def test_missing_reports_blank_keys_by_label_in_keys_order(appdata):
    settings = _settings()
    values = {"param": u"  ", "mask": u""}
    assert settings.missing(values, ["mask", "param"]) == [u"Маска", u"Имя параметра"]
    assert settings.missing({"param": u"X", "mask": u"Y"}, ["param", "mask"]) == []
    assert settings.missing({}, ["unknown"]) == ["unknown"]


def test_require_passes_silently_outside_revit(appdata):
    # Вне Revit forms.alert недоступен — require не должен падать.
    _settings().require({"param": u""}, ["param"])


def test_room_settings_modules_keep_their_files_and_api(appdata):
    from lowlife import room_finder_settings, room_info_settings, room_lots_settings

    expected = {
        room_lots_settings: "LowLifeRoomLots_settings.json",
        room_finder_settings: "LowLifeFindRoom_settings.json",
        room_info_settings: "LowLifeRoomInfo_settings.json",
    }
    for module, file_name in expected.items():
        assert os.path.basename(module.SETTINGS.store.path()) == file_name
        for name in ("load_saved_values", "save_values", "require",
                     "show_settings_form", "get_settings_interactive",
                     "get_settings_silent"):
            assert callable(getattr(module, name))


def test_room_info_migrates_old_room_number_param(appdata):
    from lowlife import room_info_settings

    _write_raw(appdata, "LowLifeRoomInfo_settings.json",
               u'{"room_number_param_name": "Номер_АР"}')
    values = room_info_settings.load_saved_values()
    assert values["room_mask"] == u"Имя (Номер_АР)"
    assert values["view_name_prefixes"] == u"1, 2, 20, 30, 60"


def test_module_imports_without_revit():
    assert settings_core.JsonStore is JsonStore


# --- NumberField ----------------------------------------------------------------

def test_number_field_parses_comma_and_checks_min():
    field = NumberField("x", u"Отступ, мм", u"", default=3.0, min_value=0)
    assert field.parse(u" 2,5 ") == 2.5
    assert field.parse(u"0") == 0.0
    assert field.parse(u"-1") is None
    assert field.parse(u"abc") is None
    assert field.parse(u"") is None
    assert field.requirement() == u"неотрицательное число"


def test_number_field_integer():
    field = NumberField("days", u"Период", u"", default=3, min_value=1, integer=True)
    assert field.parse(u"5") == 5 and isinstance(field.parse(u"5"), int)
    assert field.parse(u"2.5") is None
    assert field.parse(u"0") is None
    assert field.requirement() == u"целое число, не меньше 1"


def test_number_field_coerce_falls_back_to_default():
    field = NumberField("x", u"Отступ", u"", default=3.0, min_value=0)
    assert field.coerce(1.5) == 1.5
    assert field.coerce(u"4") == 4.0
    assert field.coerce(-2) == 3.0
    assert field.coerce(u"мусор") == 3.0
    assert field.coerce(None) == 3.0


def _mixed_settings(**kwargs):
    return TextSettings(
        file_name="LowLifeTest_settings.json",
        button_name=u"Кнопка",
        heading=u"Заголовок",
        transfer_label=u"теста",
        fields=[
            TextField("param", u"① Параметр", u"Имя параметра", required=True),
            NumberField("gap", u"Зазор, мм", u"", default=1.0, min_value=0),
        ],
        **kwargs
    )


def test_load_coerces_numbers_from_file(appdata):
    _write_raw(appdata, "LowLifeTest_settings.json", u'{"gap": "2,5"}')
    assert _mixed_settings().load_saved_values() == {"param": u"", "gap": 2.5}
    _write_raw(appdata, "LowLifeTest_settings.json", u'{"gap": -1}')
    assert _mixed_settings().load_saved_values()["gap"] == 1.0


def test_parse_form_returns_numbers_or_errors_by_title():
    settings = _mixed_settings()
    values, errors = settings.parse_form({"param": u"Этаж", "gap": u"0,5"})
    assert values == {"param": u"Этаж", "gap": 0.5} and errors == []

    values, errors = settings.parse_form({"param": u"", "gap": u"x"})
    # Без подписи поле называется заголовком раздела
    assert errors == [u"Зазор, мм — неотрицательное число"]
    assert values == {"param": u""}


def test_missing_treats_zero_as_filled():
    settings = _mixed_settings()
    assert settings.missing({"param": u"P", "gap": 0.0}, ["param", "gap"]) == []
    assert settings.missing({"param": u"P"}, ["gap"]) == [u"Зазор, мм"]


def test_equipment_tags_settings_defaults_and_bad_values(appdata):
    from lowlife import equipment_tags_settings

    defaults = {"offset_mm": 3.0, "gap_mm": 1.0, "shelf_mm": 3.0, "cluster_mm": 8.0}
    assert equipment_tags_settings.load_settings() == defaults
    assert os.path.basename(equipment_tags_settings.SETTINGS.store.path()) == \
        "LowLifeEquipmentTags_settings.json"

    _write_raw(appdata, "LowLifeEquipmentTags_settings.json",
               u'{"offset_mm": 5, "gap_mm": -2, "shelf_mm": "плохо", "other": 1}')
    loaded = equipment_tags_settings.load_settings()
    assert loaded == dict(defaults, offset_mm=5.0)
