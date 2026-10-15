# -*- coding: utf-8 -*-
import datetime

from lowlife import usage_core

ENTRIES = [
    {u"panel": u"SCS", u"panel_title": u"SCS", u"button": u"PlaceRouteNodes",
     u"path": [u"PlaceRouteNodes"], u"title": u"Узлы трассы", u"tooltip": u""},
    {u"panel": u"CircuitsSPS", u"panel_title": u"Цепи СПС", u"button": u"BuildLoopCircuitsSPS",
     u"path": [u"BuildLoopCircuitsSPS"], u"title": u"Цепи шлейфов СПС", u"tooltip": u""},
    {u"panel": u"Tools", u"panel_title": u"Инструменты", u"button": u"Child",
     u"path": [u"Menu", u"Child"], u"title": u"Вложенная", u"tooltip": u""},
]
CTX = {u"user": u"ivanov", u"windows_user": u"iivanov", u"model": u"A.rvt",
       u"version": u"main @ 1234567", u"revit": u"2024"}


def test_parse_item_id():
    assert usage_core.parse_item_id(u"CustomCtrl_%CustomCtrl_%LowLife%Цепи СПС%BuildLoopCircuitsSPS") == \
        (u"Цепи СПС", [u"BuildLoopCircuitsSPS"])
    assert usage_core.parse_item_id(u"CustomCtrl_%CustomCtrl_%LowLife%Инструменты%Menu%Child") == \
        (u"Инструменты", [u"Menu", u"Child"])


def test_parse_item_id_not_lowlife():
    assert usage_core.parse_item_id(u"CustomCtrl_%CustomCtrl_%pyRevit%Tools%Reload") is None
    assert usage_core.parse_item_id(u"ID_OBJECTS_WALL") is None
    assert usage_core.parse_item_id(None) is None
    assert usage_core.parse_item_id(u"CustomCtrl_%CustomCtrl_%LowLife%SCS") is None


def test_find_entry():
    assert usage_core.find_entry(ENTRIES, u"SCS", [u"PlaceRouteNodes"])[u"title"] == u"Узлы трассы"
    assert usage_core.find_entry(ENTRIES, u"Инструменты", [u"Menu", u"Child"])[u"title"] == u"Вложенная"
    # путь в Id может отличаться от папок — кнопка находится по последней папке
    assert usage_core.find_entry(ENTRIES, u"Инструменты", [u"Child"])[u"title"] == u"Вложенная"
    assert usage_core.find_entry(ENTRIES, u"LowLife", [u"ThemeSelector"]) is None
    assert usage_core.find_entry(ENTRIES, u"SCS", []) is None


def test_new_event():
    now = datetime.datetime(2026, 10, 15, 9, 5, 7)
    ev = usage_core.new_event(ENTRIES[2], usage_core.SOURCE_RIBBON, CTX, now)
    assert ev[u"time"] == u"2026-10-15 09:05:07"
    assert ev[u"button_id"] == u"Tools/Menu/Child"
    assert ev[u"panel"] == u"Инструменты" and ev[u"button"] == u"Вложенная"
    assert ev[u"user"] == u"ivanov" and ev[u"model"] == u"A.rvt"
    assert len(ev[u"id"]) == 12


def test_should_flush():
    now = datetime.datetime(2026, 10, 15, 12, 0, 0)
    fresh = {u"time": u"2026-10-15 11:50:00"}
    old = {u"time": u"2026-10-15 11:00:00"}
    assert not usage_core.should_flush([], now)
    assert not usage_core.should_flush([fresh], now)
    assert usage_core.should_flush([old, fresh], now)
    assert usage_core.should_flush([fresh] * usage_core.FLUSH_COUNT, now)
    assert usage_core.should_flush([{u"time": u"мусор"}], now)


def test_batch_id_stable():
    events = [{u"id": u"a"}, {u"id": u"b"}, {u"id": u"c"}]
    assert usage_core.batch_id(events) == usage_core.batch_id(list(events)) == u"a-c-3"
    assert usage_core.batch_id([]) == u""


def test_trim_queue():
    assert usage_core.trim_queue(list(range(10)), 3) == [7, 8, 9]
    assert usage_core.trim_queue([1, 2], 3) == [1, 2]


def test_is_duplicate():
    mark = (u"SCS/PlaceRouteNodes", 100.0)
    assert usage_core.is_duplicate(mark, u"SCS/PlaceRouteNodes", 105.0)
    assert not usage_core.is_duplicate(mark, u"SCS/PlaceRouteNodes", 120.0)
    assert not usage_core.is_duplicate(mark, u"SCS/Other", 101.0)
    assert not usage_core.is_duplicate(None, u"SCS/PlaceRouteNodes", 101.0)


def test_panel_titled_like_tab():
    # первая панель вкладки называется так же, как вкладка
    assert usage_core.parse_item_id(u"CustomCtrl_%CustomCtrl_%LowLife%LowLife%About") == (u"LowLife", [u"About"])
