# -*- coding: utf-8 -*-

__title__ = u"Марки\nоборудования"
__doc__ = (
    u"Три режима. «Разложить марки» — выберите марки (или оборудование, "
    u"чьи марки двигать): они раскладываются ровно и без пересечений, "
    u"новые не создаются. «Поставить марки» — выберите оборудование: в "
    u"таблице по семействам укажите, что маркировать и каким типом марки "
    u"(выбор запоминается); новые марки сразу раскладываются. Выноска "
    u"идёт к УГО, а не к семейству.\n\n"
    u"«Маркировать оборудование смежной модели» — выбрать связи и поставить "
    u"марки на их оборудование, видимое на текущем виде (Revit 2024+). "
    u"«Маркировка шахт по примеру» — выбрать марку шахты и уровни, затем "
    u"создать такие же типы марок и автоматически разложить их на планах.\n\n"
    u"Shift+клик — настройки (отступ, зазор, полка, что считать «рядом»)."
)
__author__ = "Pipers"

import traceback
from lowlife.i18n import tr

from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, EXEC_PARAMS, script
from lowlife import select_list

from lowlife import equipment_tags, equipment_tags_settings, equipment_tags_form, geometry
from lowlife import tag_leader_follow

doc = revit.doc
uidoc = revit.uidoc

MODE_LAYOUT = tr(u"Разложить выбранные марки")
MODE_CREATE = tr(u"Поставить марки на оборудование")
MODE_LINK = tr(u"Маркировать оборудование смежной модели")
MODE_SHAFT = tr(u"Маркировка шахт по примеру", u"Tag shafts by example")


def preselected():
    return [e for e in (doc.GetElement(i) for i in uidoc.Selection.GetElementIds())
            if e is not None]


def choose_mode(picked):
    """Только несколько марок — сразу «разложить»; одну можно взять примером."""
    tags = [e for e in picked if isinstance(e, equipment_tags.IndependentTag)]
    has_tags = bool(tags)
    has_equipment = any(equipment_tags.is_equipment(e) for e in picked)
    if has_tags and not has_equipment:
        if len(tags) != 1:
            return MODE_LAYOUT
        mode = select_list.CommandSwitchWindow.show(
            [MODE_LAYOUT, MODE_SHAFT],
            message=tr(u"Марка оборудования — что сделать?",
                       u"Equipment tag — what to do?"))
        if not mode:
            forms.alert(tr(u"Отменено."), exitscript=True)
        return mode
    mode = select_list.CommandSwitchWindow.show(
        [MODE_LAYOUT, MODE_CREATE, MODE_LINK, MODE_SHAFT],
        message=tr(u"Марки оборудования — что сделать?")
    )
    if not mode:
        forms.alert(tr(u"Отменено."), exitscript=True)
    return mode


def pick(selection_filter, prompt):
    try:
        refs = uidoc.Selection.PickObjects(ObjectType.Element, selection_filter, prompt)
    except OperationCanceledException:
        forms.alert(tr(u"Выбор отменён."), exitscript=True)
    return [doc.GetElement(r) for r in refs]


def pick_one(selection_filter, prompt):
    try:
        reference = uidoc.Selection.PickObject(ObjectType.Element, selection_filter, prompt)
    except OperationCanceledException:
        forms.alert(tr(u"Выбор отменён."), exitscript=True)
    return doc.GetElement(reference)


class LevelOption(object):
    def __init__(self, level):
        self.level = level
        elevation_mm = float(level.Elevation) * 304.8
        self.name = u"{} ({:+.0f} мм)".format(geometry.level_name(level), elevation_mm)


