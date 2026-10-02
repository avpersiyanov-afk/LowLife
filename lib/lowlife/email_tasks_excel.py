# -*- coding: utf-8 -*-
"""
Сохранение списка задач кнопки «Задачи из почты» в .xlsx через COM Excel
(позднее связывание, без pywin32) и открытие файла.

Формулы, которые уходят в Excel через COM (проверка данных, условное
форматирование), намеренно написаны без функций и разделителей
аргументов: эти места Excel разбирает в языке/локали интерфейса, и
английское TODAY()/AND(;) в русском Excel ломается. Поэтому:
- список статусов лежит на скрытом листе и подключается именем StatusList;
- «сегодня» — ячейка скрытого листа с =TODAY() (Range.Formula всегда
  английский), имя TodayDate;
- «и» в условии — произведение логических выражений.
"""

import os
import re
import datetime

import clr
clr.AddReference("System")

from System import Type, Activator, Array, Object, DateTime, Environment
from System.Reflection import Missing

COLUMNS = [
    # (заголовок, ширина)
    (u"№", 5),
    (u"Задача", 60),
    (u"Кто просит", 22),
    (u"Срок", 12),
    (u"Приоритет", 11),
    (u"Статус", 14),
    (u"Комментарий", 40),
    (u"Тема письма", 40),
    (u"Отправитель", 32),
    (u"Дата письма", 16),
]

STATUSES = [u"Не начато", u"В работе", u"Ждёт ответа", u"Готово"]
STATUS_DONE = u"Готово"

# Константы Excel
XL_OPENXML_WORKBOOK = 51
XL_VALIDATE_LIST = 3
XL_VALID_ALERT_STOP = 1
XL_BETWEEN = 1
XL_EXPRESSION = 2
XL_TOP = -4160
XL_CENTER = -4108
XL_SHEET_HIDDEN = 0


class ExcelError(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


def _rgb(r, g, b):
    return r + g * 256 + b * 65536


def _col(idx):
    return u"ABCDEFGHIJKLMNOPQRSTUVWXYZ"[idx]


def _excel_date(value):
    """Дата → число Excel (OLE Automation date). Число кладётся в общий
    массив данных, а формат даты задаётся колонке (см. _date_formats):
    так дата пишется надёжно. Присваивание DateTime через Range.Value из
    IronPython (у Value в Excel есть параметр) молча не срабатывало —
    ячейки «Срок» и «Дата письма» оставались пустыми."""
    if isinstance(value, datetime.datetime):
        dt = DateTime(value.year, value.month, value.day, value.hour, value.minute, 0)
    elif isinstance(value, datetime.date):
        dt = DateTime(value.year, value.month, value.day)
    else:
        return None
    return dt.ToOADate()


def _cell_text(value):
    text = u"" if value is None else unicode(value)
    # Строка, начинающаяся с «=», «+», «-», «@», иначе станет формулой
    if text[:1] in (u"=", u"+", u"-", u"@"):
        text = u"'" + text
    return text


def default_output_path(now=None):
    now = now or datetime.datetime.now()
    docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments)
    folder = os.path.join(docs, u"Задачи из почты")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return os.path.join(folder, u"Задачи_{}.xlsx".format(now.strftime("%Y-%m-%d_%H%M")))


