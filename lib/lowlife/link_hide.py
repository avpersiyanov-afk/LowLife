# -*- coding: utf-8 -*-
"""Hide linked references through Revit's native HideElements UI command.

No linked-document transactions and no linked ElementIds passed to host
View.HideElements: those IDs belong to another document.
"""
try:
    unicode
except NameError:
    unicode = str

from lowlife import link_hide_core
from lowlife.i18n import tr


def id_value(element_id):
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue


def safe_name(element):
    if element is None:
        return u""
    from pyrevit import DB
    return unicode(DB.Element.Name.GetValue(element) or u"")


def availability(doc, view):
    from pyrevit import DB
    if doc is None or view is None or doc.IsFamilyDocument:
        return tr(u"Откройте вид проекта.", u"Open a project view.")
    if int(doc.Application.VersionNumber) < 2024:
        return tr(u"Для этой кнопки нужен Revit 2024 или новее.", u"This button requires Revit 2024 or later.")
    if view.IsTemplate or not view.AreGraphicsOverridesAllowed() or not DB.FilteredElementCollector.IsViewValidForElementIteration(doc, view.Id):
        return tr(u"На текущем виде нельзя скрывать элементы связи.", u"Linked elements cannot be hidden in the current view.")
    return None


def parameter(element, name):
    """Do not choose a random parameter when names are ambiguous."""
    if element is None:
        return None
    params = list(element.GetParameters(name))
    if len(params) > 1:
        raise ValueError(tr(u"У элемента {} несколько параметров с именем «{}». Уточните имя параметра.",
                            u"Element {} has multiple parameters named '{}'. Use an unambiguous parameter name.").format(id_value(element.Id), name))
    return params[0] if params else None


def parameter_text(param, doc):
    from pyrevit import DB
    if param is None:
        return None
    if not param.HasValue:
        return u""
    if param.StorageType == DB.StorageType.String:
        return unicode(param.AsString() or u"")
    display = param.AsValueString()
    if display is not None:
        return unicode(display)
    if param.StorageType == DB.StorageType.ElementId:
        value = param.AsElementId()
        target = doc.GetElement(value)
        return safe_name(target) if target is not None else unicode(id_value(value))
    if param.StorageType == DB.StorageType.Integer:
        return unicode(param.AsInteger())
    if param.StorageType == DB.StorageType.Double:
        return unicode(param.AsDouble())
    return None


def read_value(element, settings):
    doc = element.Document
    field = settings["field"]
    if field == "workset":
        if not doc.IsWorkshared:
            return None
        workset = doc.GetWorksetTable().GetWorkset(element.WorksetId)
        return unicode(workset.Name) if workset is not None else None
    type_element = doc.GetElement(element.GetTypeId())
    if field == "type":
        return safe_name(type_element) if type_element is not None else None
    if field == "family":
        return unicode(type_element.FamilyName) if type_element is not None else None
    name = settings["filter_param_name"].strip()
    scope = settings["scope"]
    param = parameter(element, name) if scope != "type" else None
    if param is None and scope != "instance":
        param = parameter(type_element, name)
    return parameter_text(param, doc)


class LinkRow(object):
    def __init__(self, link):
        self.link = link
        self.label = u"{} [ID {}]".format(safe_name(link), id_value(link.Id))


class MatchRow(object):
    def __init__(self, link, element, value):
        self.link = link
        self.element = element
        self.value = value
        self.label = u"{} [ID {}] | {} | {} | {} | ID {}".format(
            safe_name(link), id_value(link.Id), element.Category.Name, safe_name(element),
            value, id_value(element.Id))


def collect_links(doc, view):
    from pyrevit import DB
    collector = DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance)
    try:
        links = [LinkRow(link) for link in collector
                 if link.GetLinkDocument() is not None and not link.IsHidden(view)]
        return sorted(links, key=lambda row: row.label.lower())
    finally:
        collector.Dispose()


def collect_candidates(doc, view, links):
    """The 2024+ collector returns elements of this link in this host view.

    Visibility is Revit's collector visibility, not a pixel/occlusion test.
    Restrict to model elements and never descend into nested links.
    """
    from pyrevit import DB
    result = []
    for row in links:
        collector = DB.FilteredElementCollector(doc, view.Id, row.link.Id).WhereElementIsNotElementType()
        try:
            for element in collector:
                if (element.Category is not None and
                        element.Category.CategoryType == DB.CategoryType.Model and
                        not isinstance(element, DB.RevitLinkInstance)):
                    result.append((row.link, element))
        finally:
            collector.Dispose()
    return result


def category_key(element):
    return (id_value(element.Category.Id), unicode(element.Category.Name))


