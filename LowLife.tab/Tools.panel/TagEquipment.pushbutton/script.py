# -*- coding: utf-8 -*-

__title__ = u"Марки\nоборудования"
__doc__ = (
    u"Два режима. «Разложить марки» — выберите марки (или оборудование, "
    u"чьи марки двигать): они раскладываются ровно и без пересечений, "
    u"новые не создаются. «Поставить марки» — выберите оборудование: в "
    u"таблице по семействам укажите, что маркировать и каким типом марки "
    u"(выбор запоминается); новые марки сразу раскладываются. Выноска "
    u"идёт к УГО, а не к семейству.\n\n"
    u"Shift+клик — настройки (отступ, зазор, полка, что считать «рядом»)."
)
__author__ = "Pipers"

import traceback

from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, EXEC_PARAMS
from lowlife import select_list

from lowlife import equipment_tags, equipment_tags_settings, equipment_tags_form
from lowlife import tag_leader_follow

doc = revit.doc
uidoc = revit.uidoc

MODE_LAYOUT = u"Разложить выбранные марки"
MODE_CREATE = u"Поставить марки на оборудование"


def preselected():
    return [e for e in (doc.GetElement(i) for i in uidoc.Selection.GetElementIds())
            if e is not None]


def choose_mode(picked):
    """Только марки в выделении — сразу «разложить»; иначе спросить."""
    has_tags = any(isinstance(e, equipment_tags.IndependentTag) for e in picked)
    has_equipment = any(equipment_tags.is_equipment(e) for e in picked)
    if has_tags and not has_equipment:
        return MODE_LAYOUT
    mode = select_list.CommandSwitchWindow.show(
        [MODE_LAYOUT, MODE_CREATE],
        message=u"Марки оборудования — что сделать?"
    )
    if not mode:
        forms.alert(u"Отменено.", exitscript=True)
    return mode


def pick(selection_filter, prompt):
    try:
        refs = uidoc.Selection.PickObjects(ObjectType.Element, selection_filter, prompt)
    except OperationCanceledException:
        forms.alert(u"Выбор отменён.", exitscript=True)
    return [doc.GetElement(r) for r in refs]


def layout_entries(view, picked):
    """Режим «Разложить»: только выбранные марки (у выбранного
    оборудования — все его марки на виде)."""
    pairs = equipment_tags.resolve_tag_pairs(doc, view, picked)
    if not pairs:
        picked = pick(equipment_tags.TagFilter(),
                      u"Выберите марки оборудования (рамкой и/или кликами), Enter — готово")
        pairs = equipment_tags.resolve_tag_pairs(doc, view, picked)
    if not pairs:
        forms.alert(u"Среди выбранного нет марок оборудования.", exitscript=True)
    return [(el, tag, None) for el, tag in pairs]


def create_entries(view, picked):
    """Режим «Поставить»: оборудование без марки на виде → таблица по
    семействам (что маркировать и каким типом) → новые марки."""
    elements = equipment_tags.resolve_elements(
        doc, [e for e in picked if equipment_tags.is_equipment(e)])
    if not elements:
        elements = equipment_tags.resolve_elements(doc, pick(
            equipment_tags.EquipmentFilter(),
            u"Выберите оборудование (рамкой и/или кликами), Enter — готово"))
    if not elements:
        forms.alert(u"Не выбрано ни одного элемента оборудования.", exitscript=True)

    tagged = equipment_tags.tags_by_element(doc, view)
    untagged = [el for el in elements if equipment_tags.id_int(el.Id) not in tagged]
    skipped = len(elements) - len(untagged)
    if not untagged:
        forms.alert(u"У всего выбранного оборудования ({}) уже есть марки на этом "
                    u"виде. Чтобы переложить их — режим «{}».".format(skipped, MODE_LAYOUT),
                    exitscript=True)

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
        forms.alert(u"Отменено.", exitscript=True)
    equipment_tags_form.save_choice(groups, chosen)
    if not chosen:
        forms.alert(u"Ничего не выбрано для маркировки.", exitscript=True)

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
    forms.alert(u"Отменено, настройки не изменены." if edited is None
                else u"Настройки сохранены.", exitscript=True)

view = doc.ActiveView
if not equipment_tags.is_taggable_view(view):
    forms.alert(u"Откройте план, разрез или фасад — на этом виде марки "
                u"оборудования не ставятся.", exitscript=True)

settings = equipment_tags_settings.load_settings()
picked = preselected()
mode = choose_mode(picked)
if mode == MODE_LAYOUT:
    entries = layout_entries(view, picked)
else:
    entries = create_entries(view, picked)

# слежение выноски за УГО (обычно уже зарегистрировано хуком app-init)
following_ok = False
try:
    following_ok = tag_leader_follow.install(__revit__)  # noqa: F821
except Exception:
    pass

try:
    with revit.Transaction(u"Марки оборудования"):
        stats = equipment_tags.run(doc, view, entries, settings)
except Exception:
    forms.alert(
        u"Сбой при расстановке марок (транзакция отменена, изменения не "
        u"сохранены):\n\n{}".format(traceback.format_exc()),
        title=u"Марки оборудования", exitscript=True
    )

lines = [u"Разложено марок: {}".format(stats["moved"])]
if mode == MODE_CREATE:
    lines.append(u"Из них новых: {}".format(stats["created"]))
if stats["failed"]:
    lines.append(u"Не удалось поставить/сдвинуть: {} (нет подходящей марки "
                 u"для категории?)".format(stats["failed"]))
if stats["upper_floor"]:
    lines.append(u"Только верхний этаж (тип без «/» в двухэтажном "
                 u"семействе): {}".format(stats["upper_floor"]))
if stats["following"]:
    lines.append(u"Выноска на краю УГО, следует за прибором: {}{}".format(
        stats["following"], u"" if following_ok else
        u" (слежение не запустилось — перезапустите Revit)"))
if stats["no_symbol"]:
    lines.append(u"Без УГО — марка к семейству: {}".format(stats["no_symbol"]))
if stats["no_bbox"]:
    lines.append(u"Не видно на виде (пропущено): {}".format(stats["no_bbox"]))
if stats["overlaps"] or stats["crossings"]:
    lines.append(u"\nМеста не хватило: марок внахлёст — {}, пересечений "
                 u"выносок — {}. Попробуйте уменьшить «рядом» или "
                 u"отступ в настройках (Shift+клик) либо выбрать "
                 u"оборудование частями.".format(stats["overlaps"], stats["crossings"]))
forms.alert(u"\n".join(lines), title=u"Марки оборудования")
