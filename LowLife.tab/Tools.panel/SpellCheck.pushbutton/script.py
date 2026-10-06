# -*- coding: utf-8 -*-
__title__ = u"Проверка\nорфографии"
__doc__ = (
    u"Проверяет орфографию, грамматику и пунктуацию в текстовых заметках "
    u"модели с помощью ИИ (Claude или ChatGPT — подключение то же, что у "
    u"«Задач из почты»). Найденные исправления показываются списком "
    u"«было → стало», записываются только отмеченные; меняются только "
    u"исправленные слова, форматирование заметки сохраняется.\n\n"
    u"Shift+клик — настройки: способ подключения ИИ, модель, промпт."
)
__author__ = "Pipers"

import os
import io
import datetime

import clr
clr.AddReference("System.Windows.Forms")
from System.Windows.Forms import Application

from pyrevit import revit, forms, script, EXEC_PARAMS

from lowlife import spellcheck_core as core
from lowlife import spellcheck, spellcheck_settings, email_ai

TITLE = u"Проверка орфографии"
BUNDLE_DIR = os.path.dirname(__file__)
PROMPT_FILE = os.path.join(BUNDLE_DIR, "prompt.txt")

try:
    config_mode = bool(EXEC_PARAMS.config_mode)
except Exception:
    config_mode = False


def _read_default_prompt():
    try:
        with io.open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return u""


default_prompt = _read_default_prompt()

if config_mode:
    saved = spellcheck_settings.edit_interactive(default_prompt)
    forms.alert(u"Настройки сохранены." if saved else u"Отменено, настройки не изменены.")
    script.exit()


doc = revit.doc
uidoc = revit.uidoc

settings = spellcheck_settings.load()
prompt_text = spellcheck_settings.effective_prompt(settings, default_prompt)
if not prompt_text.strip():
    forms.alert(u"Промпт пуст: в настройках нет своего текста, а стандартный "
                u"файл не прочитался:\n{}\n\nВпишите промпт в настройках "
                u"(Shift+клик по кнопке).".format(PROMPT_FILE),
                exitscript=True)

try:
    engine = email_ai.prepare(settings, system_prompt=core.SYSTEM_PROMPT)
except email_ai.AIError as ex:
    forms.alert(ex.message, title=TITLE, exitscript=True)


# --- 1. Какие заметки проверять
selected = spellcheck.selected_text_notes(doc, uidoc)
scopes = []
if selected:
    scopes.append((u"Выделенные ({})".format(len(selected)), spellcheck.SCOPE_SELECTION))
scopes.append((u"Текущий вид", spellcheck.SCOPE_VIEW))
scopes.append((u"Вся модель", spellcheck.SCOPE_MODEL))
choice = forms.alert(u"Какие текстовые заметки проверить?", title=TITLE,
                     options=[label for label, _scope in scopes])
if not choice:
    script.exit()
scope = dict(scopes)[choice]

all_notes = spellcheck.collect_text_notes(doc, scope, doc.ActiveView, selected)
notes = []
skipped = []  # (заметка, причина)
for note in all_notes:
    reason = spellcheck.skip_reason(doc, note)
    if reason:
        skipped.append((note, reason))
    else:
        notes.append(note)

items = core.collect_items([(i, spellcheck.plain_text(note)) for i, note in enumerate(notes)])
if not items:
    forms.alert(u"Нет текстовых заметок с текстом для проверки ({}).{}".format(
        choice.lower(),
        u"\n\nПропущено заметок (в группах / заняты): {}".format(len(skipped)) if skipped else u""),
        title=TITLE, exitscript=True)


def _pump():
    """Дать окну прогресса перерисоваться и обработать «Отмена»."""
    try:
        Application.DoEvents()
    except Exception:
        pass


def _set_indeterminate(pb, value):
    # Свойство есть не во всех версиях pyRevit
    try:
        pb.indeterminate = value
    except Exception:
        pass


def _save_raw_answer(part, text):
    folder = os.path.join(os.environ.get("TEMP") or os.path.expanduser("~"), u"LowLifeSpellCheck")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    path = os.path.join(folder, u"answer_{}_part{}.txt".format(
        datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), part))
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


# --- 2. Проверка в ИИ, пачками
items_by_id = dict((item["id"], item) for item in items)
proposals = []   # {"item", "new_body", "changes"}
rejected = []    # (item, исправление ИИ) — ИИ переписал текст, а не исправил
batch_errors = []
fatal_error = None
cancelled = False

with forms.ProgressBar(title=u"Проверка орфографии…", cancellable=True) as pb:
    batches = core.make_batches(items)
    total = len(batches)
    for part, batch in enumerate(batches, start=1):
        pb.title = u"Проверка текста в {}: часть {} из {} (надписей: {})".format(
            engine.name, part, total, len(batch))
        pb.update_progress(part - 1, total)
        _set_indeterminate(pb, True)
        _pump()

        def ai_tick():
            _pump()
            return pb.cancelled

        try:
            answer = engine.run(core.build_request(prompt_text, batch), tick=ai_tick)
        except email_ai.Cancelled:
            cancelled = True
            break
        except email_ai.AIError as ex:
            text = ex.message
            if ex.details:
                text += u"\n\nПодробности:\n" + ex.details[:1500]
            if ex.fatal:
                fatal_error = text
                break
            batch_errors.append(u"Часть {} из {}: {}".format(part, total, text))
            continue

        try:
            fixes = core.parse_fixes(answer)
        except core.ParseError as ex:
            raw_path = _save_raw_answer(part, answer)
            batch_errors.append(u"Часть {} из {}: не удалось разобрать ответ {} ({}). "
                                u"Ответ сохранён: {}".format(part, total, engine.name, ex, raw_path))
            continue

        batch_ids = set(item["id"] for item in batch)
        for item_id, new_text in sorted(fixes.items()):
            if item_id not in batch_ids:
                continue
            item = items_by_id[item_id]
            status, new_body = core.review_fix(item["text"], new_text)
            if status == core.FIX_OK:
                proposals.append({"item": item, "new_body": new_body,
                                  "changes": core.describe_changes(item["text"], new_body)})
            elif status == core.FIX_REWRITE:
                rejected.append((item, new_body))

    _set_indeterminate(pb, False)
    pb.update_progress(total, total)