def choose_example_tag(picked):
    tags = [item for item in picked if isinstance(item, equipment_tags.IndependentTag)]
    tag = tags[0] if len(tags) == 1 else pick_one(
        equipment_tags.TagFilter(),
        tr(u"Выберите одну марку как пример, Esc — отмена.",
           u"Select one tag as the example, Esc — cancel."))
    targets = [target for target in equipment_tags.tagged_equipment(doc, tag)
               if target is not None and equipment_tags.is_equipment(target)
               and not isinstance(target, equipment_tags.LinkedEquipment)]
    if len(targets) != 1:
        forms.alert(
            tr(u"Пример должен указывать ровно на один элемент текущей модели.",
               u"The example tag must point to exactly one local model element."),
            exitscript=True)
    return tag, equipment_tags.family_group(targets[0])


def choose_levels():
    levels = geometry.get_document_levels(doc)
    if not levels:
        forms.alert(tr(u"В проекте нет уровней.", u"The project has no levels."),
                    exitscript=True)
    chosen = select_list.SelectFromList.show(
        [LevelOption(level) for level in levels],
        title=tr(u"Уровни для маркировки шахт", u"Levels for shaft tagging"),
        button_name=tr(u"Маркировать", u"Tag"),
        multiselect=True,
        checked_only=True)
    if not chosen:
        forms.alert(tr(u"Уровни не выбраны.", u"No levels selected."), exitscript=True)
    return [option.level for option in chosen]


def shaft_jobs(view, example_tag, example_group, levels):
    jobs = []
    skipped = []
    tag_type_id = example_tag.GetTypeId()
    for level in levels:
        target_view, candidates = equipment_tags.matching_plan_view(doc, level, view)
        if target_view is None:
            skipped.append((geometry.level_name(level), candidates))
            continue
        elements, entries, pinned = equipment_tags.example_entries(
            doc, target_view, example_group, tag_type_id)
        if not elements:
            skipped.append((geometry.level_name(level), candidates))
            continue
        if entries or pinned:
            jobs.append((target_view, entries, len(elements), pinned))
    return jobs, skipped


def _shaft_summary(results, skipped, following_ok):
    lines = []
    created = moved = failed = 0
    for target_view, stats, count, pinned in results:
        created += stats["created"]
        moved += stats["moved"]
        failed += stats["failed"]
        suffix = tr(u", закреплено {}", u", pinned {}").format(pinned) if pinned else u""
        lines.append(u"{}: элементов {}, создано {}, разложено {}{}".format(
            target_view.Name, count, stats["created"], stats["moved"], suffix))
    lines.insert(0, tr(u"Создано марок: {}, разложено: {}.",
                        u"Tags created: {}, arranged: {}.").format(created, moved))
    if failed:
        lines.append(tr(u"Ошибок: {}.", u"Errors: {}.").format(failed))
    if skipped:
        lines.append(tr(u"Пропущены уровни без однозначного плана: {}.",
                        u"Levels without an unambiguous plan were skipped: {}.").format(
            u", ".join(name for name, _candidates in skipped)))
    if not following_ok:
        lines.append(tr(u"Следящие выноски не установлены — это ограничение Revit.",
                        u"Leader following is unavailable due to a Revit limitation."))
    return lines


def run_shaft_mode(view, picked, settings):
    if not isinstance(view, equipment_tags.ViewPlan):
        forms.alert(tr(u"Для маркировки шахт откройте план этажа.",
                       u"Open a floor plan to tag shafts."), exitscript=True)
    example_tag, example_group = choose_example_tag(picked)
    levels = choose_levels()
    jobs, skipped = shaft_jobs(view, example_tag, example_group, levels)
    if not jobs:
        forms.alert(
            tr(u"На выбранных уровнях не найдено подходящих планов или элементов.",
               u"No matching plans or elements were found on the selected levels."),
            exitscript=True)

    following_ok = False
    try:
        following_ok = tag_leader_follow.install(__revit__)  # noqa: F821
    except Exception:
        pass

    results = []
    try:
        with revit.Transaction(tr(u"Маркировка шахт по примеру",
                                 u"Tag shafts by example")):
            for target_view, entries, count, pinned in jobs:
                stats = equipment_tags.run(doc, target_view, entries, settings)
                results.append((target_view, stats, count, pinned))
    except Exception:
        forms.alert(
            tr(u"Ошибка маркировки шахт (транзакция отменена):\n\n{}",
               u"Shaft tagging failed (transaction rolled back):\n\n{}").format(
                   traceback.format_exc()),
            title=tr(u"Маркировка шахт", u"Shaft tagging"), exitscript=True)
    forms.alert(u"\n".join(_shaft_summary(results, skipped, following_ok)),
                title=tr(u"Маркировка шахт", u"Shaft tagging"))


