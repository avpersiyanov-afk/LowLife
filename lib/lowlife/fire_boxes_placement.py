# -*- coding: utf-8 -*-
"""Native Revit drawing with a document-scoped, temporary creation updater."""
import copy

try:
    unicode
except NameError:
    unicode = str

from Autodesk.Revit import DB, UI
from System import Guid
from System.Collections.Generic import List
from pyrevit import forms, script
from lowlife.i18n import tr
from lowlife import fire_boxes as fb, fire_boxes_core as core

SESSION_KEY = 'LowLife.FireBoxes.NativePlacement'
UPDATER_GUID = Guid('a1cd038b-189e-40a3-9892-4edaf4e07734')


class PlacementUpdater(DB.IUpdater):
    def __init__(self, session):
        self.session = session
        self.identifier = DB.UpdaterId(session.uiapp.ActiveAddInId, UPDATER_GUID)

    def GetUpdaterId(self):
        return self.identifier

    def GetUpdaterName(self):
        return 'LowLife fire enclosure placement'

    def GetAdditionalInformation(self):
        return 'Apply the enclosure settings to newly drawn segments and fittings.'

    def GetChangePriority(self):
        return DB.ChangePriority.MEPSystems

    def Execute(self, data):
        if self.session.active and data.GetDocument().Equals(self.session.doc):
            self.session.process(data.GetAddedElementIds())


