# -*- coding: utf-8 -*-
"""Перевод окон и сообщений LowLife на английский — инструмент разработчика (CPython 3.8+).

    python tools/i18n_tool.py wrap FILE...      # обернуть строки интерфейса в tr(...)
    python tools/i18n_tool.py mark FILE VARS IDX # пометить N_(...) подписи в таблицах-данных
    python tools/i18n_tool.py wrapat FILE:LINE…  # обернуть русские строки на этих строках файла
    python tools/i18n_tool.py todo FILE...       # русские строки, ещё не обёрнутые (на просмотр)
    python tools/i18n_tool.py extract [--write] # собрать все tr()/N_() в lib/lowlife/locale/en.json
    python tools/i18n_tool.py check             # что не переведено / не совпали подстановки

`wrap` находит в файле русские строки там, где их видит пользователь: присваивание
``.Text``/``.Content``/``.Title``/``.ToolTip``/``.Header``, аргументы ``forms.alert``,
``print``, ``output.print_md`` и т. п. (вместе с ``.format``/``%``/``+``), оборачивает их в
``tr(...)`` и добавляет ``from lowlife.i18n import tr``. Строки-данные (ключевые слова поиска,
имена параметров, варианты, которые потом сравниваются) он не трогает — их, если это подписи,
помечают вручную: ``N_(u"…")`` в данных и ``tr(...)`` при показе. Результат `wrap` надо
просмотреть глазами (``git diff``).

`extract --write` дописывает в каталог новые строки с пустым переводом — их заполняют руками;
``tests/test_i18n.py`` падает, пока перевода нет или в нём другие подстановки (``{}``, ``%s``).
"""
import ast
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "lib", "lowlife", "locale", "en.json")
SCAN_DIRS = ("lib", "LowLife.tab", "hooks", "apps")
CYRILLIC = re.compile(u"[Ѐ-ӿ]")
PLACEHOLDER = re.compile(r"\{[^{}]*\}|%[-+ #0]*\d*(?:\.\d+)?[sdfrxi%]")

UI_ATTRS = {"Text", "Content", "Title", "ToolTip", "Header", "Watermark"}
UI_CALLS = {"alert", "toast", "print_md", "print_html", "ask_for_string", "print", "set_title",
            "show_balloon", "ask_to_use_selected"}
# у этих вызовов — только именованные title=/button_name=/…: позиционный аргумент — варианты выбора
UI_CALLS_KW_ONLY = {"show", "pick_file", "save_file", "pick_folder", "select_views", "ask_for_one_item",
                    "show_dialog", "print_table"}
SECTION = re.compile(r"^\[([^\]]+)\]\s*(.*)$", re.S)
UI_KEYWORDS = {"title", "message", "msg", "sub_msg", "button_name", "prompt", "columns", "yes_text",
               "no_text", "header"}


def _is_cyrillic_str(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and CYRILLIC.search(node.value)


def _ui_strings(expr, out):
    """Строковые константы выражения, которые увидит пользователь."""
    if _is_cyrillic_str(expr):
        out.append(expr)
    elif isinstance(expr, ast.BinOp) and isinstance(expr.op, (ast.Add, ast.Mod)):
        _ui_strings(expr.left, out)
        if isinstance(expr.op, ast.Add):
            _ui_strings(expr.right, out)
    elif isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "format":
        _ui_strings(expr.func.value, out)
    elif isinstance(expr, ast.IfExp):
        _ui_strings(expr.body, out)
        _ui_strings(expr.orelse, out)
    elif isinstance(expr, (ast.List, ast.Tuple)) and getattr(expr, "_ui_list", False):
        for elt in expr.elts:
            _ui_strings(elt, out)


def _call_name(call):
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


METADATA = {"__title__", "__doc__", "__author__", "__context__", "__helpurl__"}


def _already_wrapped(tree):
    """id() строковых констант, которые не трогать: уже внутри tr(...)/N_(...) или в метаданных
    кнопки pyRevit (__title__/__doc__ — pyRevit читает их из файла как есть)."""
    done = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in METADATA
                                                for t in node.targets):
            for sub in ast.walk(node):
                done.add(id(sub))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) in ("tr", "N_"):
            for sub in ast.walk(node):
                done.add(id(sub))
    return done


