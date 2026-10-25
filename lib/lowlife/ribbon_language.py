# -*- coding: utf-8 -*-
"""Перевод ленты LowLife на выбранный язык (lowlife.i18n) — без перезагрузки pyRevit.

pyRevit строит ленту по-русски (``title``/``tooltip`` из bundle.yaml или ``__title__``/docstring
из script.py). Английские подписи лежат рядом, в том же bundle.yaml: ``title_en``/``tooltip_en``
у кнопок и панелей, ``members_en`` у списков (.combobox) — pyRevit их не читает.
``apply_language("en")`` ставит их на ленту, ``apply_language("ru")`` возвращает русские.

Русские подписи кнопок берутся с самой ленты при первом переводе и хранятся в AppDomain
(у движка каждой кнопки своя копия модуля, а вернуть их должен любой, кто переключает язык);
после перезагрузки pyRevit лента снова русская, и ``restore_on_idle`` из startup.py
запоминает их заново.

Панели распознаются по русскому или английскому имени: новый pyRevit-wrapper может
получить уже переведённое имя. Ключ хранилища всегда русский, а исходный заголовок панели
берётся из bundle.yaml, чтобы вернуть русский даже после ошибочного запоминания английского.
pyRevit-овский ``get_adwindows_object()`` панели сверяет заголовок с именем — вместо него
``adwindows_panel(panel)``.
"""
import os

from lowlife import i18n, ribbon_catalog

TAB_NAME = u"LowLife"
_STORE_KEY = u"LowLife.ribbon_language.originals"
_BUNDLE_NAME_MARK = u"Bundle Name:"  # pyRevit дописывает это к подсказке кнопки


# ---------------------------------------------------------------- без Revit API

def _ribbon_text(text):
    """«Узлы\\nтрассы» из bundle.yaml → перенос строки, как у pyRevit."""
    return (text or u"").replace(u"\\n", u"\n").strip()


def english_tooltip(original, en):
    """Подсказка кнопки по-английски: перевод + служебный хвост pyRevit («Bundle Name: …»),
    если он был в русской подсказке."""
    en = (en or u"").strip()
    if not en:
        return original
    original = original or u""
    mark = original.find(_BUNDLE_NAME_MARK)
    if mark < 0:
        return en
    return en + u"\n\n" + original[mark:]


def panel_index(root=None):
    """{имя панели на ленте (русский title): (папка панели, {имя папки кнопки: папка кнопки})}.

    Кнопки — со всех уровней (стеки, выпадающие списки): pyRevit называет элемент ленты именем
    папки без расширения. Свои панели пользователя («Мои панели») тоже здесь: в них копии кнопок
    со своими bundle.yaml."""
    tab = os.path.join(root or ribbon_catalog.extension_root(), ribbon_catalog.TAB_FOLDER)
    result = {}
    try:
        names = sorted(os.listdir(tab))
    except (IOError, OSError):
        return result
    for name in names:
        folder = os.path.join(tab, name)
        if os.path.splitext(name)[1].lower() != u".panel" or not os.path.isdir(folder):
            continue
        buttons = {}
        _collect_buttons(folder, buttons)
        result[ribbon_catalog.item_title(folder)] = (folder, buttons)
    return result


def _collect_buttons(folder, out):
    exts = ribbon_catalog.BUTTON_EXTS + ribbon_catalog.STACK_EXTS
    try:
        names = os.listdir(folder)
    except (IOError, OSError):
        return
    for name in names:
        full = os.path.join(folder, name)
        stem, ext = os.path.splitext(name)
        if ext.lower() not in exts or not os.path.isdir(full):
            continue
        if ext.lower() not in ribbon_catalog.STACK_EXTS:
            out.setdefault(stem, full)
        _collect_buttons(full, out)


# ---------------------------------------------------------------- Revit

def _originals():
    """Русские подписи ленты: .NET-словарь в AppDomain (общий для движков всех кнопок)."""
    from System import AppDomain, String
    from System.Collections.Generic import Dictionary
    domain = AppDomain.CurrentDomain
    store = domain.GetData(_STORE_KEY)
    if store is None:
        store = Dictionary[String, String]()
        domain.SetData(_STORE_KEY, store)
    return store


def _apply_text(store, key, obj, attr, english, lang, capture, original=None):
    try:
        current = getattr(obj, attr)
    except Exception:
        return
    current = current or u""
    if original is not None:
        store[key] = original
    elif capture or not store.ContainsKey(key):
        store[key] = current
    original = store[key]
    target = english(original) if lang == i18n.EN else original
    if target and target != current:
        try:
            setattr(obj, attr, target)
        except Exception:
            pass