def save_tasks(rows, path):
    """
    rows — уже отсортированные задачи (см. email_tasks_core.normalize_task).
    Сохраняет книгу в path и оставляет её открытой в видимом Excel.
    Возвращает список некритичных предупреждений.
    """
    com_type = Type.GetTypeFromProgID("Excel.Application")
    if com_type is None:
        raise ExcelError(u"Excel не найден (COM-объект Excel.Application не зарегистрирован).")
    try:
        xl = Activator.CreateInstance(com_type)
    except Exception as ex:
        raise ExcelError(u"Не удалось запустить Excel:\n{}".format(ex))

    try:
        xl.Visible = False
        xl.DisplayAlerts = False
        xl.ScreenUpdating = False
        warnings = []

        wb = xl.Workbooks.Add()
        ws = wb.Worksheets.Item(1)
        lists = wb.Worksheets.Add()  # добавляется перед активным листом — порядок не важен, лист скрыт
        lists.Name = u"Списки"
        ws.Name = u"Задачи"

        # --- скрытый лист со списком статусов и «сегодня»
        for i, status in enumerate(STATUSES):
            lists.Range(u"A{}".format(i + 1)).Value2 = status
        lists.Range(u"B1").Formula = u"=TODAY()"
        wb.Names.Add(u"StatusList", u"='Списки'!$A$1:$A${}".format(len(STATUSES)))
        wb.Names.Add(u"TodayDate", u"='Списки'!$B$1")
        lists.Visible = XL_SHEET_HIDDEN

        # --- данные одним присваиванием 2D-массива (по ячейке через COM медленно)
        n_rows = len(rows) + 1
        n_cols = len(COLUMNS)
        data = Array.CreateInstance(Object, n_rows, n_cols)
        for c, (title, _width) in enumerate(COLUMNS):
            data[0, c] = title
        for r, row in enumerate(rows, start=1):
            values = [
                r,
                _cell_text(row.get("task")),
                _cell_text(row.get("requester")),
                _excel_date(row.get("deadline")),
                _cell_text(row.get("priority")),
                STATUSES[0],
                _cell_text(row.get("comment")),
                _cell_text(row.get("subject")),
                _cell_text(row.get("sender")),
                _excel_date(row.get("received")),
            ]
            for c, value in enumerate(values):
                data[r, c] = value

        last_col = _col(n_cols - 1)
        last_row = n_rows
        full = ws.Range(u"A1:{}{}".format(last_col, last_row))
        full.Value2 = data

        # --- оформление
        ws.Cells.Font.Name = u"Arial"
        ws.Cells.Font.Size = 10
        for c, (_title, width) in enumerate(COLUMNS):
            ws.Columns.Item(c + 1).ColumnWidth = width

        header = ws.Range(u"A1:{}1".format(last_col))
        header.Font.Bold = True
        header.Interior.Color = _rgb(221, 235, 247)
        header.VerticalAlignment = XL_CENTER
        header.WrapText = True

        full.VerticalAlignment = XL_TOP
        full.WrapText = True
        ws.Range(u"A2:A{}".format(max(last_row, 2))).HorizontalAlignment = XL_CENTER
        date_fmt, datetime_fmt = _date_formats(xl, lists.Range(u"C1"))
        _set_format(ws.Range(u"D:D"), date_fmt)
        _set_format(ws.Range(u"J:J"), datetime_fmt)

        borders = full.Borders
        borders.LineStyle = 1
        borders.Color = _rgb(191, 191, 191)

        # --- выпадающий список статусов (с запасом строк под ручные задачи)
        status_range = ws.Range(u"F2:F{}".format(last_row + 200))
        status_range.Validation.Delete()
        status_range.Validation.Add(XL_VALIDATE_LIST, XL_VALID_ALERT_STOP, XL_BETWEEN, u"=StatusList")
        status_range.Validation.IgnoreBlank = True
        status_range.Validation.InCellDropdown = True

        if rows:
            try:
                _add_conditional_formats(ws, last_col, last_row)
            except Exception as ex:
                warnings.append(u"Условное форматирование не применилось: {}".format(ex))

        full.AutoFilter()

        wb.SaveAs(path, XL_OPENXML_WORKBOOK)
    except ExcelError:
        _quit(xl)
        raise
    except Exception as ex:
        _quit(xl)
        raise ExcelError(u"Ошибка при заполнении/сохранении книги Excel:\n{}".format(ex))

    # --- показать файл; закрепление шапки надёжно работает только в видимом окне
    try:
        xl.ScreenUpdating = True
        xl.Visible = True
        xl.UserControl = True
        xl.DisplayAlerts = True
        ws.Activate()
        window = xl.ActiveWindow
        window.FreezePanes = False
        window.SplitColumn = 0
        window.SplitRow = 1
        window.FreezePanes = True
        ws.Range(u"A2").Select()
        wb.Save()
    except Exception:
        warnings.append(u"Не удалось закрепить шапку таблицы (файл сохранён).")
    return warnings


_DATE_TEXT_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$")
_TEST_DATE = 46290.5  # 25.09.2026 12:00


def _set_format(rng, fmt):
    """fmt — (код формата, свойство: NumberFormat или NumberFormatLocal)."""
    code, prop = fmt
    setattr(rng, prop, code)