def find_ui_strings(tree):
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Attribute) and t.attr in UI_ATTRS for t in node.targets):
                _ui_strings(node.value, found)
        elif isinstance(node, ast.Call) and _call_name(node) in UI_CALLS | UI_CALLS_KW_ONLY:
            if _call_name(node) in UI_CALLS:
                for arg in node.args:
                    _ui_strings(arg, found)
            for kw in node.keywords:
                if kw.arg in UI_KEYWORDS:
                    if kw.arg == "columns" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        kw.value._ui_list = True
                    _ui_strings(kw.value, found)
    done = _already_wrapped(tree)
    unique, seen = [], set()
    for node in found:
        if id(node) in done or id(node) in seen:
            continue
        seen.add(id(node))
        unique.append(node)
    return unique


def binds_tr(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "tr" and isinstance(node.ctx, ast.Store):
            return True
        if isinstance(node, ast.arg) and node.arg == "tr":
            return True
    return False


def _offset(lines, lineno, col_bytes):
    """Позиция символа в тексте по (строка с 1, смещение в байтах UTF-8)."""
    line = lines[lineno - 1]
    col = len(line.encode("utf-8")[:col_bytes].decode("utf-8"))
    return sum(len(x) for x in lines[:lineno - 1]) + col


def _has_tr_import(tree):
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "lowlife.i18n":
            if any(a.name == "tr" for a in node.names):
                return True
    return False


def _import_line(tree):
    """Номер строки (с 0), перед которой вставить импорт: сразу после первого импорта верхнего
    уровня (кроме from __future__), иначе после docstring."""
    for node in tree.body:
        if isinstance(node, ast.Import) or (isinstance(node, ast.ImportFrom) and node.module != "__future__"):
            return node.end_lineno
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        return body[0].end_lineno
    return 0


_I18N_IMPORT = re.compile(r"^from lowlife\.i18n import ([\w, ]+?)(\r?\n)", re.M)


def ensure_import(text, tree, name):
    """Добавить name в «from lowlife.i18n import …» (или вставить такую строку)."""
    m = _I18N_IMPORT.search(text)
    if m:
        names = sorted(set([n.strip() for n in m.group(1).split(",")] + [name]))
        return text[:m.start()] + "from lowlife.i18n import " + ", ".join(names) + m.group(2) + text[m.end():]
    lines = _lines(text)
    eol = "\r\n" if "\r\n" in text else "\n"
    lines.insert(_import_line(tree), "from lowlife.i18n import " + name + eol)
    return "".join(lines)


def _lines(text):
    """Строки с концами — ровно так, как их считает ast (только по переводу строки)."""
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + [parts[-1]]


def wrap_source(text):
    """(новый текст, число обёрнутых строк) — или ValueError, если в модуле есть своя переменная tr."""
    tree = ast.parse(text)
    nodes = find_ui_strings(tree)
    if not nodes:
        return text, 0
    if binds_tr(tree):
        raise ValueError("в модуле есть своя переменная tr — переименуйте её")
    lines = _lines(text)
    spans = []
    for node in nodes:
        start = _offset(lines, node.lineno, node.col_offset)
        end = _offset(lines, node.end_lineno, node.end_col_offset)
        spans.append((start, end))
    out = text
    for start, end in sorted(spans, reverse=True):
        out = out[:start] + "tr(" + out[start:end] + ")" + out[end:]
    out = ensure_import(out, tree, "tr")
    return out, len(nodes)


def mark_source(text, var_names, indexes):
    """Пометить N_(...) русские строки-подписи в таблицах-данных модуля: у переменных var_names
    (список/кортеж кортежей) — элементы с номерами indexes каждого кортежа. (текст, число)."""
    tree = ast.parse(text)
    done = _already_wrapped(tree)
    nodes = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not any(
                isinstance(t, ast.Name) and t.id in var_names for t in node.targets):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            continue
        for row in node.value.elts:
            if not isinstance(row, (ast.Tuple, ast.List)):
                continue
            for i in indexes:
                if i < len(row.elts) and _is_cyrillic_str(row.elts[i]) and id(row.elts[i]) not in done:
                    nodes.append(row.elts[i])
    if not nodes:
        return text, 0
    lines = _lines(text)
    out = text
    for node in sorted(nodes, key=lambda n: (n.lineno, n.col_offset), reverse=True):
        start = _offset(lines, node.lineno, node.col_offset)
        end = _offset(lines, node.end_lineno, node.end_col_offset)
        out = out[:start] + "N_(" + out[start:end] + ")" + out[end:]
    out = ensure_import(out, tree, "N_")
    return out, len(nodes)


def cmd_mark(args):
    path, names, indexes = args[0], args[1].split(","), [int(i) for i in args[2].split(",")]
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    new, count = mark_source(text, set(names), indexes)
    if count:
        with io.open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    print("%4d  %s" % (count, path))


def wrap_lines(text, linenos):
    """Обернуть в tr(...) все русские строки, которые начинаются на строках linenos (с 1)."""
    tree = ast.parse(text)
    done = _already_wrapped(tree)
    if binds_tr(tree):
        raise ValueError("в модуле есть своя переменная tr — переименуйте её")
    nodes = [n for n in ast.walk(tree)
             if _is_cyrillic_str(n) and n.lineno in linenos and id(n) not in done]
    if not nodes:
        return text, 0
    lines = _lines(text)
    out = text
    for node in sorted(nodes, key=lambda n: (n.lineno, n.col_offset), reverse=True):
        start = _offset(lines, node.lineno, node.col_offset)
        end = _offset(lines, node.end_lineno, node.end_col_offset)
        out = out[:start] + "tr(" + out[start:end] + ")" + out[end:]
    return ensure_import(out, tree, "tr"), len(nodes)


def cmd_wrapat(args):
    by_file = {}
    for item in args:
        path, _, line = item.rpartition(":")
        by_file.setdefault(path, set()).add(int(line))
    for path, linenos in by_file.items():
        with io.open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        new, count = wrap_lines(text, linenos)
        if count:
            with io.open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new)
        print("%4d  %s" % (count, path))


