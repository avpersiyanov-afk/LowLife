# -*- coding: utf-8 -*-
"""Native Copy/Monitor session; selected datums still require Revit UI picks."""
from Autodesk.Revit import DB, UI
from pyrevit import script, forms
from lowlife import link_datums, link_datums_copy
from lowlife.i18n import tr

SESSION_KEY = 'LowLife.Kfp.NativeCopyMonitor'


class NativeSession(object):
    def __init__(self, uiapp, link, choices, tolerance, report):
        self.uiapp = uiapp
        self.doc = uiapp.ActiveUIDocument.Document
        self.link_id = link.Id
        self.choices = choices
        self.tolerance = tolerance
        self.report = report
        levels, grids = link_datums.compare(self.doc, link, tolerance)
        self.original_ids = set(row.model['id_int'] for row in levels + grids if row.model)
        self.command = UI.RevitCommandId.LookupPostableCommandId(UI.PostableCommand.CopyMonitorSelectLink)
        self.binding = None
        self.started = False
        self.settling = True
        self.before_handler = self.before
        self.idle_handler = self.idle
        self.close_handler = self.closing

    def before(self, sender, args):
        self.started = True

    def closing(self, sender, args):
        if args.Document.Equals(self.doc):
            self.stop()

    def stop(self):
        self.uiapp.Idling -= self.idle_handler
        self.uiapp.Application.DocumentClosing -= self.close_handler
        if self.binding is not None:
            self.binding.BeforeExecuted -= self.before_handler
            self.uiapp.RemoveAddInCommandBinding(self.command)
            self.binding = None
        if script.get_envvar(SESSION_KEY) is self:
            script.set_envvar(SESSION_KEY, None)

    def idle(self, sender, args):
        if not self.started or self.doc.IsModifiable:
            return
        if self.settling:
            self.settling = False
            args.SetRaiseWithoutDelay()
            return
        self.stop()
        if not self.doc.IsValidObject:
            return
        try:
            link = self.doc.GetElement(self.link_id)
            if link is None or link.GetLinkDocument() is None:
                raise ValueError(tr(u'Связь больше не загружена.', u'Link is no longer loaded.'))
            configured, errors = link_datums_copy.configure_copies(
                self.doc, link, self.choices, self.original_ids, self.tolerance)
            self.report(link, configured, errors)
        except Exception as exc:
            forms.alert(tr(u'Не удалось обработать результат штатного копирования:\n{}',
                           u'Could not process the native copying result:\n{}').format(exc))


def start(uiapp, link, choices, tolerance, report):
    """Post the supported native command; never manufacture monitoring links."""
    previous = script.get_envvar(SESSION_KEY)
    if previous is not None:
        raise ValueError(tr(u'Сначала завершите предыдущее Копирование/Мониторинг.',
                            u'Finish the previous Copy/Monitor session first.'))
    session = NativeSession(uiapp, link, choices, tolerance, report)
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
