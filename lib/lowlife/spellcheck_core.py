# -*- coding: utf-8 -*-
"""
Чистая логика кнопки «Проверка орфографии» (Tools.panel/SpellCheck) — без
Revit API и .NET, тестируется и под Python 3 (tests/test_spellcheck_core.py).

Поток данных:

    collect_items(notes)      одинаковые тексты склеиваются в один пункт —
                              ИИ видит каждую надпись один раз
    make_batches(items)       пачки ≈BATCH_CHARS символов
    build_request(prompt, batch)
    parse_fixes(answer)       {id: исправленный текст} из JSON-ответа
    review_fix(old, new)      отсеивает пустые / без изменений / переписанные
    full_text(plain, body)    вернуть ведущие/хвостовые пробелы и разделитель
                              строк Revit
    replacement_spans(old, new)
                              минимальные замены (начало, длина, текст) по
                              словам — их применяют к FormattedText заметки,
                              чтобы не сбросить жирный/курсив и списки

Revit хранит переводы строк в тексте заметки как "\\r" (и добавляет "\\r"
в конце); ИИ получает и возвращает "\\n", обратно переводится тем же
разделителем, что был в исходном тексте, — длины совпадают, позиции замен
считаются по исходному тексту заметки.
"""

import re
import json
import difflib

from lowlife.email_tasks_core import _strip_fences, _balanced_objects

BATCH_CHARS = 6000
# Ниже этого сходства (0..1) «исправление» считается переписыванием текста
# и не применяется
MIN_SIMILARITY = 0.6

SYSTEM_PROMPT = (
    u"You are a careful proofreader of texts on engineering drawings. "
    u"Fix only spelling, grammar, punctuation and typos. "
    u"Follow the instructions in the message exactly and reply with JSON only."
)

_LETTER_RE = re.compile(u"[^\\W\\d_]", re.U)
_TOKEN_RE = re.compile(u"\\w+|\\s+|[^\\w\\s]", re.U)


class ParseError(Exception):
    pass


def _u(value):
    if value is None:
        return u""
    try:
        return unicode(value)  # noqa: F821 — IronPython
    except NameError:
        return str(value)


def has_letters(text):
    return bool(_LETTER_RE.search(text or u""))


def line_separator(plain):
    if u"\r\n" in plain:
        return u"\r\n"
    if u"\r" in plain:
        return u"\r"
    return u"\n"


def split_text(plain):
    """(ведущие пробелы, тело с "\\n" вместо разделителя строк, хвостовые пробелы)."""
    plain = _u(plain)
    body = plain.strip()
    if not body:
        return plain, u"", u""
    start = plain.index(body)
    head, tail = plain[:start], plain[start + len(body):]
    return head, body.replace(line_separator(plain), u"\n"), tail


def full_text(plain, new_body):
    """Полный текст заметки: исправленное тело с исходными пробелами по краям
    и исходным разделителем строк."""
    head, _body, tail = split_text(plain)
    body = _u(new_body).replace(u"\r\n", u"\n").replace(u"\r", u"\n")
    return head + body.replace(u"\n", line_separator(plain)) + tail


def collect_items(notes):
    """
    notes — [(ключ_элемента, текст), ...]. Возвращает пункты для ИИ:
    [{"id": 1, "text": тело, "notes": [(ключ, текст), ...]}, ...] — один
    пункт на каждый уникальный текст; без букв (только цифры/знаки) —
    пропускаются.
    """
    items = []
    by_body = {}
    for key, plain in notes:
        plain = _u(plain)
        _head, body, _tail = split_text(plain)
        if not has_letters(body):
            continue
        item = by_body.get(body)
        if item is None:
            item = {"id": len(items) + 1, "text": body, "notes": []}
            by_body[body] = item
            items.append(item)
        item["notes"].append((key, plain))
    return items


def make_batches(items, batch_chars=BATCH_CHARS):
    batches, current, size = [], [], 0
    for item in items:
        length = len(item["text"]) + 20
        if current and size + length > batch_chars:
            batches.append(current)
            current, size = [], 0
        current.append(item)
        size += length
    if current:
        batches.append(current)
    return batches


def build_request(prompt_text, batch):
    payload = {"items": [{"id": item["id"], "text": item["text"]} for item in batch]}
    return u"{}\n\nТексты (JSON):\n{}".format(
        _u(prompt_text).strip(), _u(json.dumps(payload, ensure_ascii=False)))