def cmd_todo(paths):
    """Русские строки, не обёрнутые в tr()/N_() — просмотреть: данные это или подпись."""
    for path in paths:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        tree = ast.parse(text)
        done = _already_wrapped(tree)
        docstrings = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and body and \
                    isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
            if isinstance(node, ast.Call):
                docstrings.update(id(v) for v in _ctor_nodes(node))  # settings_core переводит сам
        for node in ast.walk(tree):
            if _is_cyrillic_str(node) and id(node) not in done and id(node) not in docstrings:
                short = node.value[:90].replace("\n", " ")
                print("%s:%d: %s" % (os.path.relpath(path, ROOT), node.lineno, short))


def cmd_wrap(paths):
    for path in paths:
        with io.open(path, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        try:
            new, count = wrap_source(text)
        except ValueError as exc:
            print("SKIP %s: %s" % (path, exc))
            continue
        if count:
            with io.open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new)
        print("%4d  %s" % (count, path))


def iter_sources(root=ROOT):
    for top in SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, top)):
            dirnames[:] = [d for d in dirnames if not re.match(r"MyPanel\d+\.panel$", d)
                           and d not in ("__pycache__", "build", "dist")]
            for name in filenames:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


# Подписи, которые settings_core переводит сам при показе: (позиции, именованные, позиция/имя choices)
CTOR_RULES = {
    "TextField": ((1, 2, 3), ("section", "label", "hint"), None),
    "NumberField": ((1, 2, 3), ("section", "label", "hint"), None),
    "ChoiceField": ((1, 2, 4), ("section", "label", "hint"), (3, "choices")),
    "SourceField": ((1, 2, 4), ("section", "label", "hint"), (3, "choices")),  # tray_boxes_settings
    "LevelTemplateField": ((1, 2, 3), ("section", "label", "hint"), None),  # view_range_settings
    "ParamSpec": ((1,), ("label", "note"), None),  # fop_catalog
    "TextSettings": ((1, 2, 3), ("button_name", "heading", "transfer_label", "intro"), None),
    "JsonStore": ((1,), ("label",), None),
}


def _ctor_strings(call):
    """Строки-подписи из вызова конструктора по CTOR_RULES."""
    return [v.value for v in _ctor_nodes(call)]


def _ctor_nodes(call):
    """Узлы русских строк-подписей из вызова конструктора по CTOR_RULES."""
    rule = CTOR_RULES.get(_call_name(call))
    if rule is None:
        return []
    positions, keywords, choices = rule
    values = [call.args[i] for i in positions if i < len(call.args)]
    values += [kw.value for kw in call.keywords if kw.arg in keywords]
    if choices:
        pos, name = choices
        node = call.args[pos] if pos < len(call.args) else next(
            (kw.value for kw in call.keywords if kw.arg == name), None)
        if isinstance(node, (ast.List, ast.Tuple)):
            for pair in node.elts:
                if isinstance(pair, (ast.Tuple, ast.List)) and len(pair.elts) > 1:
                    values.append(pair.elts[1])
    return [v for v in values if _is_cyrillic_str(v)]


