# -*- coding: utf-8 -*-
"""Native Copy/Monitor session; selected datums still require Revit UI picks."""
from Autodesk.Revit import DB, UI
from pyrevit import script, forms
from lowlife import link_datums, link_datums_copy
from lowlife.i18n import tr

SESSION_KEY = 'LowLife.Kfp.NativeCopyMonitor'


class NativeSession(object):
    def __init__(self, uiapp, link, choices, tolerance, report, pending=None):
        self.uiapp = uiapp
        self.doc = uiapp.ActiveUIDocument.Document
        self.link_id = link.Id
        self.choices = choices
        self.tolerance = tolerance
        self.report = report
        self.pending = list(pending or [])
        self.waiting_view = None
        self.view_waits = 0
        levels, grids = link_datums.compare(self.doc, link, tolerance)
        self.original_ids = set(row.model['id_int'] for row in levels + grids if row.model)
        self.command = UI.RevitCommandId.LookupPostableCommandId(UI.PostableCommand.CopyMonitorSelectLink)
        self.binding = None
        self.started = False
        self.settling = True
        self.multiple = None
        self.before_handler = self.before
        self.idle_handler = self.idle
        self.close_handler = self.closing

    def before(self, sender, args):
        self.started = True
        try:
            from lowlife.link_datums_native_ui import MultipleSelection
            self.multiple = MultipleSelection(self.uiapp, self.doc)
            self.multiple.start()
        except Exception:
            pass  # Native Copy/Monitor remains available manually.

    def closing(self, sender, args):
        if args.Document.Equals(self.doc):
            self.stop()

    def stop(self):
        if self.multiple is not None:
            self.multiple.stop()
            self.multiple = None
        self.uiapp.Idling -= self.idle_handler
        self.uiapp.Application.DocumentClosing -= self.close_handler
        if self.binding is not None:
            self.binding.BeforeExecuted -= self.before_handler
            self.uiapp.RemoveAddInCommandBinding(self.command)
            self.binding = None
        if script.get_envvar(SESSION_KEY) is self:
            script.set_envvar(SESSION_KEY, None)

    def idle(self, sender, args):
        uidoc = self.uiapp.ActiveUIDocument
        if (not self.doc.IsValidObject or uidoc is None
                or not uidoc.Document.Equals(self.doc)):
            self.stop()
            return
        if self.doc.IsModifiable:
            return
        if self.waiting_view is not None:
            self.view_waits += 1
            if not self.waiting_view.IsValidObject or self.view_waits > 100:
                self.stop()
                return
            if uidoc.ActiveView.Id != self.waiting_view.Id:
                return
            self.waiting_view = None
            try:
                from lowlife.link_datums_views import activate
                activate(uidoc, uidoc.ActiveView, self.doc.GetElement(self.link_id), self.choices)
                self.uiapp.PostCommand(self.command)
            except Exception as exc:
                self.stop()
                forms.alert(tr(u'Не удалось запустить копирование на следующем виде:\n{}',
                               u'Could not start copying in the next view:\n{}').format(exc))
            return
        if not self.started:
            return
        if self.settling:
            self.settling = False
            args.SetRaiseWithoutDelay()
            return
        try:
            link = self.doc.GetElement(self.link_id)
            if link is None or link.GetLinkDocument() is None:
                raise ValueError(tr(u'Связь больше не загружена.', u'Link is no longer loaded.'))
            configured, errors = link_datums_copy.configure_copies(
                self.doc, link, self.choices, self.original_ids, self.tolerance)
            self.report(link, configured, errors)
            if configured and self.pending:
                # Revit forbids registering a new Idling handler inside Idling.
                # Keep this session/binding and reuse them after the view request.
                view, self.choices = self.pending.pop(0)
                if self.multiple is not None:
                    self.multiple.stop()
                    self.multiple = None
                self.started = False
                self.settling = True
                self.waiting_view = view
                self.view_waits = 0
                self.uiapp.ActiveUIDocument.RequestViewChange(view)
            else:
                self.stop()
        except Exception as exc:
            self.stop()
            forms.alert(tr(u'Не удалось обработать результат штатного копирования:\n{}',
                           u'Could not process the native copying result:\n{}').format(exc))


def start(uiapp, link, choices, tolerance, report, pending=None):
    """Post the supported native command; never manufacture monitoring links."""
    previous = script.get_envvar(SESSION_KEY)
    if previous is not None:
        raise ValueError(tr(u'Сначала завершите предыдущее Копирование/Мониторинг.',
                            u'Finish the previous Copy/Monitor session first.'))
    session = NativeSession(uiapp, link, choices, tolerance, report, pending)
    if not uiapp.CanPostCommand(session.command):
        raise ValueError(tr(u'Копирование/Мониторинг недоступно на текущем виде.',
                            u'Copy/Monitor is unavailable in the current view.'))
    try:
        session.binding = uiapp.CreateAddInCommandBinding(session.command)
        session.binding.BeforeExecuted += session.before_handler
        uiapp.Idling += session.idle_handler
        uiapp.Application.DocumentClosing += session.close_handler
        script.set_envvar(SESSION_KEY, session)
        uiapp.PostCommand(session.command)
    except Exception:
        session.stop()
        raise
    return session
