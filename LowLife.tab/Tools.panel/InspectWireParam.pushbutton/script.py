# -*- coding: utf-8 -*-
__title__ = "Диагностика\nПроводник"
__doc__ = (
    "Тестовая кнопка: берёт первый найденный контроллер СКУД и его первую "
    "цепь, полностью описывает параметр «Проводник» этой цепи (StorageType, "
    "значения, связь с типом/глобальным параметром) в окно вывода pyRevit."
)
__author__ = "Pipers"

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from pyrevit import revit, forms, script as pyrevit_script

from lowlife.scs_circuits import norm
from lowlife.skud import is_controller
from lowlife import skud_settings
from lowlife.skud_settings import get_settings_silent
from lowlife.scs_settings import list_wire_types, _safe_element_name

doc = revit.doc
output = pyrevit_script.get_output()


def describe_parameter(p):
    lines = []
    lines.append("Name: {}".format(p.Definition.Name))
    lines.append("StorageType: {}".format(p.StorageType))
    lines.append("IsShared: {}".format(p.IsShared))
    lines.append("IsReadOnly: {}".format(p.IsReadOnly))
    try:
        lines.append("HasValue: {}".format(p.HasValue))
    except Exception as e:
        lines.append("HasValue failed: {}".format(e))

    try:
        lines.append("AsValueString(): {}".format(p.AsValueString()))
    except Exception as e:
        lines.append("AsValueString() failed: {}".format(e))

    if p.StorageType == StorageType.String:
        try:
            lines.append("AsString(): {}".format(p.AsString()))
        except Exception as e:
            lines.append("AsString() failed: {}".format(e))

    if p.StorageType == StorageType.ElementId:
        try:
            eid = p.AsElementId()
            lines.append("AsElementId(): {}".format(eid.IntegerValue if eid else None))
            if eid and eid.IntegerValue > 0:
                el = doc.GetElement(eid)
                lines.append("Referenced element: {} (class {})".format(
                    getattr(el, "Name", None), type(el).__name__
                ))
        except Exception as e:
            lines.append("AsElementId() failed: {}".format(e))

    if p.StorageType == StorageType.Integer:
        try:
            lines.append("AsInteger(): {}".format(p.AsInteger()))
        except Exception as e:
            lines.append("AsInteger() failed: {}".format(e))

    if p.StorageType == StorageType.Double:
        try:
            lines.append("AsDouble(): {}".format(p.AsDouble()))
        except Exception as e:
            lines.append("AsDouble() failed: {}".format(e))

    # Связь с глобальным параметром (если API это поддерживает)
    try:
        gp_id = p.GetAssociatedGlobalParameter()
        lines.append("GetAssociatedGlobalParameter(): {}".format(
            gp_id.IntegerValue if gp_id and gp_id.IntegerValue > 0 else None
        ))
        if gp_id and gp_id.IntegerValue > 0:
            gp = doc.GetElement(gp_id)
            lines.append("Global parameter name: {}".format(getattr(gp, "Name", None)))
    except Exception as e:
        lines.append("GetAssociatedGlobalParameter() failed/unavailable: {}".format(e))

    try:
        lines.append("Definition.ParameterType: {}".format(p.Definition.ParameterType))
    except Exception as e:
        lines.append("Definition.ParameterType failed: {}".format(e))

    try:
        lines.append("Definition.GetDataType(): {}".format(p.Definition.GetDataType()))
    except Exception as e:
        lines.append("Definition.GetDataType() failed/unavailable: {}".format(e))

    return lines


settings = get_settings_silent()

skud_settings.require(settings, [
    "controller_workset_keyword", "controller_type_keyword", "workset_param_name",
    "circuit_panel_param", "cable_type_param"
])

CONTROLLER_WORKSET_KEYWORD = settings["controller_workset_keyword"]
CONTROLLER_TYPE_KEYWORD = settings["controller_type_keyword"]
WORKSET_PARAM_NAME = settings["workset_param_name"]
CIRCUIT_PANEL_PARAM = settings["circuit_panel_param"]
CABLE_TYPE_PARAM = settings["cable_type_param"]

from lowlife.scs import get_workset_name, safe_element_name

all_equipment = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalEquipment) \
    .WhereElementIsNotElementType() \
    .ToElements()

wire_types = list_wire_types(doc)
output.print_md(u"### Способ 1: FilteredElementCollector(doc).OfClass(WireType) — найдено {}".format(len(wire_types)))
for wt in wire_types:
    output.print_md(u"- ID {}: name=`{}`".format(wt.Id.IntegerValue, _safe_element_name(wt)))