def layout_entries(view, picked):
    """Режим «Разложить»: только выбранные марки (у выбранного
    оборудования — все его марки на виде)."""
    pairs = equipment_tags.resolve_tag_pairs(doc, view, picked)
    if not pairs:
        picked = pick(equipment_tags.TagFilter(),
                      tr(u"Выберите марки оборудования (рамкой и/или кликами), Enter — готово"))
        pairs = equipment_tags.resolve_tag_pairs(doc, view, picked)
    if not pairs:
        forms.alert(tr(u"Среди выбранного нет марок оборудования."), exitscript=True)
    return [(el, tag, None) for el, tag in pairs]


def create_entries(view, picked, elements=None):
    """Режим «Поставить»: оборудование без марки на виде → таблица по
    семействам (что маркировать и каким типом) → новые марки."""
    if elements is None:
        elements = equipment_tags.resolve_elements(
            doc, [e for e in picked if equipment_tags.is_equipment(e)])
    else:
        return choose_tag_entries(view, elements)
    if not elements:
        elements = equipment_tags.resolve_elements(doc, pick(
            equipment_tags.EquipmentFilter(),
            tr(u"Выберите оборудование (рамкой и/или кликами), Enter — готово")))
    if not elements:
        forms.alert(tr(u"Не выбрано ни одного элемента оборудования."), exitscript=True)

    return choose_tag_entries(view, elements)


def choose_tag_entries(view, elements):
    tagged = equipment_tags.tags_by_element(doc, view)
    untagged = [el for el in elements if equipment_tags.equipment_key(el) not in tagged]
    skipped = len(elements) - len(untagged)
    if not untagged:
        return []  # Новых нет: уже стоящие марки всё равно участвуют в раскладке.

    by_group = {}
    for el in untagged:
        by_group.setdefault(equipment_tags.family_group(el), []).append(el)

    saved = equipment_tags_form.load_saved()
    options_by_cat = {}
    groups = []
    for key in sorted(by_group):
        els = by_group[key]
        cat = els[0].Category
        cat_key = equipment_tags.id_int(cat.Id)
        if cat_key not in options_by_cat:
            types = equipment_tags.tag_types_for_category(doc, cat)
            default_id = equipment_tags.default_tag_type_id(doc, cat)
            types.sort(key=lambda s: default_id is None or s.Id != default_id)
            options_by_cat[cat_key] = [(equipment_tags.tag_type_label(s), s.Id) for s in types]
        options = options_by_cat[cat_key]
        family = key[1]
        if family in saved:
            default = saved[family] or None
        else:
            default = options[0][0] if options else None
        groups.append(equipment_tags_form.TagGroup(
            key, key[0], family, len(els), options, default))

    chosen = equipment_tags_form.show_groups(groups, skipped)
    if chosen is None:
        forms.alert(tr(u"Отменено."), exitscript=True)
    equipment_tags_form.save_choice(groups, chosen)
    if not chosen:
        forms.alert(tr(u"Ничего не выбрано для маркировки."), exitscript=True)

    entries = []
    for key, type_id in chosen.items():
        for el in by_group[key]:
            entries.append((el, None, type_id))
    return entries


try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False

if config_mode:
    edited = equipment_tags_settings.get_settings_interactive()
    forms.alert(tr(u"Отменено, настройки не изменены.") if edited is None
                else tr(u"Настройки сохранены."), exitscript=True)