def extract_keys(root=ROOT):
    """{русская строка: [файлы]} — первые аргументы tr(u"…") без английского и N_(u"…")."""
    keys = {}
    for path in iter_sources(root):
        with io.open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) in CTOR_RULES:
                for text in _ctor_strings(node):
                    keys.setdefault(text, []).append(os.path.relpath(path, root))
                continue
            if not isinstance(node, ast.Call) or _call_name(node) not in ("tr", "N_") or not node.args:
                continue
            if _call_name(node) == "tr" and (len(node.args) > 1 or node.keywords):
                continue  # tr(ru, en) — перевод прямо в коде
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value:
                where = os.path.relpath(path, root)
                m = SECTION.match(arg.value) if _call_name(node) == "N_" else None
                # «[Раздел] подпись» из таблиц полей: показывается частями — tr(раздел), tr(подпись)
                for key in ([m.group(1), m.group(2)] if m else [arg.value]):
                    if key:
                        keys.setdefault(key, []).append(where)
    # Marked XAML files translate the same literal UI attributes at load time.
    lib_dir = os.path.join(root, 'lib')
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    from lowlife import xaml_i18n
    for top in SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, top)):
            dirnames[:] = [d for d in dirnames if not re.match(r'MyPanel\d+\.panel$', d)
                           and d not in ('__pycache__', 'build', 'dist')]
            for name in filenames:
                if not name.endswith('.xaml'):
                    continue
                path = os.path.join(dirpath, name)
                with io.open(path, encoding='utf-8-sig') as stream:
                    source = stream.read()
                if xaml_i18n.MARKER not in source:
                    continue
                for text in xaml_i18n.strings(source):
                    if CYRILLIC.search(text):
                        keys.setdefault(text, []).append(os.path.relpath(path, root))
    return keys


def module_level_tr(root=ROOT):
    """[(файл, строка)] — вызовы tr() в библиотеке (lib/), которые выполняются при импорте модуля:
    язык там застынет на момент загрузки. В данных — N_(…), tr(…) — при показе."""
    found = []
    for path in iter_sources(root):
        if not path.startswith(os.path.join(root, "lib")):
            continue
        with io.open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        if "tr(" not in text:
            continue
        tree = ast.parse(text)
        inside = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.Lambda, ast.AsyncFunctionDef)):
                for sub in ast.walk(node):
                    inside.add(id(sub))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) == "tr" and id(node) not in inside:
                found.append((os.path.relpath(path, root), node.lineno))
    return found


def load_catalog():
    try:
        with io.open(CATALOG, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, OSError, ValueError):
        return {}


def save_catalog(data):
    os.makedirs(os.path.dirname(CATALOG), exist_ok=True)
    with io.open(CATALOG, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def placeholders(text):
    return sorted(PLACEHOLDER.findall(text))


def problems(keys=None, catalog=None):
    """[(русская строка, причина)] — нет перевода или подстановки не совпали."""
    keys = extract_keys() if keys is None else keys
    catalog = load_catalog() if catalog is None else catalog
    result = []
    for ru in sorted(keys):
        en = catalog.get(ru)
        if not en:
            result.append((ru, "нет перевода"))
        elif placeholders(ru) != placeholders(en):
            result.append((ru, "подстановки %s ≠ %s" % (placeholders(ru), placeholders(en))))
    return result


def main(argv):
    if not argv or argv[0] not in ("wrap", "wrapat", "mark", "todo", "extract", "check"):
        print(__doc__)
        return 1
    if argv[0] == "wrapat":
        cmd_wrapat(argv[1:])
        return 0
    if argv[0] == "todo":
        cmd_todo(argv[1:])
        return 0
    if argv[0] == "mark":
        cmd_mark(argv[1:])
        return 0
    if argv[0] == "wrap":
        cmd_wrap(argv[1:])
        return 0
    keys = extract_keys()
    catalog = load_catalog()
    if argv[0] == "extract":
        missing = [k for k in keys if k not in catalog]
        unused = [k for k in catalog if k not in keys]
        print("строк: %d, новых: %d, лишних в каталоге: %d" % (len(keys), len(missing), len(unused)))
        if "--write" in argv:
            for k in missing:
                catalog[k] = ""
            if "--prune" in argv:
                for k in unused:
                    del catalog[k]
            save_catalog(catalog)
        return 0
    bad = problems(keys, catalog)
    for ru, why in bad:
        print("%s: %s  [%s]" % (why, ru, ", ".join(sorted(set(keys[ru])))))
    print("проблем: %d из %d" % (len(bad), len(keys)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