output.print_md(u"### Способ 2: OfCategory(OST_Wire).WhereElementIsElementType()")
try:
    wire_types_2 = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Wire)
        .WhereElementIsElementType()
        .ToElements()
    )
    output.print_md(u"Найдено {}".format(len(wire_types_2)))
    for wt in wire_types_2:
        output.print_md(u"- ID {}: name=`{}` class={}".format(
            wt.Id.IntegerValue, _safe_element_name(wt), type(wt).__name__
        ))
except Exception as ex:
    output.print_md(u"FAILED: {}".format(ex))

output.print_md(u"### Способ 3: сам ElementId 623487 через doc.GetElement")
try:
    wt_623487 = doc.GetElement(ElementId(623487))
    output.print_md(u"class={} name=`{}` Category=`{}`".format(
        type(wt_623487).__name__,
        _safe_element_name(wt_623487),
        wt_623487.Category.Name if wt_623487.Category else None
    ))
    try:
        output.print_md(u"GetType().FullName: {}".format(wt_623487.GetType().FullName))
    except Exception as ex2:
        output.print_md(u"GetType().FullName FAILED: {}".format(ex2))
    try:
        output.print_md(u"IsElementType(): {}".format(wt_623487.GetType()))
    except:
        pass
    try:
        fam = wt_623487.Family
        output.print_md(u"Family: {}".format(_safe_element_name(fam)))
    except Exception as ex2:
        output.print_md(u"Family FAILED/unavailable: {}".format(ex2))
    try:
        output.print_md(u"UniqueId: {}".format(wt_623487.UniqueId))
    except:
        pass
    try:
        bic = wt_623487.get_Parameter(BuiltInParameter.ELEM_CATEGORY_PARAM)
        output.print_md(u"ELEM_CATEGORY_PARAM: {}".format(bic.AsValueString() if bic else None))
    except Exception as ex2:
        output.print_md(u"ELEM_CATEGORY_PARAM FAILED: {}".format(ex2))

    output.print_md(u"Все параметры этого элемента:")
    try:
        for p2 in wt_623487.Parameters:
            try:
                pname2 = p2.Definition.Name
                pval2 = p2.AsValueString() or p2.AsString()
            except:
                pname2, pval2 = "?", "?"
            output.print_md(u"  - {} = {}".format(pname2, pval2))
    except Exception as ex2:
        output.print_md(u"  Parameters iteration FAILED: {}".format(ex2))

    output.print_md(u"В списке всех WhereElementIsElementType() присутствует ли этот ID?")
    try:
        all_types = FilteredElementCollector(doc).WhereElementIsElementType().ToElementIds()
        output.print_md(u"ID 623487 in all element types: {}".format(ElementId(623487) in all_types))
    except Exception as ex2:
        output.print_md(u"FAILED: {}".format(ex2))

    output.print_md(u"В списке всех WhereElementIsNotElementType() присутствует ли этот ID (т.е. это экземпляр, не тип)?")
    try:
        all_instances = FilteredElementCollector(doc).WhereElementIsNotElementType().ToElementIds()
        output.print_md(u"ID 623487 in all instances: {}".format(ElementId(623487) in all_instances))
    except Exception as ex2:
        output.print_md(u"FAILED: {}".format(ex2))
except Exception as ex:
    output.print_md(u"FAILED: {}".format(ex))

output.print_md(u"### Способ 5: все элементы документа с параметром «Ключевое имя»")
try:
    key_name_bip = None
    for bip_name in ["KEY_NAME", "KEYNOTE_KEY", "KEYSCHEDULE_KEY"]:
        try:
            key_name_bip = getattr(BuiltInParameter, bip_name)
            output.print_md(u"BuiltInParameter.{} существует".format(bip_name))
            break
        except:
            output.print_md(u"BuiltInParameter.{} НЕ существует".format(bip_name))

    if key_name_bip is not None:
        all_instances_els = FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
        key_elements = []
        for el in all_instances_els:
            try:
                p = el.get_Parameter(key_name_bip)
                if p and p.HasValue:
                    key_elements.append((el, p.AsString()))
            except:
                continue
        output.print_md(u"Найдено элементов с непустым «Ключевое имя»: {}".format(len(key_elements)))
        for el, key_val in key_elements[:30]:
            output.print_md(u"- ID {}: KeyName=`{}` class={}".format(
                el.Id.IntegerValue, key_val, type(el).__name__
            ))
        output.print_md(u"ID 623487 среди них: {}".format(
            any(el.Id.IntegerValue == 623487 for el, _ in key_elements)
        ))