if cancelled:
    forms.alert(u"Отменено пользователем. В модели ничего не изменено.", title=TITLE, exitscript=True)
if fatal_error:
    forms.alert(fatal_error, title=TITLE, exitscript=True)


# --- 3. Выбор исправлений
class FixOption(object):
    def __init__(self, proposal):
        self.proposal = proposal
        count = len(proposal["item"]["notes"])
        new_short = proposal["new_body"].replace(u"\n", u" ↵ ")
        if len(new_short) > 90:
            new_short = new_short[:90] + u"…"
        self.name = u"{}    «{}»{}".format(
            proposal["changes"], new_short, u"   ×{}".format(count) if count > 1 else u"")


chosen = []
if proposals:
    picked = forms.SelectFromList.show(
        [forms.TemplateListItem(FixOption(p), checked=True, name_attr="name") for p in proposals],
        title=u"Исправления ИИ — снимите отметку с ненужных",
        button_name=u"Исправить отмеченные",
        multiselect=True,
        width=1000,
        height=650,
    )
    if picked is None:
        forms.alert(u"Отменено. В модели ничего не изменено.", title=TITLE, exitscript=True)
    chosen = [getattr(option, "proposal", None) for option in picked]
    chosen = [p for p in chosen if p]


# --- 4. Запись
applied = []      # (proposal, [ElementId])
plain_notes = []  # ElementId, где форматирование сброшено
failed = []       # (ElementId, причина)
commit_error = None

if chosen:
    try:
        with revit.Transaction(TITLE):
            for proposal in chosen:
                ids = []
                for index, old_plain in proposal["item"]["notes"]:
                    note = notes[index]
                    new_plain = core.full_text(old_plain, proposal["new_body"])
                    try:
                        how = spellcheck.apply_fix(note, old_plain, new_plain)
                    except Exception as ex:
                        failed.append((note.Id, unicode(ex)))
                        continue
                    ids.append(note.Id)
                    if how == spellcheck.APPLIED_PLAIN:
                        plain_notes.append(note.Id)
                if ids:
                    applied.append((proposal, ids))
    except Exception as ex:
        commit_error = unicode(ex)
        applied, plain_notes = [], []


# --- Отчёт
output = script.get_output()
output.print_md(u"## Проверка орфографии — {}".format(
    datetime.datetime.now().strftime("%d.%m.%Y %H:%M")))
output.print_md(u"Область: **{}**, заметок: **{}**, уникальных надписей: **{}**, "
                u"с исправлениями: **{}**. ИИ: {}.".format(
                    choice, len(all_notes), len(items), len(proposals), engine.description))

if commit_error:
    output.print_md(u"> ⚠ Revit не сохранил изменения, модель не изменена: " + commit_error)
    forms.alert(u"Revit не сохранил изменения, модель не изменена:\n\n" + commit_error, title=TITLE)

if applied:
    output.print_md(u"### Исправлено")
    rows = []
    for proposal, ids in applied:
        rows.append([proposal["changes"], proposal["new_body"].replace(u"\n", u" ↵ "),
                     output.linkify(ids)])
    output.print_table(table_data=rows, columns=[u"Что исправлено", u"Текст", u"Заметки"])
elif not proposals and not batch_errors:
    output.print_md(u"Ошибок не найдено.")
elif proposals and not chosen:
    output.print_md(u"Ни одно исправление не отмечено — модель не изменена.")

if plain_notes:
    output.print_md(u"> ⚠ В этих заметках текст записан целиком, форматирование "
                    u"(жирный/курсив/списки) сброшено: " + output.linkify(plain_notes))

if failed:
    output.print_md(u"### Не удалось записать")
    for element_id, reason in failed:
        output.print_md(u"- {} — {}".format(output.linkify(element_id), reason))

if skipped:
    output.print_md(u"### Пропущены, не проверялись")
    for note, reason in skipped:
        output.print_md(u"- {} — {}".format(output.linkify(note.Id), reason))

if rejected:
    output.print_md(u"### Отклонено: ИИ переписал текст, а не исправил ошибки")
    for item, new_body in rejected:
        output.print_md(u"- «{}» → «{}»".format(item["text"], new_body))

if batch_errors:
    output.print_md(u"### Ошибки")
    for err in batch_errors:
        output.print_md(u"- " + err.replace(u"\n", u" "))
    if not proposals:
        forms.alert(u"Не удалось проверить текст:\n\n" + u"\n\n".join(batch_errors)[:3000],
                    title=TITLE)
