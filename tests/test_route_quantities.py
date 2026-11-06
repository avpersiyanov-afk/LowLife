# -*- coding: utf-8 -*-
from lowlife import route_quantities as rq


def test_codes_sizes_decimals_and_tray_merging():
    data = rq.calculate([u"ПВХгст20-1,25; ПВХгст20-2.5; ПНДт32-3",
                         u"Лоток100-4 + Лоток200-5; СТн16-2; СТ16-1; ПЛЛЛ-7"])
    assert data["result"] == [(u"ПВХгст20", 3.75), (u"ПНДт32", 3),
                              (u"Лоток", 9), (u"СТн16", 2), (u"СТ16", 1), (u"ПЛЛЛ", 7)]
    assert data["parsed_items"] == 8


def test_empty_unknown_repeated_and_rounding():
    data = rq.calculate([None, u"  ", u"неизвестно", u"МР16-0.1 МР16-0.2", u"КК-1.234"])
    assert data["chains_with_route"] == 3
    assert data["unmatched"] == 1
    assert data["result"] == [(u"МР16", 0.3), (u"КК", 1.23)]
    assert rq.calculate([])["groups_count"] == 0


class Parameter(object):
    def __init__(self, value):
        self.value = value

    def AsString(self):
        return self.value


class Circuit(object):
    def __init__(self, **values):
        self.values = values

    def LookupParameter(self, name):
        return Parameter(self.values[name]) if name in self.values else None


def test_package_filter_and_independent_reports():
    systems = [Circuit(package=u" A ", reserve=u"ПВХл20-12", route=u"ПВХл20-10"),
               Circuit(package=u"A", route=u"Лоток100-3"),
               Circuit(package=u"B", reserve=u"ПВХл20-100"), Circuit(),
               Circuit(package=u" ")]
    settings = dict(package_param="package", route_method_reserve_param="reserve",
                    route_method_param="route")
    assert rq.packages(systems, "package") == [u"A", u"B"]
    processed, sections = rq.summarize(systems, settings, u" A ")
    assert processed == 2
    assert sections[0]["result"] == [(u"ПВХл20", 12)]
    assert sections[0]["chains_with_route"] == 1
    assert sections[1]["result"] == [(u"ПВХл20", 10), (u"Лоток", 3)]
