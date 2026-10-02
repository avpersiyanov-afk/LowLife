# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «Задачи из почты» (Mail.panel) — без Revit API,
COM и .NET, чтобы её можно было проверить обычным Python вне Revit.

- trim_body: отрезает историю переписки и ограничивает длину текста;
- make_batches: делит письма на пачки ~30k символов (по вызову claude на пачку);
- build_request: собирает текст запроса (промпт + сегодняшняя дата + письма);
- parse_tasks_json: устойчиво вытаскивает {"tasks": [...]} из ответа модели;
- normalize_task / sort_rows: приводит задачи к единому виду и сортирует
  приоритет → срок → дата письма.

Письмо здесь — словарь: id (int, сквозной номер), received (datetime),
sender, to, cc, subject, body (unicode).
"""

import re
import json
import datetime

try:
    unicode
except NameError:  # CPython 3 — только для локальной проверки вне Revit
    unicode = str

MAX_BODY_CHARS = 4000
BATCH_CHARS = 30000

PRIORITY_HIGH = u"высокий"
PRIORITY_MEDIUM = u"средний"
PRIORITY_LOW = u"низкий"
PRIORITY_ORDER = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}

# Строки, с которых начинается процитированная история переписки. Ищем их
# в начале строки (после пробелов/«>»): Outlook вставляет шапку
# «От: ... Отправлено: ...», Gmail/Thunderbird — «... пишет:».
_HISTORY_PATTERNS = [
    re.compile(u"^[ \\t>]*-{2,}\\s*Original Message\\s*-{2,}", re.I | re.M | re.U),
    re.compile(u"^[ \\t>]*-{2,}\\s*Исходное сообщение\\s*-{2,}", re.I | re.M | re.U),
    re.compile(u"^[ \\t>]*-{2,}\\s*Пересылаемое сообщение\\s*-{2,}", re.I | re.M | re.U),
    re.compile(u"^[ \\t>]*-{2,}\\s*Forwarded message\\s*-{2,}", re.I | re.M | re.U),
    re.compile(u"^[ \\t>]*(От|From)\\s*:\\s*\\S", re.I | re.M | re.U),
    re.compile(u"^[ \\t>]*[^\\n]{0,200}\\s(пишет|написал|написала|wrote)\\s*:\\s*$", re.I | re.M | re.U),
    # Чистая линия-разделитель Outlook перед шапкой ответа
    re.compile(u"^[ \\t]*_{10,}[ \\t]*$", re.M | re.U),
]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _u(value):
    if value is None:
        return u""
    if isinstance(value, unicode):
        return value
    try:
        return unicode(value)
    except Exception:
        try:
            return value.decode("utf-8", "replace")
        except Exception:
            return u""


def trim_body(text, max_chars=MAX_BODY_CHARS):
    """Текст письма без цитируемой истории, не длиннее max_chars."""
    text = _u(text).replace(u"\r\n", u"\n").replace(u"\r", u"\n")

    cut = len(text)
    for pattern in _HISTORY_PATTERNS:
        match = pattern.search(text)
        # Маркер в самой первой строке — это не история, а, например,
        # пересланное письмо целиком: тогда его не режем, иначе текста не останется.
        if match and match.start() > 0 and match.start() < cut:
            cut = match.start()
    text = text[:cut]

    # Схлопываем пустые строки и хвостовые пробелы — экономим символы пачки.
    lines = [line.rstrip() for line in text.split(u"\n")]
    compact = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank and compact:
                compact.append(u"")
            blank = True
            continue
        blank = False
        compact.append(line)
    text = u"\n".join(compact).strip()

    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + u"\n[…текст обрезан…]"
    return text


def format_email(email):
    """Одно письмо в текстовом виде для запроса к модели."""
    received = email.get("received")
    if isinstance(received, datetime.datetime):
        received_text = received.strftime("%Y-%m-%d %H:%M")
    else:
        received_text = _u(received)
    parts = [
        u"=== Письмо email_id={} ===".format(email.get("id")),
        u"Дата: {}".format(received_text),
        u"От: {}".format(_u(email.get("sender"))),
        u"Кому: {}".format(_u(email.get("to"))),
    ]
    if email.get("folder"):
        parts.insert(2, u"Папка: {}".format(_u(email.get("folder"))))
    if email.get("cc"):
        parts.append(u"Копия: {}".format(_u(email.get("cc"))))
    parts.append(u"Тема: {}".format(_u(email.get("subject"))))
    parts.append(u"Текст:")
    parts.append(_u(email.get("body")) or u"(пусто)")
    return u"\n".join(parts)


def make_batches(emails, batch_chars=BATCH_CHARS):
    """Список пачек писем: суммарный текст пачки ≈ не больше batch_chars.
    Письмо, которое само больше лимита, идёт отдельной пачкой."""
    batches = []
    current = []
    size = 0
    for email in emails:
        length = len(format_email(email))
        if current and size + length > batch_chars:
            batches.append(current)
            current = []
            size = 0
        current.append(email)
        size += length
    if current:
        batches.append(current)
    return batches


def build_request(prompt_text, emails, today):
    """Полный текст, который уходит в stdin claude -p."""
    if isinstance(today, (datetime.date, datetime.datetime)):
        today = today.strftime("%Y-%m-%d")
    parts = [
        _u(prompt_text).strip(),
        u"",
        u"Сегодняшняя дата: {}.".format(today),
        u"Писем в этой части: {}.".format(len(emails)),
        u"",
    ]
    for email in emails:
        parts.append(format_email(email))
        parts.append(u"")
    return u"\n".join(parts)


class ParseError(Exception):
    pass


def _strip_fences(text):
    text = text.strip()
    fence = re.search(u"```(?:json|JSON)?\\s*(.*?)```", text, re.S | re.U)
    if fence:
        return fence.group(1).strip()
    # Открывающая обёртка без закрывающей (ответ оборвался)
    if text.startswith(u"```"):
        text = re.sub(u"^```(?:json|JSON)?", u"", text).strip()
    return text


def _balanced_objects(text):
    """Все подстроки вида {...} верхнего уровня (с учётом строк в кавычках)."""
    result = []
    depth = 0
    start = None
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == u"\\":
                escape = True
            elif ch == u'"':
                in_str = False
            continue
        if ch == u'"':
            in_str = True
        elif ch == u"{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == u"}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                result.append(text[start:i + 1])
                start = None
    return result


def parse_tasks_json(text):
    """
    Список задач (словарей) из ответа модели. Понимает ответ в ```-обёртке,
    с пояснениями до/после JSON, голый массив. Бросает ParseError, если
    ничего похожего на {"tasks": [...]} в ответе нет.
    """
    raw = _u(text)
    if not raw.strip():
        raise ParseError(u"Пустой ответ.")

    candidates = [_strip_fences(raw), raw.strip()]
    for candidate in list(candidates):
        candidates.extend(_balanced_objects(candidate))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("tasks"), list):
            return [t for t in data["tasks"] if isinstance(t, dict)]
        if isinstance(data, list) and all(isinstance(t, dict) for t in data):
            return data

    # Голый массив задач без обёртки {"tasks": ...}
    stripped = _strip_fences(raw)
    lb, rb = stripped.find(u"["), stripped.rfind(u"]")
    if lb != -1 and rb > lb:
        try:
            data = json.loads(stripped[lb:rb + 1])
            if isinstance(data, list):
                return [t for t in data if isinstance(t, dict)]
        except Exception:
            pass

    raise ParseError(u"В ответе не найден JSON вида {\"tasks\": [...]}.")


def _norm_priority(value):
    v = _u(value).strip().lower()
    if v.startswith(u"выс") or v in (u"high", u"h"):
        return PRIORITY_HIGH
    if v.startswith(u"низ") or v in (u"low", u"l"):
        return PRIORITY_LOW
    return PRIORITY_MEDIUM


def _norm_deadline(value):
    v = _u(value).strip()
    if not v or v.lower() in (u"null", u"none", u"нет", u"-"):
        return None
    v = v[:10]
    if not _DATE_RE.match(v):
        return None
    try:
        return datetime.datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        return None


def normalize_task(task, emails_by_id):
    """Задача модели → строка результата (словарь с привязкой к письму).
    Задачи с несуществующим email_id всё равно сохраняются (без письма)."""
    try:
        email_id = int(task.get("email_id"))
    except Exception:
        email_id = None
    email = emails_by_id.get(email_id) or {}
    comment = task.get("comment")
    return {
        "email_id": email_id,
        "task": _u(task.get("task")).strip(),
        "requester": _u(task.get("requester")).strip() or _u(email.get("sender_name") or email.get("sender")),
        "deadline": _norm_deadline(task.get("deadline")),
        "priority": _norm_priority(task.get("priority")),
        "comment": u"" if comment is None else _u(comment).strip(),
        "subject": _u(email.get("subject")),
        "sender": _u(email.get("sender")),
        "received": email.get("received"),
    }


def sort_rows(rows):
    """Приоритет (высокий первым) → срок (ближайший первым, без срока — в конце)
    → дата письма (новые первыми)."""
    far = datetime.date(9999, 12, 31)
    epoch = datetime.datetime(1900, 1, 1)

    def key(row):
        received = row.get("received")
        if not isinstance(received, datetime.datetime):
            received = epoch
        age = (datetime.datetime(2100, 1, 1) - received).total_seconds()
        return (
            PRIORITY_ORDER.get(row.get("priority"), 1),
            row.get("deadline") or far,
            age,
        )

    return sorted(rows, key=key)


def load_test_emails(path, now=None):
    """Выдуманные письма тестового режима из JSON (см. test_emails.json
    кнопки): дата письма = now - days_ago, время — time «ЧЧ:ММ»."""
    import io
    now = now or datetime.datetime.now()
    with io.open(path, "r", encoding="utf-8") as f:
        data = json.loads(f.read())
    raw = data.get("emails") if isinstance(data, dict) else data
    emails = []
    for entry in raw or []:
        try:
            hour, minute = [int(x) for x in _u(entry.get("time") or u"09:00").split(u":")[:2]]
        except Exception:
            hour, minute = 9, 0
        day = now - datetime.timedelta(days=int(entry.get("days_ago") or 0))
        sender = _u(entry.get("sender"))
        emails.append({
            "id": len(emails) + 1,
            "received": datetime.datetime(day.year, day.month, day.day, hour, minute),
            "sender": sender,
            "sender_name": sender.split(u"<")[0].strip(),
            "to": _u(entry.get("to")),
            "cc": _u(entry.get("cc")),
            "subject": _u(entry.get("subject")),
            "body": trim_body(entry.get("body")),
        })
    emails.sort(key=lambda e: e["received"], reverse=True)
    for i, email in enumerate(emails, start=1):
        email["id"] = i
    return emails
