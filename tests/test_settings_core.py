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
from lowlife.settings_core import ChoiceField, JsonStore, NumberField, TextField, TextSettings


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


def _number_settings():
    return TextSettings(
        file_name="LowLifeTest_settings.json",
        button_name=u"Кнопка",
        heading=u"Заголовок",
        transfer_label=u"теста",
        fields=[
            NumberField("offset_mm", u"Отступ, мм", u"", default=3.0, minimum=0),
            NumberField("count", u"Количество", u"", default=5, integer=True),
            TextField("name", u"Имя", u"Имя параметра"),
        ],
    )


def test_number_field_parse_accepts_comma_and_checks_minimum():
    field = NumberField("offset_mm", u"Отступ, мм", u"", default=3.0, minimum=0)
    assert field.parse(u" 2,5 ") == (2.5, None)
    assert field.parse(u"0") == (0.0, None)
    value, error = field.parse(u"-1")
    assert value is None and u"Отступ, мм" in error and u"не меньше 0" in error
    value, error = field.parse(u"abc")
    assert value is None and error


def test_integer_number_field_rejects_fractions():
    field = NumberField("count", u"Количество", u"", default=5, integer=True)
    assert field.parse(u"7") == (7, None)
    assert field.parse(u"7.5")[0] is None


def test_number_values_load_as_numbers_and_bad_saved_values_fall_back(appdata):
    settings = _number_settings()
    assert settings.load_saved_values() == {"offset_mm": 3.0, "count": 5, "name": u""}

    _write_raw(appdata, "LowLifeTest_settings.json",
               u'{"offset_mm": -2, "count": "abc", "name": "X"}')
    assert settings.load_saved_values() == {"offset_mm": 3.0, "count": 5, "name": u"X"}

    _write_raw(appdata, "LowLifeTest_settings.json", u'{"offset_mm": "1,5", "count": 2}')
    values = settings.load_saved_values()
    assert values["offset_mm"] == 1.5 and values["count"] == 2


def test_parse_form_collects_errors_and_keeps_text_as_is():
    settings = _number_settings()
    values, errors = settings.parse_form(
        {"offset_mm": u"4", "count": u"x", "name": u" Этаж "})
    assert values == {"offset_mm": 4.0, "name": u" Этаж "}
    assert len(errors) == 1 and u"Количество" in errors[0]


def test_missing_uses_section_when_label_is_empty_and_zero_is_filled():
    settings = _number_settings()
    assert settings.missing({"offset_mm": 0.0, "name": u""}, ["offset_mm", "name"]) == [u"Имя параметра"]
    assert settings.missing({}, ["count"]) == [u"Количество"]


def test_field_display_turns_values_into_text():
    assert NumberField("a", u"A", u"").display(3.0) == u"3.0"
    assert TextField("b", u"B", u"").display(None) == u""


def test_equipment_tags_settings_keep_file_defaults_and_api(appdata):
    from lowlife import equipment_tags_settings

    assert os.path.basename(equipment_tags_settings.SETTINGS.store.path()) == \
        "LowLifeEquipmentTags_settings.json"
    assert equipment_tags_settings.load_settings() == {
        "offset_mm": 3.0, "gap_mm": 1.0, "shelf_mm": 3.0, "cluster_mm": 8.0}
    _write_raw(appdata, "LowLifeEquipmentTags_settings.json",
               u'{"offset_mm": 5.0, "gap_mm": -1}')
    loaded = equipment_tags_settings.load_settings()
    assert loaded["offset_mm"] == 5.0 and loaded["gap_mm"] == 1.0
    assert callable(equipment_tags_settings.get_settings_interactive)


def test_module_imports_without_revit():
    assert settings_core.JsonStore is JsonStore


# --- общие значения между кнопками --------------------------------------------

def test_shared_key_rule():
    assert settings_core.is_shared_key("wire_mark_param")
    assert settings_core.is_shared_key("level_param_name")
    assert not settings_core.is_shared_key("schematic_view_name")
    assert not settings_core.is_shared_key("route_type_id")
    assert not settings_core.is_shared_key("room_number_param_name")


# --- переименованные ключи -------------------------------------------------------

def test_rename_keys_moves_old_value_unless_new_is_filled():
    data = {"old_a": u"A", "old_b": u"B", "new_b": u"Своё", "old_c": u"", "x": 1}
    renames = {"old_a": "new_a", "old_b": "new_b", "old_c": "new_c", "old_d": "new_d"}
    assert settings_core.rename_keys(data, renames) is data
    assert data == {"new_a": u"A", "new_b": u"Своё", "x": 1}


