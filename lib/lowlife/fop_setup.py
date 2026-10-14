# -*- coding: utf-8 -*-
"""
Кнопка «Параметры в ФОП» (Tools.panel/FopParameters): создание определений
общих параметров в файле ФОП и их привязка к категориям проекта.

Что делать — строки fop_catalog.Row (имя, тип данных, экземпляр/тип,
категории), окно — fop_parameters_ui.py. Здесь только Revit API:

- connected_file(app) / open_file(app, path) / create_file(path) — ФОП,
  подключённый к Revit (Управление → Общие параметры).
- add_and_bind(doc, app, sp_file, group_name, rows) — для каждой строки:
  определение берётся из ФОП (в любой группе) или создаётся в группе
  group_name с нужным типом данных; затем параметр привязывается к
  категориям строки (к уже существующей привязке категории добавляются,
  прежние сохраняются). Определения пишутся в ФОП до транзакции, привязки —
  в одной транзакции.

Совместимость: Revit 2022+ — SpecTypeId/GroupTypeId (ForgeTypeId), раньше —
ParameterType/BuiltInParameterGroup; 2025+ — только ForgeTypeId.
"""

import io
import os

from Autodesk.Revit.DB import (
    BuiltInCategory, ExternalDefinitionCreationOptions, TypeBinding, Transaction
)

from lowlife import fop_catalog

try:
    from Autodesk.Revit.DB import SpecTypeId, GroupTypeId
except ImportError:  # Revit 2021 и старше
    SpecTypeId = None
    GroupTypeId = None

try:
    from Autodesk.Revit.DB import ParameterType
except ImportError:  # Revit 2025+
    ParameterType = None

try:
    from Autodesk.Revit.DB import BuiltInParameterGroup
except ImportError:  # Revit 2025+
    BuiltInParameterGroup = None


# --- файл ФОП ----------------------------------------------------------------------

def connected_path(app):
    try:
        return app.SharedParametersFilename or u""
    except Exception:
        return u""


def connected_file(app):
    """(путь, DefinitionFile) подключённого ФОП; файл None — не подключён или не открылся."""
    path = connected_path(app)
    if not path:
        return path, None
    try:
        return path, app.OpenSharedParameterFile()
    except Exception:
        return path, None


# Заголовок пустого ФОП — как его пишет сам Revit (UTF-16, табуляции).
_EMPTY_FILE = (
    u"# This is a Revit shared parameter file.\r\n"
    u"# Do not edit manually.\r\n"
    u"*META\tVERSION\tMINVERSION\r\n"
    u"META\t2\t1\r\n"
    u"*GROUP\tID\tNAME\r\n"
    u"*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\tVISIBLE\tDESCRIPTION"
    u"\tUSERMODIFIABLE\tHIDEWHENNOVALUE\r\n"
)


def create_file(path):
    """Новый пустой ФОП. True — файл создан или уже был."""
    if os.path.isfile(path):
        return True
    try:
        with io.open(path, "w", encoding="utf-16", newline="") as f:
            f.write(_EMPTY_FILE)
        return True
    except Exception:
        return False


def open_file(app, path):
    """Подключает path как ФОП Revit и открывает его; None — не открылся."""
    old = connected_path(app)
    try:
        app.SharedParametersFilename = path
        sp_file = app.OpenSharedParameterFile()
    except Exception:
        sp_file = None
    if sp_file is None and old:
        try:
            app.SharedParametersFilename = old
        except Exception:
            pass
    return sp_file


def find_definition(sp_file, name):
    """(имя группы, ExternalDefinition) по имени без учёта регистра; (None, None) — нет."""
    if sp_file is None:
        return None, None
    lower = name.lower()
    for group in sp_file.Groups:
        for definition in group.Definitions:
            if definition.Name.lower() == lower:
                return group.Name, definition
    return None, None


