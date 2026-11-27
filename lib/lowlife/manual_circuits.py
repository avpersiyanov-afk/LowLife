# -*- coding: utf-8 -*-
"""
Тело кнопок ручного построения цепей «панель -> устройства» на панелях
CircuitsSCS/CircuitsGeneric/CircuitsSKUD. СКС и общая команда сначала
выбирают панель на плане или по имени, затем устройства. СКУД выбирает
панель и устройства вместе (рамкой и/или кликами) и создаёт
по одной отдельной цепи на каждое устройство (аналог «home run» —
без промежуточных узлов и адресации). Какой из выбранных элементов панель,
определяется автоматически по категории «Электрооборудование»
(OST_ElectricalEquipment) — тем же способом, что и выбор изолятора в
fire_alarm_isolator_circuits.pick_devices_and_isolator.

Логика не зависит от дисциплины — используется целиком
(run_manual_circuit_button) кнопкой СКУД (различаются только подписи и тип
цепи по умолчанию — его в любом случае можно поменять в диалоге при
запуске). СКС — особый случай: тип цепи определяется по коннектору
устройства, а не запрашивается в диалоге, и добавлен выбор проводника,
поэтому её кнопка использует только choose_panel_and_devices отсюда, а
остальное — из lowlife.scs_manual_circuits. СПА раньше тоже использовала
этот общий сценарий (заготовка, пока не было своей адресации), но теперь
строит цепи по адресу устройства как СПС — см. CircuitsSPA.panel и
fire_alarm_settings/fire_alarm_buttons.build_loop_circuits (система "SPA",
рабочий набор с ключевым словом «СПА»).
"""

from Autodesk.Revit.DB import BuiltInCategory, CategoryType
from lowlife.i18n import tr
from Autodesk.Revit.DB.Electrical import ElectricalSystemType
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms, script as pyrevit_script
from lowlife import select_list

from lowlife.circuit_builtins import panel_name
from lowlife.electrical_circuits import create_circuit
from lowlife.selection import pick_rectangle_then_clicks


class _NotLinkedSelectionFilter(ISelectionFilter):
    """Отсекает элементы связанных файлов — PickObject/PickObjects иначе даёт их выбрать."""

    def AllowElement(self, elem):
        try:
            return not elem.Document.IsLinked
        except:
            return True

    def AllowReference(self, reference, position):
        return True


# Категории, которые заведомо не подключаются в электрическую цепь и
# которые пользователь может случайно захватить рамкой при выборе панели
# и устройств: оси, уровни, текст, линии (модельные и детализации),
# обобщённые модели, обобщённые аннотации, вставки связанных файлов.
# Плюс отдельно (см. фильтр) отсекается вся аннотация целиком по
# CategoryType.Annotation — марки, размеры и т.п.
_EXCLUDED_PICK_CATEGORY_IDS = set(
    int(bic) for bic in (
        BuiltInCategory.OST_Grids,
        BuiltInCategory.OST_Levels,
        BuiltInCategory.OST_TextNotes,
        BuiltInCategory.OST_Lines,
        BuiltInCategory.OST_GenericModel,
        BuiltInCategory.OST_GenericAnnotation,
        BuiltInCategory.OST_RvtLinks,
    )
)


class _CircuitTargetSelectionFilter(ISelectionFilter):
    """
    Строгий фильтр выбора для кнопки «Цепь (общее)»: помимо элементов
    связанных файлов (как _NotLinkedSelectionFilter) отсекает заведомо
    не подключаемое — аннотации в целом, оси, уровни, текстовые
    аннотации, линии детализации, обобщённые модели.
    """

    def AllowElement(self, elem):
        try:
            if elem.Document.IsLinked:
                return False
        except:
            pass

        try:
            cat = elem.Category
        except:
            cat = None

        if cat is None:
            return False

        try:
            if cat.Id.IntegerValue in _EXCLUDED_PICK_CATEGORY_IDS:
                return False
        except:
            pass

        try:
            if cat.CategoryType == CategoryType.Annotation:
                return False
        except:
            pass

        return True

    def AllowReference(self, reference, position):
        return True


