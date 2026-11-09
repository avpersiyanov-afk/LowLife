# -*- coding: utf-8 -*-
"""Prepare native Copy/Monitor multiple selection (Revit 2024 UI adapter)."""
import ctypes

COPY_COMMAND = 'ID_CPWTCH_COPY'
MULTIPLE_CONTROL_ID = 12179


def enable_multiple(main_window):
    """Check the native options-bar checkbox; never toggle an existing check."""
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumChildWindows.argtypes = [ctypes.c_void_p, callback_type, ctypes.c_void_p]
    user32.GetDlgCtrlID.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowEnabled.argtypes = [ctypes.c_void_p]
    user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                   ctypes.c_size_t, ctypes.c_ssize_t]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    found = []

    def child(hwnd, unused):
        if (user32.GetDlgCtrlID(hwnd) == MULTIPLE_CONTROL_ID
                and user32.IsWindowVisible(hwnd) and user32.IsWindowEnabled(hwnd)):
            name = ctypes.create_unicode_buffer(32)
            user32.GetClassNameW(hwnd, name, 32)
            if name.value == 'Button':
                found.append(hwnd)
        return True

    user32.EnumChildWindows(main_window, callback_type(child), None)
    if len(found) != 1:
        return False
    hwnd = found[0]
    if user32.SendMessageW(hwnd, 0x00F0, 0, 0) == 0:  # BM_GETCHECK
        user32.SendMessageW(hwnd, 0x00F5, 0, 0)  # BM_CLICK: native notification
    return user32.SendMessageW(hwnd, 0x00F0, 0, 0) == 1


class MultipleSelection(object):
    """One bounded preparation attempt; leaves selection and Finish to the user."""
    def __init__(self, uiapp, doc):
        import clr
        clr.AddReference('WindowsBase')
        clr.AddReference('AdWindows')
        clr.AddReference('UIFrameworkServices')
        from System import TimeSpan
        from System.Windows.Threading import DispatcherTimer
        from Autodesk.Windows import ComponentManager
        from UIFrameworkServices import CommandHandlerService
        self.uiapp = uiapp
        self.doc = doc
        self.ribbon = ComponentManager.Ribbon
        self.commands = CommandHandlerService
        self.ticks = 0
        self.invoked = False
        self.busy = False
        self.error = None
        self.handler = self.tick
        self.timer = DispatcherTimer()
        self.timer.Interval = TimeSpan.FromMilliseconds(250)
        self.timer.Tick += self.handler

    def start(self):
        self.timer.Start()

    def stop(self):
        self.timer.Stop()
        self.timer.Tick -= self.handler

    def tick(self, sender, args):
        if self.busy:
            return
        self.busy = True
        try:
            self.ticks += 1
            uidoc = self.uiapp.ActiveUIDocument
            if (self.ticks >= 1200 or not self.doc.IsValidObject or uidoc is None
                    or not uidoc.Document.Equals(self.doc)):
                self.stop()
                return
            active = self.commands.getActiveCommandId()
            if active == COPY_COMMAND:
                if enable_multiple(self.uiapp.MainWindowHandle.ToInt64()):
                    self.stop()
                return
            tab = self.ribbon.ActiveTab
            if not self.invoked and active == 'ID_BUTTON_SELECT' and tab is not None:
                # Stable command IDs, independent of the Revit UI language.
                ready = any(item.Id == COPY_COMMAND and item.IsEnabled
                            for panel in tab.Panels for item in panel.Source.Items)
                if ready and self.commands.canExecute(COPY_COMMAND):
                    self.invoked = True
                    self.commands.invokeCommandHandler(COPY_COMMAND)
        except Exception as exc:
            self.error = str(exc)
            # An unsupported UI version must leave the native manual workflow usable.
            self.stop()
        finally:
            self.busy = False
