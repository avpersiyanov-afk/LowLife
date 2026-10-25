# -*- coding: utf-8 -*-
"""Тесты выбора языка (lowlife.i18n) и английских подписей ленты (title_en/tooltip_en в bundle.yaml)."""

import os

import pytest

from lowlife import favorites_core, i18n, panel_themes, ribbon_catalog, ribbon_language

TAB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "LowLife.tab")


@pytest.fixture
def appdata(tmpdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmpdir))
    i18n._STORE = None
    i18n._CACHE.update({"mtime": None, "lang": None})
    yield tmpdir
    i18n._STORE = None
    i18n._CACHE.update({"mtime": None, "lang": None})


def test_russian_is_the_default(appdata):
    assert i18n.current() == i18n.RU
    assert i18n.tr(u"Цепи", u"Circuits") == u"Цепи"


def test_saved_language_is_used(appdata):
    assert i18n.save(i18n.EN) == i18n.EN
    assert i18n.current() == i18n.EN
    assert i18n.tr(u"Цепи", u"Circuits") == u"Circuits"
    assert i18n.tr(u"Только по-русски") == u"Только по-русски"  # перевода нет — русский
    assert i18n.pick({"ru": u"Да", "en": u"Yes"}) == u"Yes"
    assert i18n.save("de") is None and i18n.current() == i18n.EN


def _panel_folders():
    return [os.path.join(TAB, n) for n in sorted(os.listdir(TAB))
            if n.endswith(".panel") and not favorites_core.is_slot(n[:-len(".panel")])]


def _button_folders():
    for panel in _panel_folders():
        for root, dirs, _files in os.walk(panel):
            for d in dirs:
                if os.path.splitext(d)[1] in ribbon_catalog.BUTTON_EXTS:
                    folder = os.path.join(root, d)
                    if os.path.exists(os.path.join(folder, "bundle.yaml")) or \
                            os.path.exists(os.path.join(folder, "script.py")):
                        yield folder


def test_every_panel_has_an_english_title():
    missing = [os.path.basename(f) for f in _panel_folders() if not ribbon_catalog.item_title_en(f)]
    assert missing == []


def test_every_button_has_an_english_title_and_tooltip():
    # новая кнопка — сразу с title_en (и tooltip_en, если у неё есть подсказка) в bundle.yaml
    no_title, no_tooltip = [], []
    for folder in _button_folders():
        text = ribbon_catalog.raw_bundle_text(folder)
        name = os.path.relpath(folder, TAB)
        if not text[u"title_en"]:
            no_title.append(name)
        if (text[u"tooltip"] or ribbon_catalog._script_doc(folder)) and not text[u"tooltip_en"]:
            no_tooltip.append(name)
    assert no_title == []
    assert no_tooltip == []


def test_theme_list_has_english_labels_for_every_theme():
    members = ribbon_catalog.read_members_en(os.path.join(TAB, "_Themes.panel", "ThemeSelector.combobox"))
    assert sorted(members) == sorted(panel_themes.THEME_NAMES)
    assert all(m.get(u"text") for m in members.values())


def test_english_tooltip_keeps_pyrevit_tail():
    original = u"Подсказка\n\nBundle Name:\nКнопка (pushbutton)"
    assert ribbon_language.english_tooltip(original, u"Tooltip") == u"Tooltip\n\nBundle Name:\nКнопка (pushbutton)"
    assert ribbon_language.english_tooltip(u"Подсказка", u"Tooltip") == u"Tooltip"
    assert ribbon_language.english_tooltip(u"Подсказка", u"") == u"Подсказка"
    assert ribbon_language._ribbon_text(u"Route\\nnodes") == u"Route\nnodes"


def test_panel_index_is_keyed_by_the_russian_ribbon_name():
    index = ribbon_language.panel_index()
    folder, buttons = index[u"СКС"]
    assert folder.endswith(u"SCS.panel")
    assert u"PlaceRouteNodes" in buttons
    assert u"Search" in index[u"LowLife"][1]  # кнопки стека тоже


def test_search_finds_buttons_by_english_caption():
    found = ribbon_catalog.search(ribbon_catalog.list_buttons(), u"route nodes")
    assert found[0][u"button"] in (u"PlaceRouteNodes", u"PlaceSkudRouteNodes")
    entry = found[0]
    assert ribbon_catalog.localized(entry, u"title", u"en") == entry[u"title_en"]
    assert ribbon_catalog.localized(entry, u"title", u"ru") == entry[u"title"]
    assert entry[u"panel_title_en"]


def test_language_window_marks_current_and_maps_back():
    from lowlife import language_ui
    options = dict(language_ui._options(i18n.EN))
    assert options == {u"Русский": i18n.RU, u"✓ English": i18n.EN}
    assert language_ui.chosen_language(u"Русский", i18n.EN) == i18n.RU
    assert language_ui.chosen_language(u"✓ English", i18n.EN) == i18n.EN
    assert language_ui.chosen_language(u"Deutsch", i18n.EN) is None