def _is_panel(el):
    try:
        return el.Category.Id.IntegerValue == int(BuiltInCategory.OST_ElectricalEquipment)
    except:
        return False


class _PanelSelectionFilter(_NotLinkedSelectionFilter):
    def AllowElement(self, elem):
        return _is_panel(elem) and super(_PanelSelectionFilter, self).AllowElement(elem)


class _DeviceSelectionFilter(_NotLinkedSelectionFilter):
    def __init__(self, strict):
        self.base_filter = (_CircuitTargetSelectionFilter() if strict
                            else _NotLinkedSelectionFilter())

    def AllowElement(self, elem):
        return not _is_panel(elem) and self.base_filter.AllowElement(elem)


def _choose_named_panel(doc):
    by_name = {}
    for panel in revit.query.get_elements_by_categories(
            [BuiltInCategory.OST_ElectricalEquipment], doc=doc):
        name = panel_name(panel).strip()
        if name:
            by_name.setdefault(name, []).append(panel)

    if not by_name:
        forms.alert(tr(u"В проекте нет оборудования с заполненным именем панели.",
                       u"No equipment in the project has a panel name."))
        return None

    by_label = {}
    for name, panels in by_name.items():
        for panel in panels:
            label = name if len(panels) == 1 else u"{} [ID {}]".format(name, panel.Id)
            by_label[label] = panel
    label = select_list.show_dropdown(sorted(by_label, key=lambda name: name.lower()),
                                      title=tr(u"Выбор панели", u"Select panel"))
    return by_label.get(label)


def choose_panel_and_devices(uidoc, doc, strict=False):
    """Выбирает панель, затем устройства. При отмене возвращает (None, [])."""
    on_plan = tr(u"Выбрать панель на плане", u"Pick a panel on the plan")
    from_list = tr(u"Показать список панелей", u"Show the panel list")
    mode = select_list.CommandSwitchWindow.show(
        [on_plan, from_list],
        message=tr(u"Как выбрать панель?", u"How would you like to select the panel?"),
    )
    if not mode:
        return None, []

    try:
        if mode == on_plan:
            reference = uidoc.Selection.PickObject(
                ObjectType.Element, _PanelSelectionFilter(),
                tr(u"Выберите панель на плане.", u"Pick a panel on the plan."))
            panel = doc.GetElement(reference)
        else:
            panel = _choose_named_panel(doc)
        if panel is None:
            return None, []
        devices = pick_rectangle_then_clicks(
            uidoc, doc, _DeviceSelectionFilter(strict),
            tr(u"Выберите устройства рамкой. Esc — перейти к одиночным кликам.",
               u"Select devices by dragging a window. Press Esc to skip to individual clicks."),
            tr(u"Устройств выбрано: {}. Клик — добавить или снять. Esc — завершить выбор.",
               u"Devices selected: {}. Click to add or remove. Press Esc to finish."))
    except OperationCanceledException:
        return None, []

    return panel, devices


def pick_panel_and_devices(uidoc, doc, prompt, strict=False):
    """
    Просит выбрать панель и устройства вместе, одним PickObjects (рамкой
    и/или кликами, подтверждение Enter/«Готово») — без определённого
    порядка. Среди выбранного панелью считается элемент категории
    «Электрооборудование» (OST_ElectricalEquipment), остальные —
    устройствами. Останавливает скрипт (forms.alert exitscript), если
    пользователь отменил выбор (Esc), если панель в выборе не ровно одна,
    или если не выбрано ни одного устройства.

    strict=True — использовать строгий фильтр выбора
    (_CircuitTargetSelectionFilter): дополнительно к элементам связанных
    файлов не даёт захватить аннотации, оси, уровни, текст, линии
    детализации и обобщённые модели. По умолчанию (для кнопок СКС/СКУД)
    фильтр прежний — только связанные файлы.
    """
    selection_filter = _CircuitTargetSelectionFilter() if strict else _NotLinkedSelectionFilter()

    try:
        refs = uidoc.Selection.PickObjects(ObjectType.Element, selection_filter, prompt)
    except OperationCanceledException:
        forms.alert(tr(u"Операция отменена."), exitscript=True)
        return None, None

    els = [doc.GetElement(r) for r in refs]
    panels = [el for el in els if _is_panel(el)]
    device_els = [el for el in els if not _is_panel(el)]

    if len(panels) != 1:
        forms.alert(
            tr(u"В выборе должна быть ровно одна панель (категория "
            u"«Электрооборудование»), а выбрано {}.").format(len(panels)),
            exitscript=True
        )
        return None, None

    if not device_els:
        forms.alert(tr(u"Не выбрано ни одного устройства."), exitscript=True)

    return panels[0], device_els


