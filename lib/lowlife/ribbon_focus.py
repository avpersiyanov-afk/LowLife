# -*- coding: utf-8 -*-
"""Keep the LowLife ribbon tab active after a LowLife button finishes."""

TAB_NAME = u"LowLife"
_HANDLER_KEY = u"LowLife.ribbon_focus.handler"

try:
    unicode  # noqa: F821 - IronPython/Python 2
except NameError:  # Python 3
    unicode = str


def is_lowlife_item_id(item_id):
    """Return True when an Autodesk.Windows item belongs to the LowLife tab."""
    return TAB_NAME in unicode(item_id or u"").split(u"%")


def activate_tab():
    """Show and activate the LowLife tab; return whether it was found."""
    import clr
    clr.AddReference("AdWindows")
    from Autodesk.Windows import ComponentManager

    ribbon = ComponentManager.Ribbon
    for tab in ribbon.Tabs:
        if tab.Title == TAB_NAME or tab.Id == TAB_NAME:
            tab.IsVisible = True
            ribbon.ActiveTab = tab
            return True
    return False


def _cancel_pending(state):
    state[u"cancelled"] = True
    idle = state.get(u"idle")
    if idle is not None:
        try:
            state[u"uiapp"].Idling -= idle
        except Exception:
            pass
        state[u"idle"] = None


def install(uiapp):
    """Restore LowLife after every executed LowLife ribbon button.

    ``ItemExecuted`` is raised while Revit is still processing the click.  The
    one-shot ``Idling`` callback runs after the posted command has returned,
    so changing the active tab there is not immediately overwritten by Revit.
    """
    if uiapp is None:
        return False

    import clr
    clr.AddReference("AdWindows")
    from Autodesk.Windows import ComponentManager
    from System import AppDomain

    domain = AppDomain.CurrentDomain
    old = domain.GetData(_HANDLER_KEY)
    if old is not None:
        try:
            ComponentManager.ItemExecuted -= old[u"delegate"]
        except Exception:
            pass
        try:
            old[u"cancel"]()
        except Exception:
            pass

    state = {u"uiapp": uiapp, u"idle": None, u"cancelled": False}

    def schedule():
        if state[u"cancelled"] or state[u"idle"] is not None:
            return

        def on_idle(sender, args):
            state[u"idle"] = None
            try:
                uiapp.Idling -= on_idle
            except Exception:
                pass
            try:
                activate_tab()
            except Exception:
                pass

        state[u"idle"] = on_idle
        try:
            uiapp.Idling += on_idle
        except Exception:
            state[u"idle"] = None

    def on_item_executed(sender, args):
        try:
            item = args.Item
            if item is not None and is_lowlife_item_id(item.Id):
                schedule()
        except Exception:
            pass

    try:
        from System import EventHandler
        from Autodesk.Windows import RibbonItemExecutedEventArgs
        delegate = EventHandler[RibbonItemExecutedEventArgs](on_item_executed)
    except Exception:
        delegate = on_item_executed

    state[u"delegate"] = delegate
    state[u"cancel"] = lambda: _cancel_pending(state)
    ComponentManager.ItemExecuted += delegate
    domain.SetData(_HANDLER_KEY, state)
    return True
