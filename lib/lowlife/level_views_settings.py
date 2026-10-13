# -*- coding: utf-8 -*-
"""
Настройки кнопки «Виды по уровням» (Tools.panel/LevelViews) — хранение,
без WPF (окно — level_views_dialog.py).

JSON-файл %APPDATA%\\pyRevit\\LowLifeLevelViews_settings.json (обвязка —
settings_core.JsonStore):
  - groups              — список групп видов (level_views_core.GROUP_DEFAULTS);
  - level_name_template — шаблон имени уровня: {Этаж}/{Корпус}/{Комментарий}
                          в маске имени и поиск следующего этажа (верх
                          диапазона); пока не сохранён — берётся из настроек
                          «Секущего диапазона»;
  - last_levels / last_groups — что было отмечено в прошлый запуск (имена);
  - link_view_choices   — виды связей, выбранные в прошлый раз:
                          {группа: {связь: {уровень: вид связи или ""}}}.

Шаблоны и типы видов хранятся по имени, а не по ElementId — как в
family_section_settings.py: имя переносится между проектами, Id — нет.
"""

from lowlife import level_name_template, settings_core
from lowlife import level_views_core as core

SETTINGS_FILE_NAME = "LowLifeLevelViews_settings.json"

GROUPS_KEY = "groups"
LEVEL_TEMPLATE_KEY = "level_name_template"
LAST_LEVELS_KEY = "last_levels"
LAST_GROUPS_KEY = "last_groups"
LINK_CHOICES_KEY = "link_view_choices"

_VIEW_RANGE_FILE = "LowLifeViewRange_settings.json"

_STORE = settings_core.JsonStore(SETTINGS_FILE_NAME, label=u"видов по уровням")
_settings_file_path = _STORE.path
_read_all = _STORE.read
_write_all = _STORE.write


def _level_template_fallback():
    """Шаблон имени уровня «Секущего диапазона», иначе — по умолчанию."""
    other = settings_core.JsonStore(_VIEW_RANGE_FILE, share=False).read()
    value = (other.get(LEVEL_TEMPLATE_KEY) or u"").strip()
    if value and not level_name_template.validate(value):
        return value
    return level_name_template.DEFAULT_TEMPLATE


def _names(value):
    if not isinstance(value, (list, tuple)):
        return []
    return [v for v in value if isinstance(v, settings_core._string_types)]


def _choices(value):
    """{группа: {связь: {уровень: вид}}} — битые части отбрасываются."""
    result = {}
    if not isinstance(value, dict):
        return result
    for group, links in value.items():
        if not isinstance(links, dict):
            continue
        for link, levels in links.items():
            if not isinstance(levels, dict):
                continue
            clean = dict((k, v) for k, v in levels.items()
                         if isinstance(v, settings_core._string_types))
            result.setdefault(group, {})[link] = clean
    return result


def merge_choices(old, new):
    """Новый выбор поверх старого (уровни и связи, которых не было в окне, — остаются)."""
    merged = _choices(old)
    for group, links in (new or {}).items():
        for link, levels in links.items():
            merged.setdefault(group, {}).setdefault(link, {}).update(levels)
    return merged


def remember_link_choices(choices, filters):
    """
    Сохраняет выбор видов связей и фильтры, изменённые в окне выбора:
    filters — {группа: (вид фильтра, значение)}.
    """
    saved = _read_all()
    groups = core.normalize_groups(saved.get(GROUPS_KEY))
    for g in groups:
        if g[core.G_NAME] in filters:
            g[core.G_LINK_VIEW_MODE], g[core.G_LINK_VIEW_FILTER] = filters[g[core.G_NAME]]
    save_values({
        GROUPS_KEY: groups,
        LINK_CHOICES_KEY: merge_choices(saved.get(LINK_CHOICES_KEY), choices),
    })


def load_saved_values():
    saved = _read_all()
    level_tpl = (saved.get(LEVEL_TEMPLATE_KEY) or u"").strip()
    if not level_tpl or level_name_template.validate(level_tpl):
        level_tpl = _level_template_fallback()
    return {
        GROUPS_KEY: core.normalize_groups(saved.get(GROUPS_KEY)),
        LEVEL_TEMPLATE_KEY: level_tpl,
        LAST_LEVELS_KEY: _names(saved.get(LAST_LEVELS_KEY)),
        LAST_GROUPS_KEY: _names(saved.get(LAST_GROUPS_KEY)),
        LINK_CHOICES_KEY: _choices(saved.get(LINK_CHOICES_KEY)),
    }


def save_values(values):
    """Дописывает переданные ключи, остальные оставляет как есть."""
    return _STORE.update(values)


def remember_choice(level_names, group_names):
    save_values({LAST_LEVELS_KEY: list(level_names), LAST_GROUPS_KEY: list(group_names)})


def get_settings_silent():
    return load_saved_values()


def get_settings_interactive(doc):
    """Окно настроек (Shift+клик); сохраняет и возвращает значения, None — отмена."""
    from lowlife import level_views_dialog, settings_transfer

    while True:
        saved = load_saved_values()
        edited = level_views_dialog.show_settings_form(doc, saved, _read_all, _write_all)
        if edited == settings_transfer.RELOAD:
            continue
        if edited is None:
            return None
        save_values(edited)
        return load_saved_values()