def _tool():
    import importlib
    import sys
    tools = os.path.join(os.path.dirname(TAB), "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    return importlib.import_module("i18n_tool")


def test_every_marked_string_has_an_english_translation():
    # новая строка в tr(u"…")/N_(u"…") → python tools/i18n_tool.py extract --write и перевести в locale/en.json
    tool = _tool()
    assert tool.problems() == []


def test_tr_uses_the_catalog_only_in_english(appdata):
    assert i18n.tr(u"Сохранить") == u"Сохранить"
    i18n.save(i18n.EN)
    assert i18n.tr(u"Сохранить") == u"Save"
    assert i18n.tr(u"Нет такой строки в каталоге") == u"Нет такой строки в каталоге"
    assert i18n.tr(u"Найдено {}", u"Found {}").format(3) == u"Found 3"


def test_tr_translates_the_label_after_a_section_number(appdata):
    i18n.save(i18n.EN)
    assert i18n.tr(u"⑨ Сохранить") == u"⑨ Save"
    assert i18n.tr(u"⑨ Нет такой строки") == u"⑨ Нет такой строки"


def test_choice_field_round_trip_in_english(appdata):
    from lowlife import settings_core
    field = settings_core.ChoiceField("mode", u"", u"Подписи в помещениях",
                                      [("ceiling", u"только подвесные потолки (ПП)"), ("none", u"нет")])
    i18n.save(i18n.EN)
    assert field.labels() == [u"suspended ceilings only", u"no"]
    assert field.display("none") == u"no"
    assert field.parse(u"no") == ("none", None)
    assert field.title() == u"Labels in rooms"


def test_wrap_tool_wraps_ui_strings_but_not_data_or_metadata():
    tool = _tool()
    source = (u'__title__ = u"Кнопка"\n'
              u'import os\n'
              u'KEYWORDS = [u"стояк"]\n'
              u'def run(n):\n'
              u'    forms.alert(u"Найдено: {}".format(n))\n'
              u'    box.Text = u"Подпись"\n'
              u'    if value == u"стояк":\n'
              u'        pass\n')
    out, count = tool.wrap_source(source)
    assert count == 2
    assert u'__title__ = u"Кнопка"' in out
    assert u'from lowlife.i18n import tr\n' in out
    assert u'forms.alert(tr(u"Найдено: {}").format(n))' in out
    assert u'box.Text = tr(u"Подпись")' in out
    assert u'KEYWORDS = [u"стояк"]' in out and u'value == u"стояк"' in out


def test_library_does_not_translate_at_import_time():
    assert _tool().module_level_tr() == []


def test_ss1_labels_switch_language_without_changing_model_defaults(appdata):
    from lowlife import ss1_easy_settings as ss1
    before = ss1.load_all()
    ru_missing = ss1.missing_main({})
    i18n.save(i18n.EN)
    assert ss1.missing_main({}) == [
        u"Telecom shaft — family", u"Telecom shaft — checkbox",
        u"Cross-connect — family and type", u"Cable entry — family and type",
    ]
    assert ss1.load_all() == before
    assert ss1.DEFAULT_SHAFT_FLAG == u"СС"
    assert before["target_room_name"] == u"Прихожая"
    assert before["niche_text"] == u"Ниша СС"
    i18n.save(i18n.RU)
    assert ss1.missing_main({}) == ru_missing


def test_loi_status_and_mask_errors_follow_language_preserving_data(appdata):
    from lowlife import loi_check_core as loi, ss1_easy_core as ss1
    i18n.save(i18n.EN)
    assert loi.status_text(loi.ABSENT, None) == u"parameter missing"
    assert loi.status_text(loi.FILLED, u"Этаж 2") == u"Этаж 2"
    pairs, errors = ss1.parse_letter_params(u"А=Этаж; AB=Секция; C=")
    assert pairs == [(u"A", u"Этаж")]
    assert errors == [u"«AB=Секция» — the left side must contain one letter",
                      u"«C=» — no parameter specified"]
    i18n.save(i18n.RU)
    assert loi.status_text(loi.ABSENT, None) == u"нет параметра"


def test_mail_language_changes_labels_and_errors_but_preserves_requests(appdata):
    from lowlife import email_ai_core as ai, email_tasks_core as mail, email_tasks_run
    settings = {"provider": ai.OPENAI_API, "openai_api_model": u"gpt-5"}
    request = mail.build_request(u"Промпт пользователя", [], None)
    ru_label = ai.provider_label(settings["provider"])
    i18n.save(i18n.EN)
    assert ai.provider_label(settings["provider"]) == u"ChatGPT — OpenAI API (API key)"
    assert i18n.tr(email_tasks_run.TABLE_COLUMNS[1]) == u"Task"
    error = ai.classify_codex_failure(u"not logged in")
    assert error.fatal and u"not signed in" in error.message
    assert error.details == u"not logged in"
    assert mail.build_request(u"Промпт пользователя", [], None) == request
    assert settings == {"provider": ai.OPENAI_API, "openai_api_model": u"gpt-5"}
    i18n.save(i18n.RU)
    assert ai.provider_label(settings["provider"]) == ru_label


def test_catalog_extractor_reads_only_marked_xaml_captions(tmpdir):
    folder = tmpdir.mkdir('lib')
    folder.join('window.xaml').write_text(
        u'<!-- lowlife:i18n --><Window Title="Окно XAML">'
        u'<Hyperlink>Ссылка XAML</Hyperlink>'
        u'<DataTrigger Value="Статус XAML" Binding="{Binding status}"/></Window>',
        encoding='utf-8')
    folder.join('other.xaml').write_text(u'<Window Title="Не переведено"/>', encoding='utf-8')
    keys = _tool().extract_keys(str(tmpdir))
    assert set(keys) == {u'Окно XAML', u'Ссылка XAML'}
