# -*- coding: utf-8 -*-
"""
Цепи «изолятор -> устройства» СПС.

В отличие от build_loop_circuits (fire_alarm_buttons.py) — весь шлейф целиком
по адресации панель.шлейф.номер — здесь состав каждой цепи выбирается
вручную: устройства пожарной сигнализации и изолятор (электрооборудование,
к которому их нужно подключить) выбираются вместе, одним PickObjects — среди
выбранного должен быть ровно один изолятор.

Правила группировки (см. docs/fire-alarm-panels.md):
- Каждое устройство ручного пуска (ИПР, «ручной» в имени типа) — отдельная
  цепь.
- Остальные выбранные устройства — одна общая цепь.
- У изолятора не может быть больше MAX_CIRCUITS_PER_ISOLATOR цепей: если по
  этим правилам получается больше — ничего не создаётся, кнопка сообщает об
  ошибке (жёсткий лимит, без частичного создания).

Каждой созданной цепи проставляются «Панель» (имя изолятора), «Имя нагрузки»
(обозначение + адрес устройства с наибольшим порядковым номером в цепи) и,
если в настройках задан параметр «Проводник», тип кабеля по категории
устройства — тем же способом, что и build_loop_circuits.
"""

from Autodesk.Revit.DB import BuiltInCategory
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms

from lowlife.scs import safe_element_name, classify_element
from lowlife.scs_circuits import clean_text_value, make_load_name
from lowlife.params import get_type_string_param, get_string_param, set_param_any, set_element_id_param
from lowlife.electrical_circuits import create_circuit
from lowlife.fire_alarm_circuits import device_category_id
from lowlife import fire_alarm_settings

MANUAL_DEVICE_KEYWORD = u"ручной"

MAX_CIRCUITS_PER_ISOLATOR = 2


class _CombinedSelectionFilter(ISelectionFilter):
    """Разрешает выбирать элементы из нескольких категорий текущего документа (не связанного файла)."""

    def __init__(self, categories):
        self._category_ids = set(int(c) for c in categories)

    def AllowElement(self, elem):
        try:
            if elem.Document.IsLinked:
                return False
        except:
            pass
        try:
            return elem.Category is not None and elem.Category.Id.IntegerValue in self._category_ids
        except:
            return False

    def AllowReference(self, reference, position):
        return True


def _is_isolator(el):
    try:
        return el.Category.Id.IntegerValue == int(BuiltInCategory.OST_ElectricalEquipment)
    except:
        return False


def pick_devices_and_isolator(uidoc, doc):
    """
    Выбор для новой цепи одним шагом: устройства пожарной сигнализации и
    изолятор (электрооборудование) вместе — рамкой и/или кликами с
    подтверждением Enter/«Готово». Среди выбранного должен быть ровно один
    изолятор; если это не так или не выбрано ни одного устройства, просит
    повторить выбор (тот же вызов, без отдельного запуска кнопки).

    Возвращает (device_els, isolator_el) либо (None, None), если
    пользователь отменил выбор (Esc) — это сигнал закончить цикл выбора
    (не ошибка).
    """
    combined_filter = _CombinedSelectionFilter([
        BuiltInCategory.OST_FireAlarmDevices, BuiltInCategory.OST_ElectricalEquipment
    ])

    while True:
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, combined_filter,
                u"Выберите устройства и изолятор (панель) одним выбором — "
                u"подтвердите Enter/«Готово», Esc — закончить"
            )
        except OperationCanceledException:
            return None, None

        els = [doc.GetElement(r) for r in refs]
        isolators = [el for el in els if _is_isolator(el)]
        device_els = [el for el in els if not _is_isolator(el)]

        if len(isolators) != 1:
            forms.alert(
                u"В выборе должен быть ровно один изолятор (электрооборудование), "
                u"а выбрано {}. Повторите выбор.".format(len(isolators))
            )
            continue

        if not device_els:
            forms.alert(u"Не выбрано ни одного устройства. Повторите выбор.")
            continue

        return device_els, isolators[0]