def find_matches(candidates, categories, settings):
    error = link_hide_core.validate(settings)
    if error:
        raise ValueError(error)
    result = []
    seen = set()
    categories = set(categories)
    for link, element in candidates:
        key = (id_value(link.Id), id_value(element.Id))
        if key in seen or category_key(element) not in categories:
            continue
        seen.add(key)
        value = read_value(element, settings)
        if link_hide_core.matches(value, settings["operator"], settings.get("value")):
            result.append(MatchRow(link, element, value))
    return sorted(result, key=lambda row: row.label.lower())


def post_hide(uiapp, rows):
    """Queue one native command; restore original selection on queue failure.

    Return means queued, not executed. Revit runs it after the script exits.
    """
    from pyrevit import DB, UI
    from System.Collections.Generic import List
    if not rows:
        return False
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None:
        raise ValueError(tr(u"Нет активного документа.", u"No active document."))
    refs = List[DB.Reference]()
    seen = set()
    for row in rows:
        if not row.link.Document.Equals(uidoc.Document) or not row.element.Document.Equals(row.link.GetLinkDocument()):
            raise ValueError(tr(u"Документ связи изменился. Запустите кнопку повторно.", u"The linked document changed. Run the button again."))
        key = (id_value(row.link.Id), id_value(row.element.Id))
        if key not in seen:
            refs.Add(DB.Reference(row.element).CreateLinkReference(row.link))
            seen.add(key)
    command = UI.RevitCommandId.LookupPostableCommandId(UI.PostableCommand.HideElements)
    original = List[DB.Reference](uidoc.Selection.GetReferences())
    try:
        uidoc.Selection.SetReferences(refs)
        if not uiapp.CanPostCommand(command):
            raise ValueError(tr(u"Revit не разрешает команду «Скрыть элементы» для этого выбора на текущем виде.",
                                u"Revit cannot run Hide Elements for this selection in the current view."))
        uiapp.PostCommand(command)
    except Exception:
        uidoc.Selection.SetReferences(original)
        raise
    return True


def run(uiapp, settings_only=False):
    from pyrevit import forms
    from lowlife import link_hide_settings, select_list
    title = tr(u"Скрыть в связи", u"Hide in link")
    uidoc = uiapp.ActiveUIDocument
    doc = uidoc.Document if uidoc else None
    view = uidoc.ActiveView if uidoc else None
    problem = availability(doc, view)
    if problem:
        forms.alert(problem, title=title)
        return
    settings = link_hide_settings.SETTINGS.get_settings_interactive()
    if settings is None or settings_only:
        return
    if link_hide_core.validate(settings):
        forms.alert(tr(u"Заполните имя параметра (если выбран параметр) и значение условия. Для «Пусто» и «Не пусто» значение не требуется.",
                       u"Enter the parameter name (when checking a parameter) and comparison value. Empty and Not empty need no value."), title=title)
        return
    available_links = collect_links(doc, view)
    if not available_links:
        forms.alert(tr(u"Нет загруженных видимых экземпляров связей Revit.", u"No loaded visible Revit link instances were found."), title=title)
        return
    links = select_list.SelectFromList.show(
        available_links, name_attr="label", multiselect=True,
        title=tr(u"Выберите экземпляры связей", u"Select link instances"))
    if not links:
        return
    candidates = collect_candidates(doc, view, links)
    categories = sorted(set(category_key(el) for _link, el in candidates), key=lambda key: key[1].lower())
    if not categories:
        forms.alert(tr(u"На текущем виде не найдено элементов выбранных связей.", u"No elements of the selected links were found in the current view."), title=title)
        return
    # Keep category IDs as data; the search list shows translated Revit names.
    labels = dict((u"{} [ID {}]".format(name, ident), (ident, name)) for ident, name in categories)
    choices = select_list.SelectFromList.show(
        sorted(labels), multiselect=True,
        title=tr(u"Выберите категории для проверки", u"Select categories to check"))
    if not choices:
        return
    rows = find_matches(candidates, [labels[label] for label in choices], settings)
    if not rows:
        forms.alert(tr(u"Совпадений с условием нет.", u"No elements match the criterion."), title=title)
        return
    options = [forms.TemplateListItem(row, checked=True, name_attr="label") for row in rows]
    selected = select_list.SelectFromList.show(
        options, multiselect=True, checked_only=True,
        title=tr(u"Проверьте элементы: {}. Вид: {}", u"Review elements: {}. View: {}").format(len(rows), safe_name(view)),
        button_name=tr(u"Скрыть выбранные", u"Hide selected"), width=1100)
    if selected:
        post_hide(uiapp, selected)
