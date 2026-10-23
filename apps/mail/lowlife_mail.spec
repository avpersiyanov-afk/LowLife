# -*- mode: python ; coding: utf-8 -*-
# Сборка «Задач из почты» в один LowLifeMail.exe: pyinstaller apps/mail/lowlife_mail.spec
import glob
import os

HERE = os.path.abspath(SPECPATH)  # noqa: F821 — задаёт PyInstaller
REPO = os.path.dirname(os.path.dirname(HERE))
LIB = os.path.join(REPO, 'lib')
BUTTON = os.path.join(REPO, 'LowLife.tab', 'Mail.panel', 'EmailTasks.pushbutton')

# Модули lib/lowlife, нужные приложению (пакет без __init__.py — перечисляем явно)
LOWLIFE = ['lowlife.' + os.path.splitext(os.path.basename(p))[0] for p in (
    glob.glob(os.path.join(LIB, 'lowlife', 'email_*.py'))
    + [os.path.join(LIB, 'lowlife', n) for n in ('ai_settings_core.py', 'settings_core.py')])
    if os.path.basename(p) not in ('email_ai_clr.py', 'email_tasks_excel.py')]  # .NET — только в Revit

a = Analysis(  # noqa: F821
    [os.path.join(HERE, 'lowlife_mail.py')],
    pathex=[HERE, LIB],
    datas=[(os.path.join(BUTTON, name), 'data') for name in ('prompt.txt', 'test_emails.json', 'icon.png')],
    hiddenimports=LOWLIFE + ['mail_window', 'mail_settings_window', 'win32com.client'],
    # clr (pythonnet) не берём, даже если он установлен: без него библиотека
    # выбирает stdlib/pywin32 вместо .NET (email_ai_net, email_outlook)
    excludes=['clr', 'pythonnet', 'pyrevit', 'System', 'lowlife.email_ai_clr', 'lowlife.email_tasks_excel'],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LowLifeMail',
    console=False,
    upx=False,
    icon=os.path.join(BUTTON, 'icon.png'),
)
