# -*- coding: utf-8 -*-

__title__ = u"Марки\nоборудования"
__doc__ = (
    u"Ставит и раскладывает марки оборудования на активном виде ровно и "
    u"без пересечений. Выберите оборудование (или его марки) заранее либо "
    u"рамкой после нажатия. Рядом по горизонтали — марки стопкой друг над "
    u"другом с прямоугольными выносками-полками; одно над другим — колонкой "
    u"сбоку на одном отступе; одиночное — марка над ним с полкой. Сторона "
    u"выбирается так, чтобы марки не легли на другие марки и оборудование, "
    u"а выноски не пересекались. Недостающие марки создаются.\n\n"
    u"Shift+клик — настройки (отступ, зазор, полка, что считать «рядом»)."
)
__author__ = "Pipers"

import traceback

from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, EXEC_PARAMS

from lowlife import equipment_tags, equipment_tags_settings

doc = revit.doc
uidoc = revit.uidoc


class TypeOption(object):
    def __init__(self, symbol, is_default):
        self.symbol = symbol
        self.name = equipment_tags.tag_type_label(symbol)
        if is_default:
            self.name = u"{}  (по умолчанию)".format(self.name)

    def __str__(self):
        return self.name


def pick_elements():
    picked = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    elements = equipment_tags.resolve_elements(doc, [p for p in picked if p is not None])
    if elements:
        return elements
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, equipment_tags.EquipmentOrTagFilter(),
            u"Выберите оборудование или его марки (рамкой и/или кликами), Enter — готово"
        )
    except OperationCanceledException:
        forms.alert(u"Выбор отменён.", exitscript=True)
    elements = equipment_tags.resolve_elements(doc, [doc.GetElement(r) for r in refs])
    if not elements:
        forms.alert(u"Не выбрано ни одного элемента оборудования.", exitscript=True)
    return elements


def choose_tag_types(view, elements):
    """{id категории: ElementId типа марки или None} — только для
    категорий, где есть элементы без марки на этом виде."""
    existing = equipment_tags.existing_tags_by_element(doc, view)
    cats = {}
    for el in elements:
        if equipment_tags.id_int(el.Id) not in existing:
            cats[equipment_tags.id_int(el.Category.Id)] = el.Category

    result = {}
    for cat_id, cat in cats.items():
        types = equipment_tags.tag_types_for_category(doc, cat)
        default_id = equipment_tags.default_tag_type_id(doc, cat)
        if not types:
            result[cat_id] = None  # Revit сам попробует «по категории»
            continue
        if len(types) == 1:
            result[cat_id] = types[0].Id
            continue
        options = [TypeOption(s, default_id is not None and s.Id == default_id) for s in types]
        options.sort(key=lambda o: (not o.name.endswith(u"(по умолчанию)"), o.name.lower()))
        chosen = forms.SelectFromList.show(
            options,
            title=u"Марка для категории «{}»".format(cat.Name),
            button_name=u"Выбрать",
            multiselect=False
        )
        if not chosen:
            forms.alert(u"Отменено.", exitscript=True)
        result[cat_id] = chosen.symbol.Id
    return result


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
elements = pick_elements()
type_by_category = choose_tag_types(view, elements)

try:
    with revit.Transaction(u"Марки оборудования"):
        stats = equipment_tags.run(doc, view, elements, settings, type_by_category)
except Exception:
    forms.alert(
        u"Сбой при расстановке марок (транзакция отменена, изменения не "
        u"сохранены):\n\n{}".format(traceback.format_exc()),
        title=u"Марки оборудования", exitscript=True
    )

lines = [
    u"Разложено марок: {}".format(stats["moved"]),
    u"Из них новых: {}".format(stats["created"]),
]
if stats["failed"]:
    lines.append(u"Не удалось поставить/сдвинуть: {} (нет подходящей марки "
                 u"для категории?)".format(stats["failed"]))
if stats["no_bbox"]:
    lines.append(u"Не видно на виде (пропущено): {}".format(stats["no_bbox"]))
if stats["overlaps"] or stats["crossings"]:
    lines.append(u"\nМеста не хватило: марок внахлёст — {}, пересечений "
                 u"выносок — {}. Попробуйте уменьшить «рядом» или "
                 u"отступ в настройках (Shift+клик) либо выбрать "
                 u"оборудование частями.".format(stats["overlaps"], stats["crossings"]))
forms.alert(u"\n".join(lines), title=u"Марки оборудования")