view = doc.ActiveView
if not equipment_tags.is_taggable_view(view):
    forms.alert(tr(u"Откройте план, разрез или фасад — на этом виде марки "
                u"оборудования не ставятся."), exitscript=True)

settings = equipment_tags_settings.load_settings()
picked = preselected()
mode = choose_mode(picked)
if mode == MODE_SHAFT:
    run_shaft_mode(view, picked, settings)
    script.exit()
elif mode == MODE_LAYOUT:
    entries = layout_entries(view, picked)
elif mode == MODE_LINK:
    from lowlife import equipment_tags_links
    if int(doc.Application.VersionNumber) < 2024:
        forms.alert(tr(u"Маркировка видимого оборудования связей требует Revit 2024 или новее."),
                    exitscript=True)
    links = equipment_tags_links.visible_links(doc, view)
    labels = dict((u"{} [Id {}]".format(equipment_tags._safe_name(link),
                                       equipment_tags.id_int(link.Id)), link) for link in links)
    if not labels:
        forms.alert(tr(u"На текущем виде нет загруженных видимых связанных моделей."), exitscript=True)
    selected = select_list.SelectFromList.show(
        sorted(labels), title=tr(u"Выберите смежные модели"), multiselect=True)
    if not selected:
        forms.alert(tr(u"Отменено."), exitscript=True)
    elements = []
    for label in selected:
        elements.extend(equipment_tags_links.visible_equipment(doc, view, labels[label]))
    if not elements:
        forms.alert(tr(u"В выбранных моделях нет оборудования, видимого на текущем виде."), exitscript=True)
    entries = create_entries(view, [], elements=elements)
else:
    entries = create_entries(view, picked)

if mode in (MODE_CREATE, MODE_LINK):
    entries = equipment_tags.include_existing_tags(doc, view, entries)

# слежение выноски за УГО (обычно уже зарегистрировано хуком app-init)
following_ok = False
try:
    following_ok = tag_leader_follow.install(__revit__)  # noqa: F821
except Exception:
    pass

try:
    with revit.Transaction(tr(u"Марки оборудования")):
        stats = equipment_tags.run(doc, view, entries, settings)
except Exception:
    forms.alert(
        tr(u"Сбой при расстановке марок (транзакция отменена, изменения не "
        u"сохранены):\n\n{}").format(traceback.format_exc()),
        title=tr(u"Марки оборудования"), exitscript=True
    )

lines = [tr(u"Разложено марок: {}").format(stats["moved"])]
if mode in (MODE_CREATE, MODE_LINK):
    lines.append(tr(u"Из них новых: {}").format(stats["created"]))
if stats["failed"]:
    lines.append(tr(u"Не удалось поставить/сдвинуть: {} (нет подходящей марки "
                 u"для категории?)").format(stats["failed"]))
if stats["upper_floor"]:
    lines.append(tr(u"Только верхний этаж (тип без «/» в двухэтажном "
                 u"семействе): {}").format(stats["upper_floor"]))
if stats["following"]:
    lines.append(tr(u"Выноска на краю УГО, следует за прибором: {}{}").format(
        stats["following"], u"" if following_ok else
        tr(u" (слежение не запустилось — перезапустите Revit)")))
if stats["no_symbol"]:
    lines.append(tr(u"Без УГО — марка к семейству: {}").format(stats["no_symbol"]))
if stats["no_bbox"]:
    lines.append(tr(u"Не видно на виде (пропущено): {}").format(stats["no_bbox"]))
if stats["overlaps"] or stats["crossings"]:
    lines.append(tr(u"\nМеста не хватило: марок внахлёст — {}, пересечений "
                 u"выносок — {}. Попробуйте уменьшить «рядом» или "
                 u"отступ в настройках (Shift+клик) либо выбрать "
                 u"оборудование частями.").format(stats["overlaps"], stats["crossings"]))
forms.alert(u"\n".join(lines), title=tr(u"Марки оборудования"))