def adwindows_panel(panel):
    """Autodesk.Windows-панель pyRevit-панели — и когда её заголовок уже переведён."""
    try:
        adwin = panel.get_adwindows_object()
    except Exception:
        adwin = None
    if adwin is not None:
        return adwin
    try:
        title = panel.get_rvtapi_object().Title
        for candidate in panel.parent_tab.Panels:
            if candidate.Source and candidate.Source.Title == title:
                return candidate
    except Exception:
        pass
    return None


def _walk(container):
    for child in container:
        yield child
        try:
            for sub in _walk(child):
                yield sub
        except TypeError:
            pass


def _translate_combobox(store, key, item, folder, lang, capture):
    members = ribbon_catalog.read_members_en(folder)
    if not members:
        return
    try:
        rvt = item.get_rvtapi_object()
        rvt_members = list(rvt.GetItems())
    except Exception:
        return
    for member in rvt_members:
        en = members.get(member.Name)
        if not en:
            continue
        mkey = key + u"|member|" + member.Name
        _apply_text(store, mkey + u"|title", member, "ItemText",
                    lambda _o, t=en.get(u"text"): _ribbon_text(t), lang, capture)
        _apply_text(store, mkey + u"|tooltip", member, "ToolTip",
                    lambda o, t=en.get(u"tooltip"): english_tooltip(o, t), lang, capture)


def apply_language(lang=None, capture=False):
    """Подписи и подсказки ленты LowLife на языке lang (по умолчанию — выбранном).

    capture=True — лента только что построена pyRevit (она русская): запомнить подписи заново,
    даже если они уже были запомнены (после обновления LowLife русский текст мог измениться)."""
    from pyrevit.coreutils.ribbon import get_current_ui

    lang = lang or i18n.current()
    store = _originals()
    index = panel_index()
    # A newly built pyRevit wrapper can use the translated panel Name. Resolve
    # either caption, but always keep the original caption in the storage key.
    aliases = dict(index)
    for info in index.values():
        english = _ribbon_text(ribbon_catalog.raw_bundle_text(info[0])[u"title_en"])
        if english:
            aliases.setdefault(english, info)
    for tab in get_current_ui().get_pyrevit_tabs():
        for panel in tab:
            info = aliases.get(panel.name)
            if info is None:
                continue
            panel_folder, buttons = info
            panel_ru = _ribbon_text(ribbon_catalog.item_title(panel_folder))
            pkey = u"panel|" + panel_ru
            panel_en = ribbon_catalog.raw_bundle_text(panel_folder)[u"title_en"]
            _apply_text(store, pkey, panel.get_rvtapi_object(), "Title",
                        lambda _o, t=panel_en: _ribbon_text(t), lang, capture,
                        original=panel_ru)
            for item in _walk(panel):
                folder = buttons.get(getattr(item, "name", None))
                if folder is None:
                    continue
                rvt = item.get_rvtapi_object()
                key = pkey + u"|" + item.name
                text = ribbon_catalog.raw_bundle_text(folder)
                _apply_text(store, key + u"|title", rvt, "ItemText",
                            lambda _o, t=text[u"title_en"]: _ribbon_text(t), lang, capture)
                _apply_text(store, key + u"|tooltip", rvt, "ToolTip",
                            lambda o, t=text[u"tooltip_en"]: english_tooltip(o, _ribbon_text(t)),
                            lang, capture)
                if folder.lower().endswith(u".combobox"):
                    _translate_combobox(store, key, item, folder, lang, capture)
    return lang


def switch(lang):
    """Из окна кнопки «Язык / Language»: запомнить язык и перевести ленту. Возвращает применённый язык."""
    saved = i18n.save(lang)
    if saved is None:
        return None
    return apply_language(saved)


def restore_on_idle(app):
    """Из startup.py: при первом простое Revit (лента достроена) запомнить её русские подписи,
    перевести на выбранный язык. app — UIApplication или
    UIControlledApplication."""
    state = {"done": False}

    def on_idle(sender, args):
        if state["done"]:
            return
        state["done"] = True
        try:
            app.Idling -= on_idle
        except Exception:
            pass
        try:
            apply_language(capture=True)
        except Exception:
            pass

    app.Idling += on_idle