def definition_names(sp_file):
    """{имя в нижнем регистре: имя группы} — все определения ФОП."""
    result = {}
    if sp_file is None:
        return result
    for group in sp_file.Groups:
        for definition in group.Definitions:
            result[definition.Name.lower()] = group.Name
    return result


# --- типы данных -------------------------------------------------------------------

def _spec(data_type):
    """ForgeTypeId типа данных (Revit 2022+) или None."""
    if SpecTypeId is None:
        return None
    try:
        if data_type == fop_catalog.LENGTH:
            return SpecTypeId.Length
        if data_type == fop_catalog.NUMBER:
            return SpecTypeId.Number
        return SpecTypeId.String.Text
    except Exception:
        return None


def _parameter_type(data_type):
    if ParameterType is None:
        return None
    if data_type == fop_catalog.LENGTH:
        return ParameterType.Length
    if data_type == fop_catalog.NUMBER:
        return ParameterType.Number
    return ParameterType.Text


def _creation_options(name, data_type):
    spec = _spec(data_type)
    if spec is not None:
        try:
            return ExternalDefinitionCreationOptions(name, spec)
        except Exception:
            pass
    return ExternalDefinitionCreationOptions(name, _parameter_type(data_type))


def type_matches(definition, data_type):
    """Совпадает ли тип данных определения с нужным; None — не удалось узнать."""
    spec = _spec(data_type)
    if spec is not None:
        try:
            return definition.GetDataType().Equals(spec)
        except Exception:
            pass
    ptype = _parameter_type(data_type)
    if ptype is not None:
        try:
            return definition.ParameterType == ptype
        except Exception:
            pass
    return None


def create_definition(sp_file, group_name, name, data_type, description=u""):
    """Новое определение в группе group_name (группа создаётся при необходимости)."""
    group = sp_file.Groups.get_Item(group_name)
    if group is None:
        group = sp_file.Groups.Create(group_name)
    options = _creation_options(name, data_type)
    if description:
        try:
            options.Description = description
        except Exception:
            pass
    return group.Definitions.Create(options)


# --- привязки ----------------------------------------------------------------------

def find_binding(doc, name):
    """(Definition проекта, Binding) параметра с именем name; (None, None) — не привязан."""
    lower = name.lower()
    it = doc.ParameterBindings.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        if it.Key.Name.lower() == lower:
            return it.Key, it.Current
    return None, None


def _category(doc, name):
    try:
        bic = getattr(BuiltInCategory, name)
    except AttributeError:
        return None
    try:
        return doc.Settings.Categories.get_Item(bic)
    except Exception:
        return None


def _insert(doc, definition, binding, reinsert):
    method = doc.ParameterBindings.ReInsert if reinsert else doc.ParameterBindings.Insert
    if GroupTypeId is not None:
        try:
            return method(definition, binding, GroupTypeId.Data)
        except Exception:
            pass
    if BuiltInParameterGroup is not None:
        try:
            return method(definition, binding, BuiltInParameterGroup.PG_DATA)
        except Exception:
            pass
    return method(definition, binding)