except Exception as ex:
    output.print_md(u"Способ 5 FAILED: {}".format(ex))

output.print_md(u"### Способ 4: FilteredElementCollector без OfClass/OfCategory, фильтр по Category.Id == OST_Wire")
try:
    wire_cat_id = ElementId(BuiltInCategory.OST_Wire)
    all_types_candidates = FilteredElementCollector(doc).WhereElementIsElementType().ToElements()
    wire_types_4 = [
        t for t in all_types_candidates
        if t.Category is not None and t.Category.Id == wire_cat_id
    ]
    output.print_md(u"Найдено {} (из {} всего типов в документе)".format(
        len(wire_types_4), len(all_types_candidates)
    ))
    for wt in wire_types_4:
        output.print_md(u"- ID {}: name=`{}` class={}".format(
            wt.Id.IntegerValue, _safe_element_name(wt), type(wt).__name__
        ))
except Exception as ex:
    output.print_md(u"FAILED: {}".format(ex))

output.print_md(u"### Настройки поиска контроллера")
output.print_md(u"- workset_param_name: `{}`".format(WORKSET_PARAM_NAME))
output.print_md(u"- controller_workset_keyword: `{}`".format(CONTROLLER_WORKSET_KEYWORD))
output.print_md(u"- controller_type_keyword: `{}`".format(CONTROLLER_TYPE_KEYWORD))

output.print_md(u"### Все элементы OST_ElectricalEquipment ({})".format(len(all_equipment)))
for e in all_equipment:
    ws = get_workset_name(e, WORKSET_PARAM_NAME)
    try:
        type_name = safe_element_name(e.Symbol)
    except Exception as ex:
        type_name = "FAILED: {}".format(ex)
    try:
        is_ctrl = is_controller(e, WORKSET_PARAM_NAME, CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD)
    except Exception as ex:
        is_ctrl = "FAILED: {}".format(ex)
    output.print_md(u"- ID {}: name=`{}` workset=`{}` type_name=`{}` is_controller={}".format(
        e.Id.IntegerValue, e.Name, ws, type_name, is_ctrl
    ))

controllers = [
    e for e in all_equipment
    if is_controller(e, WORKSET_PARAM_NAME, CONTROLLER_WORKSET_KEYWORD, CONTROLLER_TYPE_KEYWORD)
]

if not controllers:
    forms.alert(u"Не найдено ни одного контроллера СКУД. Смотрите таблицу в окне вывода.", exitscript=True)

controller = controllers[0]
controller_name = norm(controller.Name)

output.print_md(u"### Контроллер: {} (ID {})".format(controller.Name, controller.Id.IntegerValue))

all_circuits = FilteredElementCollector(doc) \
    .OfCategory(BuiltInCategory.OST_ElectricalCircuit) \
    .WhereElementIsNotElementType() \
    .ToElements()

controller_circuits = []
for c in all_circuits:
    try:
        panel_name = norm(c.LookupParameter(CIRCUIT_PANEL_PARAM).AsValueString())
    except:
        panel_name = None
    if panel_name == controller_name:
        controller_circuits.append(c)

output.print_md(u"Цепей найдено для этого контроллера (по параметру «{}»): {}".format(
    CIRCUIT_PANEL_PARAM, len(controller_circuits)
))

if not controller_circuits:
    forms.alert(u"У контроллера {} не найдено ни одной цепи.".format(controller.Name), exitscript=True)

circuit = controller_circuits[0]

output.print_md(u"### Цепь: {} (ID {})".format(circuit.Name, circuit.Id.IntegerValue))

param = circuit.LookupParameter(CABLE_TYPE_PARAM)

if param is None:
    output.print_md(u"**LookupParameter(\"{}\") вернул None — параметра с таким именем нет у цепи.**".format(
        CABLE_TYPE_PARAM
    ))
else:
    output.print_md(u"### Параметр «{}»".format(CABLE_TYPE_PARAM))
    for line in describe_parameter(param):
        output.print_md(u"- {}".format(line))

# Дополнительно: все параметры цепи, содержащие слово "провод" в имени
output.print_md(u"### Все параметры цепи с «провод» в имени")
for p in circuit.Parameters:
    try:
        pname = p.Definition.Name
    except:
        continue
    if u"провод" in pname.lower():
        output.print_md(u"#### {}".format(pname))
        for line in describe_parameter(p):
            output.print_md(u"- {}".format(line))

forms.alert(u"Готово, смотрите окно вывода pyRevit.")
