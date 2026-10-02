# -*- coding: utf-8 -*-
"""
Чтение писем из классического Outlook через COM для кнопки «Задачи из
почты» — без pywin32: System.Type.GetTypeFromProgID + Activator /
Marshal.GetActiveObject, дальше позднее связывание (IDispatch) IronPython.

Только чтение: письма не открываются (Display), не сохраняются, не
помечаются прочитанными и не перемещаются — читаются лишь свойства
(ReceivedTime, Sender*, To, CC, Subject, Body).

Новый Outlook (One Outlook / olk.exe) COM не поддерживает — тогда
ProgID «Outlook.Application» не зарегистрирован или объект не создаётся,
и read_inbox бросает OutlookError с понятным текстом.
"""

import datetime

import clr
clr.AddReference("System")

from System import Type, Activator
from System.Runtime.InteropServices import Marshal

from lowlife.email_tasks_core import trim_body

OL_FOLDER_INBOX = 6
OL_MAIL_ITEM = 43
PR_SMTP_ADDRESS = u"http://schemas.microsoft.com/mapi/proptag/0x39FE001F"
PR_SENDER_SMTP_ADDRESS = u"http://schemas.microsoft.com/mapi/proptag/0x5D01001F"

# Защита от случайного «прочитать всю папку за год»
MAX_EMAILS = 400