def bind(doc, app, definition, category_names, kind):
    """
    Привязывает definition к категориям category_names (имена BuiltInCategory).
    Возвращает dict: added (подписи добавленных категорий), skipped
    (категории, которых нет в Revit или к которым нельзя привязать параметр),
    error (текст или None).
    """
    result = {"added": [], "skipped": [], "error": None}

    project_def, existing = find_binding(doc, definition.Name)
    if existing is not None:
        is_type = isinstance(existing, TypeBinding)
        if is_type != (kind == fop_catalog.TYPE):
            result["error"] = u"в проекте уже привязан как параметр {}, а нужен — {}".format(
                u"типа" if is_type else u"экземпляра",
                u"типа" if kind == fop_catalog.TYPE else u"экземпляра")
            return result

    missing = []
    for name in category_names:
        title = fop_catalog.CATEGORY_TITLES.get(name, name)
        category = _category(doc, name)
        if category is None or not category.AllowsBoundParameters:
            result["skipped"].append(title)
            continue
        if existing is not None and existing.Categories.Contains(category):
            continue
        missing.append((title, category))

    if not missing:
        return result

    cat_set = app.Create.NewCategorySet()
    if existing is not None:
        for c in existing.Categories:
            cat_set.Insert(c)
    for _title, c in missing:
        cat_set.Insert(c)

    if kind == fop_catalog.TYPE:
        new_binding = app.Create.NewTypeBinding(cat_set)
    else:
        new_binding = app.Create.NewInstanceBinding(cat_set)

    try:
        ok = _insert(doc, project_def if existing is not None else definition,
                     new_binding, existing is not None)
    except Exception as ex:
        result["error"] = u"{}".format(ex)
        return result

    if not ok:
        result["error"] = u"Revit не принял привязку"
        return result

    result["added"] = [title for title, _c in missing]
    return result


# --- всё вместе ----------------------------------------------------------------------

class Report(object):
    """Итог по строкам — для окна вывода pyRevit."""

    def __init__(self):
        self.created = []       # новые определения в ФОП
        self.reused = []        # определения уже были в ФОП
        self.bound = []         # добавлены привязки
        self.already = []       # всё уже было привязано
        self.warnings = []
        self.errors = []


def add_and_bind(doc, app, sp_file, group_name, rows):
    """
    Создаёт недостающие определения в ФОП и привязывает параметры отмеченных
    строк к их категориям. Возвращает Report.
    """
    report = Report()
    todo = []

    for row in rows:
        if not row.Checked:
            continue
        name = (row.Name or u"").strip()
        label = u"{} — «{}»".format(row.Label, name)

        group, definition = find_definition(sp_file, name)
        if definition is None:
            # Уже есть в проекте (общий из другого ФОП или параметр проекта) —
            # не плодим в ФОП второе определение с тем же именем, только
            # дополняем привязку.
            definition, _binding = find_binding(doc, name)
            if definition is not None:
                row.Name = name = definition.Name
                label = u"{} — «{}»".format(row.Label, name)
                report.reused.append(u"{} (уже есть в проекте, не из этого ФОП)".format(label))
                todo.append((row, label, definition))
                continue
        if definition is not None:
            if definition.Name != name:
                # Revit ищет параметр по имени с учётом регистра — в
                # настройки кнопок пойдёт имя как в ФОП.
                row.Name = name = definition.Name
                label = u"{} — «{}»".format(row.Label, name)
            report.reused.append(u"{} (группа «{}»)".format(label, group))
            if type_matches(definition, row.spec.data_type) is False:
                report.warnings.append(
                    u"{}: в ФОП тип данных не «{}» — параметр привязан как есть, "
                    u"проверьте, подходит ли он".format(label, row.DataType))
        else:
            try:
                definition = create_definition(sp_file, group_name, name,
                                               row.spec.data_type, row.Label)
            except Exception as ex:
                report.errors.append(u"{}: не удалось создать в ФОП — {}".format(label, ex))
                continue
            if definition is None:
                report.errors.append(u"{}: не удалось создать в ФОП".format(label))
                continue
            report.created.append(label)

        todo.append((row, label, definition))

    if not todo:
        return report

    t = Transaction(doc, u"LowLife: параметры из ФОП")
    t.Start()
    try:
        for row, label, definition in todo:
            result = bind(doc, app, definition, row.categories, row.spec.kind)
            if result["error"]:
                report.errors.append(u"{}: {}".format(label, result["error"]))
            elif result["added"]:
                report.bound.append(u"{} → {}".format(label, u", ".join(result["added"])))
            else:
                report.already.append(label)
            if result["skipped"]:
                report.warnings.append(u"{}: пропущены категории {}".format(
                    label, u", ".join(result["skipped"])))
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise

    return report