class PlacementSession(object):
    def __init__(self, uiapp, doc, settings):
        self.uiapp, self.doc = uiapp, doc
        self.settings = copy.deepcopy(settings)
        self.section = core.mounting_section(settings)
        self.type = doc.GetElement(settings['box_type_uid'])
        self.system = doc.GetElement(settings['system_type_uid']) if settings.get('system_type_uid') else None
        self.workset = fb.resolve_workset(doc, settings.get('box_workset_name', ''))
        self.previous_workset = doc.GetWorksetTable().GetActiveWorksetId() if doc.IsWorkshared else None
        self.active = False
        self.created = set()
        self.errors = {}
        self.seed_uid = None
        self.started = False
        self.starting_idle = True
        self.command = UI.RevitCommandId.LookupPostableCommandId(UI.PostableCommand.CreateSimilar)
        self.binding = None
        self.begin_handler = self.on_begin
        self.updater = PlacementUpdater(self)
        self.idle_handler = self.on_idle
        self.close_handler = self.on_closing

    def apply(self, element):
        if fb.in_categories(element, fb.CURVE_CATS):
            fb.size(element, self.section['width'], self.section['height'])
            if fb.is_duct_type(self.type):
                parameter = element.get_Parameter(DB.BuiltInParameter.RBS_DUCT_SYSTEM_TYPE_PARAM)
                if parameter is not None and parameter.AsElementId() != self.system.Id:
                    element.SetSystemType(self.system.Id)
            parameter = element.get_Parameter(DB.BuiltInParameter.RBS_OFFSET_PARAM)
            offset = float(self.settings['elevation_mm'])/304.8
            if parameter is None or parameter.IsReadOnly:
                raise ValueError(tr(u'Не удалось задать высоту оси короба {}.',
                                    u'Could not set enclosure {} axis elevation.').format(fb.eid(element.Id)))
            if abs(parameter.AsDouble()-offset) > 1e-7 and not parameter.Set(offset):
                raise ValueError(tr(u'Не удалось задать высоту оси короба {}.',
                                    u'Could not set enclosure {} axis elevation.').format(fb.eid(element.Id)))
        fb.assign_workset(element, self.workset)
        fb.note(element, self.settings)
        fb.write_data(element, dict(version=1, settings=self.settings))

    def process(self, ids):
        # Curves first: a fitting is ours only when it touches a segment added
        # in this placement session. Other types and existing elements are skipped.
        added = [self.doc.GetElement(identifier) for identifier in ids]
        curves = [el for el in added if fb.in_categories(el, fb.CURVE_CATS)
                  and el.GetTypeId() == self.type.Id]
        self.created.update(el.UniqueId for el in curves)
        fittings = [el for el in added if fb.in_categories(el, fb.FITTING_CATS)
                    and any(curve.UniqueId in self.created for curve in fb.connected_curves(el).values())]
        self.created.update(el.UniqueId for el in fittings)
        if curves:
            self.remove_seed()
        for element in curves+fittings:
            try:
                self.apply(element)
                self.errors.pop(element.UniqueId, None)
            except Exception as exc:
                self.errors[element.UniqueId] = unicode(exc)

    def prepare(self):
        # Create Similar copies instance dimensions/elevation into the native
        # options bar. Type placement alone reuses Revit's last (unrelated) size.
        level = self.doc.ActiveView.GenLevel
        origin = self.doc.ActiveView.Origin
        start = DB.XYZ(origin.X, origin.Y, level.Elevation+float(self.settings['elevation_mm'])/304.8)
        transaction = DB.Transaction(self.doc, tr(u'Подготовить рисование короба', u'Prepare enclosure drawing'))
        transaction.Start()
        try:
            seed = fb.create_curve(self.doc, self.type, self.system, level.Id, start, start+DB.XYZ(1, 0, 0),
                                   self.section['width'], self.section['height'])
            self.seed_uid = seed.UniqueId
            fb.assign_workset(seed, self.workset)
            fb.note(seed, self.settings)
            if transaction.Commit() != DB.TransactionStatus.Committed:
                raise ValueError(tr(u'Revit отменил подготовку короба.', u'Revit rolled back enclosure preparation.'))
        except Exception:
            if transaction.GetStatus() == DB.TransactionStatus.Started:
                transaction.RollBack()
            raise
        self.uiapp.ActiveUIDocument.Selection.SetElementIds(List[DB.ElementId]([seed.Id]))

    def remove_seed(self):
        seed = self.doc.GetElement(self.seed_uid) if self.seed_uid and self.doc.IsValidObject else None
        if seed is None:
            return
        if self.doc.IsModifiable:
            self.doc.Delete(seed.Id)
        else:
            transaction = DB.Transaction(self.doc, tr(u'Завершить подготовку короба', u'Finish enclosure preparation'))
            transaction.Start()
            try:
                self.doc.Delete(seed.Id)
                transaction.Commit()
            except Exception:
                if transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
                raise
        self.seed_uid = None

    def install(self):
        identifier = self.updater.GetUpdaterId()
        DB.UpdaterRegistry.RegisterUpdater(self.updater, self.doc, True)
        try:
            categories = List[DB.BuiltInCategory](list(fb.CURVE_CATS+fb.FITTING_CATS))
            DB.UpdaterRegistry.AddTrigger(identifier, self.doc, DB.ElementMulticategoryFilter(categories),
                                           DB.Element.GetChangeTypeElementAddition())
            self.uiapp.Idling += self.idle_handler
            self.uiapp.Application.DocumentClosing += self.close_handler
            self.binding = self.uiapp.CreateAddInCommandBinding(self.command)
            self.binding.BeforeExecuted += self.begin_handler
            self.active = True
            if self.workset is not None:
                self.doc.GetWorksetTable().SetActiveWorksetId(self.workset)
        except Exception:
            self.stop()
            raise

    def stop(self):
        self.active = False
        try:
            self.uiapp.Idling -= self.idle_handler
            self.uiapp.Application.DocumentClosing -= self.close_handler
        finally:
            identifier = self.updater.GetUpdaterId()
            if self.binding is not None:
                self.binding.BeforeExecuted -= self.begin_handler
                self.uiapp.RemoveAddInCommandBinding(self.command)
                self.binding = None
            if self.doc.IsValidObject and DB.UpdaterRegistry.IsUpdaterRegistered(identifier, self.doc):
                DB.UpdaterRegistry.UnregisterUpdater(identifier, self.doc)
            if self.doc.IsValidObject and self.previous_workset is not None:
                table = self.doc.GetWorksetTable()
                if table.GetActiveWorksetId() == self.workset:
                    table.SetActiveWorksetId(self.previous_workset)
            if script.get_envvar(SESSION_KEY) is self:
                script.set_envvar(SESSION_KEY, None)
        self.remove_seed()

    def on_idle(self, sender, args):
        # Idling is raised once the native tool has returned control to Revit.
        # Do not leave the updater attached to later manual placement of this type.
        if not self.active or not self.started or (self.doc.IsValidObject and self.doc.IsModifiable):
            return
        if self.starting_idle:
            # Create Similar may yield before entering its category's draw tool.
            # Give the queued native command one more dispatch cycle.
            self.starting_idle = False
            args.SetRaiseWithoutDelay()
            return
        self.stop()
        if not self.doc.IsValidObject:
            return
        remaining = [message for uid, message in self.errors.items() if self.doc.GetElement(uid) is not None]
        if remaining:
            forms.alert(tr(u'Не удалось применить настройки к некоторым новым коробам:\n{}',
                           u'Could not apply settings to some new enclosures:\n{}').format(u'\n'.join(sorted(set(remaining)))))

    def on_begin(self, sender, args):
        self.started = True

    def on_closing(self, sender, args):
        if args.Document.Equals(self.doc):
            self.stop()


def start(doc, uidoc, settings):
    """Queue Revit's native tool; never keep a transaction or PickPoint loop open."""
    if doc.ActiveView.GenLevel is None:
        raise ValueError(tr(u'Откройте план уровня для рисования короба.', u'Open a level plan to draw the enclosure.'))
    element_type = doc.GetElement(settings['box_type_uid'])
    if element_type is None:
        raise ValueError(tr(u'Выберите тип короба в настройках.', u'Select an enclosure type in settings.'))
    if fb.is_duct_type(element_type):
        system = doc.GetElement(settings.get('system_type_uid', '')) if settings.get('system_type_uid') else None
        if system is None:
            raise ValueError(tr(u'Выберите систему воздуховода в настройках.', u'Select a duct system in settings.'))
    previous = script.get_envvar(SESSION_KEY)
    if previous is not None:
        previous.stop()
    session = PlacementSession(uidoc.Application, doc, settings)
    try:
        session.prepare()
        if not uidoc.Application.CanPostCommand(session.command):
            raise ValueError(tr(u'Revit не может запустить рисование на текущем виде.',
                                u'Revit cannot start drawing in the current view.'))
        session.install()
        script.set_envvar(SESSION_KEY, session)
        uidoc.Application.PostCommand(session.command)
    except Exception:
        session.stop()
        raise
    return session