def is_manual_device(el):
    """Устройство ручного пуска (ИПР) — по слову «ручной» в имени семейства/типа."""
    return classify_element(el, [("manual", [MANUAL_DEVICE_KEYWORD], [])]) == "manual"


def split_manual_devices(device_els):
    """(ручные_устройства, обычные_устройства) — по имени типа."""
    manual = [d for d in device_els if is_manual_device(d)]
    other = [d for d in device_els if not is_manual_device(d)]
    return manual, other


def _address_suffix(raw_address):
    """Последнее число в адресе вида "3.1.2" -> 2, либо None."""
    if not raw_address:
        return None
    parts = unicode(raw_address).strip().split(u".")
    try:
        return int(parts[-1])
    except:
        return None


def _pick_load_device(device_els, address_param):
    """Устройство с наибольшим порядковым номером адреса — для имени нагрузки цепи."""
    best_device = None
    best_suffix = -1

    for el in device_els:
        raw = clean_text_value(get_string_param(el, address_param))
        suffix = _address_suffix(raw)
        if suffix is not None and suffix > best_suffix:
            best_suffix = suffix
            best_device = el

    return best_device or (device_els[0] if device_els else None)


def _apply_circuit_labels(doc, circuit, member_devices, isolator_el, config):
    """Проставляет цепи «Панель», «Имя нагрузки» и (если задан) «Проводник» по категории."""
    set_param_any(
        circuit, config["circuit_panel_param"],
        clean_text_value(safe_element_name(isolator_el)) or u""
    )

    load_device = _pick_load_device(member_devices, config["device_address_param"])
    if load_device is not None:
        designation = clean_text_value(get_type_string_param(doc, load_device, config["designation_param"]))
        address = clean_text_value(get_string_param(load_device, config["device_address_param"]))
        load_name = make_load_name(designation, address)
        if load_name:
            set_param_any(circuit, config["load_name_param"], load_name)

    if config.get("cable_type_param") and member_devices:
        category_wire_type_ids = fire_alarm_settings.get_category_wire_type_elem_ids(doc)
        cat_id = device_category_id(member_devices[0])
        wire_type_id = category_wire_type_ids.get(cat_id) if cat_id is not None else None
        if wire_type_id is not None:
            set_element_id_param(circuit, config["cable_type_param"], wire_type_id)


def build_isolator_device_circuits(doc, device_els, isolator_el, settings):
    """
    Строит цепи «изолятор -> устройства» по правилам группировки.

    Возвращает (created_circuits, error_message): error_message не None,
    если цепей получилось больше MAX_CIRCUITS_PER_ISOLATOR — тогда ничего
    не создаётся (жёсткий лимит).
    """
    config = dict(settings)

    manual_devices, other_devices = split_manual_devices(device_els)

    groups = [[d] for d in manual_devices]
    if other_devices:
        groups.append(other_devices)

    if len(groups) > MAX_CIRCUITS_PER_ISOLATOR:
        return [], (
            u"У изолятора «{}» получилось бы {} цепей (максимум {}): "
            u"{} ручных устройств + {} общая цепь на остальные. Цепи не "
            u"созданы — выберите устройства для отдельного изолятора за "
            u"несколько запусков кнопки.".format(
                clean_text_value(safe_element_name(isolator_el)) or isolator_el.Id.IntegerValue,
                len(groups), MAX_CIRCUITS_PER_ISOLATOR,
                len(manual_devices), 1 if other_devices else 0
            )
        )

    system_type_name = config["circuit_system_type"]
    created = []
    errors = []

    with revit.Transaction(u"Цепи изолятор-устройства СПС"):
        for group in groups:
            circuit, error = create_circuit(doc, isolator_el, group, system_type_name)

            if circuit is None:
                errors.append(u"{}: {}".format(
                    u", ".join(unicode(d.Id.IntegerValue) for d in group), error
                ))
                continue

            _apply_circuit_labels(doc, circuit, group, isolator_el, config)
            created.append(circuit)

            if error:
                errors.append(u"Цепь ID {}: {}".format(circuit.Id.IntegerValue, error))

    return created, (u"\n".join(errors) if errors else None)