def parse_fixes(text):
    """{id: текст} из ответа модели {"fixes": [{"id": 1, "text": "..."}]}.
    Понимает ```-обёртку, пояснения вокруг JSON и голый массив. Пустой
    список исправлений — нормальный ответ ({}); ParseError — JSON не найден."""
    raw = _u(text)
    if not raw.strip():
        raise ParseError(u"Пустой ответ.")

    candidates = [_strip_fences(raw), raw.strip()]
    for candidate in list(candidates):
        candidates.extend(_balanced_objects(candidate))
    stripped = _strip_fences(raw)
    lb, rb = stripped.find(u"["), stripped.rfind(u"]")
    if lb != -1 and rb > lb:
        candidates.append(stripped[lb:rb + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("fixes"), list):
            data = data["fixes"]
        if not isinstance(data, list):
            continue
        fixes = {}
        for fix in data:
            if not isinstance(fix, dict):
                continue
            try:
                item_id = int(fix.get("id"))
            except Exception:
                continue
            if isinstance(fix.get("text"), (type(u""), type(""))):
                fixes[item_id] = _u(fix["text"])
        return fixes

    raise ParseError(u"В ответе не найден JSON вида {\"fixes\": [...]}.")


# Итог review_fix
FIX_OK = "ok"
FIX_SAME = "same"
FIX_EMPTY = "empty"
FIX_REWRITE = "rewrite"


def similarity(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def review_fix(old_body, new_text):
    """(итог, исправленное тело). Исправление без изменений — FIX_SAME, пустое
    — FIX_EMPTY, слишком непохожее на исходник — FIX_REWRITE (ИИ
    переписал текст вместо правки опечаток)."""
    new_body = _u(new_text).replace(u"\r\n", u"\n").replace(u"\r", u"\n").strip()
    if not new_body:
        return FIX_EMPTY, new_body
    if new_body == old_body:
        return FIX_SAME, new_body
    if similarity(old_body, new_body) < MIN_SIMILARITY:
        return FIX_REWRITE, new_body
    return FIX_OK, new_body


def _tokens(text):
    return _TOKEN_RE.findall(text)


def replacement_spans(old, new):
    """
    Минимальные замены, превращающие old в new: [(начало, длина, текст), ...]
    по возрастанию начала, без пересечений, длина всегда ≥ 1 (у Revit
    TextRange нулевой длины для вставки ненадёжен — вставка приклеивается к
    соседнему слову). Сравнение по словам/пробелам/знакам, а не по буквам:
    замена «превышенИе» → «превышение» затрагивает одно слово целиком.
    """
    old, new = _u(old), _u(new)
    if old == new:
        return []
    if not old:
        return []
    a, b = _tokens(old), _tokens(new)
    offsets = [0]
    for token in a:
        offsets.append(offsets[-1] + len(token))

    ops = []
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i1 == i2:  # вставка — захватить соседний неизменный токен
            if i1 > 0:
                i1, j1 = i1 - 1, j1 - 1
            else:
                i2, j2 = i2 + 1, j2 + 1
        if ops and ops[-1][1] >= i1:
            p1, _p2, q1, _q2 = ops[-1]
            ops[-1] = (p1, i2, q1, j2)
        else:
            ops.append((i1, i2, j1, j2))

    return [(offsets[i1], offsets[i2] - offsets[i1], u"".join(b[j1:j2]))
            for i1, i2, j1, j2 in ops]


def apply_spans(old, spans):
    """old с применёнными заменами (с конца, как в Revit)."""
    text = _u(old)
    for start, length, replacement in sorted(spans, reverse=True):
        text = text[:start] + replacement + text[start + length:]
    return text


def describe_changes(old, new, limit=6):
    """«превышенИе → превышение; щитов → щитов,» — что именно поменялось."""
    old, new = _u(old), _u(new)
    parts = []
    for start, length, replacement in replacement_spans(old, new):
        before = old[start:start + length].strip() or u"␣"
        after = replacement.strip() or u"␣"
        if before == after:  # поменялись только пробелы
            before, after = repr_spaces(old[start:start + length]), repr_spaces(replacement)
        parts.append(u"{} → {}".format(before, after))
    if len(parts) > limit:
        parts = parts[:limit] + [u"… ещё {}".format(len(parts) - limit)]
    return u"; ".join(parts)


def repr_spaces(text):
    return text.replace(u" ", u"␣").replace(u"\n", u"↵").replace(u"\r", u"↵")