def _international_codes(xl):
    """Буквы дня/месяца/года/часа/минуты в языке этого Excel
    (Application.International: xlDayCode=21, xlMonthCode=20, xlYearCode=19,
    xlHourCode=22, xlMinuteCode=23)."""
    def get(index):
        try:
            return unicode(xl.International[index])
        except Exception:
            return unicode(xl.International(index))
    return get(21), get(20), get(19), get(22), get(23)


def _date_formats(xl, probe):
    """
    Форматы «дата» и «дата и время» для колонок. Через COM из IronPython
    русский Excel может разбирать NumberFormat в своём языке («ДД.ММ.ГГГГ»),
    а не в английском («dd.mm.yyyy»), — тогда формат пишется буквально и
    вместо даты в ячейке виден текст «dd.mm.yyyy». Поэтому пробуем варианты
    на служебной ячейке probe (скрытый лист) и берём первый, при котором
    дата реально отображается как «ДД.ММ.ГГГГ ЧЧ:ММ».
    """
    candidates = []
    try:
        d, m, y, h, n = _international_codes(xl)
        candidates.append((u"{0}{0}.{1}{1}.{2}{2}{2}{2}".format(d, m, y),
                           u"{0}{0}:{1}{1}".format(h, n), u"NumberFormatLocal"))
    except Exception:
        pass
    candidates.append((u"dd.mm.yyyy", u"hh:mm", u"NumberFormat"))
    candidates.append((u"ДД.ММ.ГГГГ", u"чч:мм", u"NumberFormatLocal"))
    candidates.append((u"dd.mm.yyyy", u"hh:mm", u"NumberFormatLocal"))

    # Узкая колонка показала бы «#####» вместо даты — расширяем
    probe.ColumnWidth = 30
    probe.Value2 = _TEST_DATE
    try:
        for date_code, time_code, prop in candidates:
            try:
                setattr(probe, prop, u"{} {}".format(date_code, time_code))
                text = unicode(probe.Text).strip()
            except Exception:
                continue
            if _DATE_TEXT_RE.match(text):
                return (date_code, prop), (u"{} {}".format(date_code, time_code), prop)
    finally:
        try:
            probe.Clear()
        except Exception:
            pass
    # Ничего не подошло — английские коды как есть (лучше, чем ничего)
    return (u"m/d/yyyy", u"NumberFormat"), (u"m/d/yyyy h:mm", u"NumberFormat")


def _add_conditional_formats(ws, last_col, last_row):
    """Порядок важен: первое правило — высший приоритет; «Готово» с
    StopIfTrue гасит красный/жёлтый у завершённых задач.

    Относительные ссылки в формулах условного форматирования Excel
    отсчитывает от активной ячейки — поэтому перед добавлением правил
    активируем левую верхнюю ячейку диапазона (A2)."""
    ws.Activate()
    ws.Range(u"A2").Select()

    rows_range = ws.Range(u"A2:{}{}".format(last_col, last_row))
    done = rows_range.FormatConditions.Add(XL_EXPRESSION, Missing.Value, u'=$F2="{}"'.format(STATUS_DONE))
    done.Font.Color = _rgb(128, 128, 128)
    done.Interior.Color = _rgb(242, 242, 242)
    done.StopIfTrue = True

    ws.Range(u"D2").Select()
    deadline_range = ws.Range(u"D2:D{}".format(last_row))
    overdue = deadline_range.FormatConditions.Add(
        XL_EXPRESSION, Missing.Value,
        u'=($D2<>"")*($D2<TodayDate)*($F2<>"{}")'.format(STATUS_DONE))
    overdue.Font.Color = _rgb(192, 0, 0)
    overdue.Font.Bold = True
    overdue.Interior.Color = _rgb(255, 199, 206)

    ws.Range(u"E2").Select()
    prio_range = ws.Range(u"E2:E{}".format(last_row))
    high = prio_range.FormatConditions.Add(XL_EXPRESSION, Missing.Value, u'=$E2="высокий"')
    high.Interior.Color = _rgb(255, 235, 156)

    ws.Range(u"A2").Select()


def _quit(xl):
    try:
        xl.DisplayAlerts = False
        for i in range(xl.Workbooks.Count, 0, -1):
            xl.Workbooks.Item(i).Close(False)
        xl.Quit()
    except Exception:
        pass