def test_store_reads_and_writes_renamed_keys(appdata):
    _write_raw(appdata, "LowLifeR_settings.json",
               u'{"address_param_name": "Адрес", "keep": "1"}')
    store = JsonStore("LowLifeR_settings.json",
                      renames={"address_param_name": "device_address_param"})
    saved = store.read()
    assert dict(saved) == {"device_address_param": u"Адрес", "keep": u"1"}

    # запись (например, импорт старого выгруженного файла) — тоже по новым ключам
    store.write({"address_param_name": u"Другой"})
    assert dict(store.read()) == {"device_address_param": u"Другой"}
    # и в общую память попадает новый ключ
    assert settings_core.read_shared().get("device_address_param") == u"Другой"


def test_param_entered_in_one_button_is_default_in_another(appdata):
    scs = JsonStore("LowLifeA_settings.json")
    skud = JsonStore("LowLifeB_settings.json")
    scs.update({"wire_mark_param": u"Марка", "schematic_view_name": u"Схема СКС"})

    saved = skud.read()
    assert saved == {}  # в сам файл ничего не попало
    assert saved.get("wire_mark_param", u"") == u"Марка"
    assert saved.get("wire_mark_param") == u"Марка"
    # не имя параметра — не делится
    assert saved.get("schematic_view_name", u"") == u""


def test_shared_value_fills_blank_but_not_own_value_or_nonempty_default(appdata):
    a = JsonStore("LowLifeA_settings.json")
    b = JsonStore("LowLifeB_settings.json")
    b.write({"wire_mark_param": u"", "load_name_param": u"Своё"})
    a.update({"wire_mark_param": u"Марка", "load_name_param": u"Чужое",
              "cable_type_param": u"Кабель"})

    saved = b.read()
    assert saved.get("wire_mark_param", u"") == u"Марка"  # пусто в файле — подставляется
    assert saved.get("load_name_param", u"") == u"Своё"
    # у модуля свой непустой default — его не перекрываем
    assert saved.get("cable_type_param", u"По умолчанию") == u"По умолчанию"
    assert saved["wire_mark_param"] == u""  # [] и `in` — как у обычного dict


def test_rewriting_unchanged_values_does_not_overwrite_newer_shared(appdata):
    a = JsonStore("LowLifeA_settings.json")
    b = JsonStore("LowLifeB_settings.json")
    a.update({"wire_mark_param": u"Старое"})
    b.update({"wire_mark_param": u"Новое"})
    a.update({"something_else": 1})  # перезапись файла A со старым значением

    assert settings_core.read_shared()["wire_mark_param"] == u"Новое"
    assert JsonStore("LowLifeC_settings.json").read().get("wire_mark_param") == u"Новое"


def test_text_settings_pick_up_shared_values(appdata):
    JsonStore("LowLifeOther_settings.json").update({"lot_param_name": u"Имя лота"})
    settings = TextSettings(
        file_name="LowLifeLots_settings.json", button_name=u"Б", heading=u"З",
        transfer_label=u"т",
        fields=[TextField("lot_param_name", u"①", u"Имя лота", required=True)],
    )
    assert settings.get_settings_silent() == {"lot_param_name": u"Имя лота"}


def test_store_without_share_ignores_shared_values(appdata):
    JsonStore("LowLifeA_settings.json").update({"wire_mark_param": u"Марка"})
    plain = JsonStore("LowLifeB_settings.json", share=False)
    assert plain.read().get("wire_mark_param") is None
    plain.write({"wire_mark_param": u"Другое"})
    assert settings_core.read_shared()["wire_mark_param"] == u"Марка"


def test_choice_field_labels_values_and_legacy():
    f = ChoiceField("kind", u"Вид", u"", [("a", u"Первый"), ("b", u"Второй")],
                    legacy={2: "b", u"2": "b", 1: "a"})
    assert f.default == "a"
    assert f.labels() == [u"Первый", u"Второй"]
    assert f.display("b") == u"Второй"
    assert f.parse(u"Второй") == ("b", None)
    value, error = f.parse(u"нет такого")
    assert value is None and error
    assert f.coerce("b") == "b"
    assert f.coerce(2) == "b"            # старое числовое значение
    assert f.coerce(2.0) == "b"
    assert f.coerce(u"2") == "b"
    assert f.coerce(u"мусор") == "a"     # битое — умолчание
    assert f.display(None) == u"Первый"