class OutlookError(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


class Cancelled(Exception):
    pass


def _to_py_datetime(value):
    try:
        return datetime.datetime(value.Year, value.Month, value.Day,
                                 value.Hour, value.Minute, value.Second)
    except Exception:
        return None


def connect():
    """Объект Outlook.Application (уже запущенный, иначе запускается в фоне)."""
    com_type = Type.GetTypeFromProgID("Outlook.Application")
    if com_type is None:
        raise OutlookError(
            u"Классический Outlook не найден (COM-объект Outlook.Application "
            u"не зарегистрирован).\n\n"
            u"Если у вас «новый Outlook» — он не поддерживает COM. Переключитесь "
            u"на классический Outlook (переключатель «Новый Outlook» в правом "
            u"верхнем углу окна) и запустите его.")

    app = None
    # Marshal.GetActiveObject есть только в .NET Framework (Revit до 2024);
    # в .NET 8 (Revit 2025+) его нет — тогда Activator: для Outlook он всё
    # равно возвращает уже запущенный экземпляр (Outlook однопроцессный).
    get_active = getattr(Marshal, "GetActiveObject", None)
    if get_active is not None:
        try:
            app = get_active("Outlook.Application")
        except Exception:
            app = None
    if app is None:
        try:
            app = Activator.CreateInstance(com_type)
        except Exception as ex:
            raise OutlookError(
                u"Не удалось подключиться к Outlook:\n{}\n\n"
                u"Запустите классический Outlook (не «новый Outlook» — у него "
                u"нет COM) и повторите. Если Outlook запущен от имени "
                u"администратора, а Revit — нет (или наоборот), подключение "
                u"тоже не сработает.".format(ex))
    return app


def _find_subfolder(folder, path):
    """Подпапка по пути «Проекты/Объект 1» (или через «\\»), без учёта регистра."""
    for name in path.replace(u"\\", u"/").split(u"/"):
        name = name.strip()
        if not name:
            continue
        found = None
        children = folder.Folders
        for i in range(1, children.Count + 1):
            child = children.Item(i)
            if unicode(child.Name).strip().lower() == name.lower():
                found = child
                break
        if found is None:
            raise OutlookError(
                u"Во «Входящих» нет подпапки «{}» (путь из настроек: «{}»).\n\n"
                u"Проверьте настройки: Shift+клик по кнопке.".format(name, path))
        folder = found
    return folder


def _safe(getter, default=u""):
    try:
        value = getter()
    except Exception:
        return default
    if value is None:
        return default
    return value


def _sender_smtp(item):
    """SMTP-адрес отправителя. Для Exchange (SenderEmailType == 'EX')
    SenderEmailAddress — это X.500-путь «/O=EXCHANGELABS/...», поэтому
    берём PrimarySmtpAddress через GetExchangeUser()."""
    kind = unicode(_safe(lambda: item.SenderEmailType)).upper()
    if kind == u"EX":
        sender = _safe(lambda: item.Sender, None)
        if sender is not None:
            user = _safe(lambda: sender.GetExchangeUser(), None)
            if user is not None:
                smtp = _safe(lambda: user.PrimarySmtpAddress)
                if smtp:
                    return unicode(smtp)
            dlist = _safe(lambda: sender.GetExchangeDistributionList(), None)
            if dlist is not None:
                smtp = _safe(lambda: dlist.PrimarySmtpAddress)
                if smtp:
                    return unicode(smtp)
            smtp = _safe(lambda: sender.PropertyAccessor.GetProperty(PR_SMTP_ADDRESS))
            if smtp:
                return unicode(smtp)
        smtp = _safe(lambda: item.PropertyAccessor.GetProperty(PR_SENDER_SMTP_ADDRESS))
        if smtp:
            return unicode(smtp)
    return unicode(_safe(lambda: item.SenderEmailAddress))


def _walk_folders(folder):
    """Папка и все её подпапки (в глубину)."""
    result = [folder]
    children = _safe(lambda: folder.Folders, None)
    if children is not None:
        for i in range(1, _safe(lambda: children.Count, 0) + 1):
            child = _safe(lambda: children.Item(i), None)
            if child is not None:
                result.extend(_walk_folders(child))
    return result


def _read_folder(folder, cutoff, unread_only, emails, tick):
    """Письма одной папки новее cutoff — дописываются в emails. Возвращает
    False, если набрали MAX_EMAILS (дальше читать нет смысла)."""
    folder_path = unicode(_safe(lambda: folder.FolderPath))
    items = folder.Items
    if unread_only:
        items = items.Restrict("[UnRead] = True")
    items.Sort("[ReceivedTime]", True)

    item = items.GetFirst()
    while item is not None:
        if _safe(lambda: item.Class, 0) == OL_MAIL_ITEM:
            received = _to_py_datetime(_safe(lambda: item.ReceivedTime, None))
            # Отсортировано по убыванию: первое письмо старше периода — дальше только старше
            if received is not None and received < cutoff:
                break
            sender_name = unicode(_safe(lambda: item.SenderName))
            smtp = _sender_smtp(item)
            if smtp and smtp.lower() != sender_name.lower():
                sender = u"{} <{}>".format(sender_name, smtp) if sender_name else smtp
            else:
                sender = sender_name or smtp
            emails.append({
                "id": 0,  # сквозные номера — после сборки всех папок
                "received": received,
                "folder": folder_path,
                "sender": sender,
                "sender_name": sender_name,
                "to": unicode(_safe(lambda: item.To)),
                "cc": unicode(_safe(lambda: item.CC)),
                "subject": unicode(_safe(lambda: item.Subject)),
                "body": trim_body(_safe(lambda: item.Body)),
            })
            if tick is not None and tick(len(emails)):
                raise Cancelled()
            if len(emails) >= MAX_EMAILS:
                return False
        item = items.GetNext()
    return True


def read_inbox(days, unread_only=False, subfolder=u"", include_subfolders=True, tick=None):
    """
    Письма из «Входящих» (или их подпапки из настроек) за последние `days`
    дней, новые первыми. include_subfolders — заодно все вложенные папки.
    Возвращает (список писем, описание папок, предупреждение или None).
    tick(n) вызывается после каждого прочитанного письма; если вернул
    True — бросается Cancelled.
    """
    app = connect()
    try:
        namespace = app.GetNamespace("MAPI")
        inbox = namespace.GetDefaultFolder(OL_FOLDER_INBOX)
    except Exception as ex:
        raise OutlookError(
            u"Outlook запущен, но папка «Входящие» недоступна:\n{}\n\n"
            u"Проверьте, что Outlook открыт и профиль загружен.".format(ex))

    root = _find_subfolder(inbox, subfolder) if (subfolder or u"").strip() else inbox
    root_name = unicode(_safe(lambda: root.FolderPath, u"Входящие"))
    folders = _walk_folders(root) if include_subfolders else [root]

    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    emails = []
    warning = None
    skipped = []
    for folder in folders:
        try:
            if not _read_folder(folder, cutoff, unread_only, emails, tick):
                warning = (u"Писем за период больше {0} — разобраны только {0} "
                           u"первых найденных. Уменьшите период в настройках.".format(MAX_EMAILS))
                break
        except Cancelled:
            raise
        except Exception:
            skipped.append(unicode(_safe(lambda: folder.Name, u"?")))

    if skipped:
        note = u"Не удалось прочитать папки: " + u", ".join(skipped)
        warning = note if not warning else warning + u" " + note

    emails.sort(key=lambda e: e["received"] or datetime.datetime(1900, 1, 1), reverse=True)
    for i, email in enumerate(emails, start=1):
        email["id"] = i

    if include_subfolders and len(folders) > 1:
        folder_name = u"{} и подпапки ({})".format(root_name, len(folders) - 1)
    else:
        folder_name = root_name
    return emails, folder_name, warning