def pick_system_type(default_name):
    """
    Даёт выбрать тип электрической цепи Revit из доступных в этой версии
    (значение по умолчанию для дисциплины — первым в списке). Останавливает
    скрипт, если пользователь отменил выбор.
    """
    # dir(ElectricalSystemType) вперемешку с реальными значениями (Data,
    # Security, ...) выдаёт унаследованные от Enum методы (CompareTo,
    # Equals, Parse, ...) — отфильтровываем через isinstance, иначе они
    # тоже попали бы в список выбора.
    available = sorted(
        a for a in dir(ElectricalSystemType)
        if not a.startswith("_") and isinstance(getattr(ElectricalSystemType, a, None), ElectricalSystemType)
    )

    if not available:
        return default_name

    if default_name in available:
        available = [default_name] + [a for a in available if a != default_name]

    selected = select_list.SelectFromList.show(
        available,
        title=tr(u"Тип электрической цепи (по умолчанию для дисциплины — первый в списке)"),
        button_name=tr(u"Выбрать"),
        multiselect=False
    )

    if not selected:
        forms.alert(tr(u"Операция отменена."), exitscript=True)

    return selected


def build_device_circuits(doc, panel_el, device_els, system_type_name, transaction_name):
    """
    Создаёт по одной электрической цепи на каждое устройство, подключая
    его напрямую к панели.

    Возвращает (created_count, errors) — errors это список текстов ошибок
    по устройствам, которые не удалось подключить.
    """
    created = 0
    errors = []

    with revit.Transaction(transaction_name):
        for dev in device_els:
            circuit, error = create_circuit(doc, panel_el, [dev], system_type_name)

            if circuit is None:
                errors.append(tr(u"Устройство ID {}: {}").format(dev.Id.IntegerValue, error))
                continue

            created += 1

            if error:
                errors.append(tr(u"Устройство ID {}: {}").format(dev.Id.IntegerValue, error))

    return created, errors


def run_manual_circuit_button(discipline_title, default_system_type):
    """Полный сценарий кнопки: выбор панели/устройств, типа цепи, создание."""
    doc = revit.doc
    uidoc = revit.uidoc

    panel_el, device_els = pick_panel_and_devices(
        uidoc, doc,
        tr(u"Выберите панель и устройства {} вместе — рамкой и/или кликами, "
        u"без порядка (подтвердите Enter/«Готово»)").format(tr(discipline_title))
    )

    system_type_name = pick_system_type(default_system_type)

    created, errors = build_device_circuits(
        doc, panel_el, device_els, system_type_name,
        tr(u"Построение цепей {}").format(tr(discipline_title))
    )

    if errors:
        output = pyrevit_script.get_output()
        output.print_md(tr(u"### Ошибки ({})").format(len(errors)))
        for line in errors[:200]:
            output.print_md(u"- {}".format(line))

    forms.alert(
        tr(u"Готово.\n\nУстройств выбрано: {}\nЦепей создано: {}\nОшибок: {}\n\n{}").format(
            len(device_els), created, len(errors),
            tr(u"Подробности — в окне вывода pyRevit.") if errors else u""
        )
    )
