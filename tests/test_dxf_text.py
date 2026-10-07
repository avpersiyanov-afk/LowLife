# -*- coding: utf-8 -*-
import math

import pytest

from lowlife import dxf_text


def _dxf(header=(), tables=(), blocks=(), entities=()):
    """Собирает текстовый DXF из списков (код, значение)."""
    out = []

    def add(pairs):
        for code, value in pairs:
            out.append(str(code))
            out.append(value)

    add([(0, "SECTION"), (2, "HEADER")])
    add(header)
    add([(0, "ENDSEC"), (0, "SECTION"), (2, "TABLES")])
    add(tables)
    add([(0, "ENDSEC"), (0, "SECTION"), (2, "BLOCKS")])
    add(blocks)
    add([(0, "ENDSEC"), (0, "SECTION"), (2, "ENTITIES")])
    add(entities)
    add([(0, "ENDSEC"), (0, "EOF")])
    return "\r\n".join(out) + "\r\n"


def _text(value, x, y, h=2.5, rot=0.0, layer="0", extra=()):
    return [(0, "TEXT"), (8, layer), (10, str(x)), (20, str(y)), (30, "0"),
            (40, str(h)), (1, value), (50, str(rot))] + list(extra)


def test_simple_text_and_units():
    data = _dxf(header=[(9, "$ACADVER"), (1, "AC1027"), (9, "$INSUNITS"), (70, "4")],
                entities=_text(u"Щит ЩР-1", 100, 200, 3.5, 90))
    d = dxf_text.parse_dxf_bytes(data.encode("utf-8"))
    assert d.units_to_feet == pytest.approx(1 / 304.8)
    assert len(d.texts) == 1
    t = d.texts[0]
    assert t.text == u"Щит ЩР-1"
    assert (t.x, t.y, t.height) == pytest.approx((100, 200, 3.5))
    assert t.angle == pytest.approx(math.pi / 2)
    assert (t.halign, t.valign) == ("left", "bottom")


def test_old_version_uses_codepage():
    data = _dxf(header=[(9, "$ACADVER"), (1, "AC1018"), (9, "$DWGCODEPAGE"), (3, "ANSI_1251")],
                entities=_text(u"Кабель", 0, 0))
    d = dxf_text.parse_dxf_bytes(data.encode("cp1251"))
    assert d.texts[0].text == u"Кабель"


def test_specials():
    assert dxf_text.text_plain(u"%%c20 %%d %%p5 %%u100%%%") == u"Ø20 ° ±5 100%"
    assert dxf_text.text_plain(u"\\U+0416\\U+041A") == u"ЖК"


def test_mtext_formatting():
    raw = u"{\\fArial|b1;\\H2.5;Первая}\\PВторая \\S1^2; {\\C1;красн}\\~конец\\{x\\}"
    assert dxf_text.mtext_plain(raw) == u"Первая\nВторая 1/2 красн конец{x}"
    assert dxf_text.mtext_height(raw, 5.0) == pytest.approx(2.5)
    assert dxf_text.mtext_height(u"\\H0.5x;abc", 4.0) == pytest.approx(2.0)


def test_mtext_entity_attachment_and_direction():
    ents = [(0, "MTEXT"), (8, u"Подписи"), (10, "10"), (20, "20"), (40, "2"), (71, "5"),
            (11, "0"), (21, "1"), (3, u"Длинный "), (1, u"текст\\Pстрока 2")]
    d = dxf_text.parse_dxf_text(_dxf(entities=ents))
    t = d.texts[0]
    assert t.text == u"Длинный текст\nстрока 2"
    assert (t.halign, t.valign) == ("center", "middle")
    assert t.angle == pytest.approx(math.pi / 2)
    assert t.layer == u"Подписи"


def test_text_alignment_uses_second_point():
    t = _text(u"Ц", 0, 0, extra=[(72, "1"), (73, "3"), (11, "50"), (21, "60")])
    d = dxf_text.parse_dxf_text(_dxf(entities=t))
    assert (d.texts[0].x, d.texts[0].y) == pytest.approx((50, 60))
    assert (d.texts[0].halign, d.texts[0].valign) == ("center", "top")


def test_insert_transforms_text_and_layer_zero():
    blocks = [(0, "BLOCK"), (2, u"МАРКА"), (10, "1"), (20, "0")] + \
        _text(u"А", 2, 0, h=1.0) + [(0, "ENDBLK")]
    ents = [(0, "INSERT"), (8, u"Оборудование"), (2, u"МАРКА"), (10, "100"), (20, "100"),
            (41, "2"), (42, "2"), (50, "90")]
    d = dxf_text.parse_dxf_text(_dxf(blocks=blocks, entities=ents))
    t = d.texts[0]
    # (2-1)*2 = 2 по X блока → поворот 90° → (0, 2) + (100, 100)
    assert (t.x, t.y) == pytest.approx((100, 102))
    assert t.height == pytest.approx(2.0)
    assert t.angle == pytest.approx(math.pi / 2)
    assert t.width_factor == pytest.approx(1.0)
    assert t.layer == u"Оборудование"


def test_non_uniform_insert_changes_width_factor():
    blocks = [(0, "BLOCK"), (2, "B"), (10, "0"), (20, "0")] + _text(u"x", 0, 0, h=1.0) + [(0, "ENDBLK")]
    ents = [(0, "INSERT"), (2, "B"), (10, "0"), (20, "0"), (41, "3"), (42, "1.5")]
    t = dxf_text.parse_dxf_text(_dxf(blocks=blocks, entities=ents)).texts[0]
    assert t.height == pytest.approx(1.5)
    assert t.width_factor == pytest.approx(2.0)


def test_hidden_layers_paper_space_and_invisible_attrib():
    tables = [(0, "LAYER"), (2, u"Выкл"), (70, "0"), (62, "-7"),
              (0, "LAYER"), (2, u"Замор"), (70, "1"), (62, "7")]
    ents = (_text(u"off", 0, 0, layer=u"Выкл") + _text(u"frozen", 0, 0, layer=u"Замор") +
            _text(u"sheet", 0, 0, extra=[(67, "1")]) +
            [(0, "ATTRIB"), (8, "0"), (10, "0"), (20, "0"), (40, "1"), (1, "hidden"), (70, "1")] +
            [(0, "ATTRIB"), (8, "0"), (10, "0"), (20, "0"), (40, "1"), (1, "shown"), (70, "0")])
    d = dxf_text.parse_dxf_text(_dxf(tables=tables, entities=ents))
    assert [t.text for t in d.texts] == [u"shown"]
    assert d.skipped_hidden == 2


def test_extents_and_fit():
    ents = [(0, "LINE"), (10, "0"), (20, "0"), (11, "1000"), (21, "0"),
            (0, "CIRCLE"), (10, "500"), (20, "500"), (40, "100")]
    d = dxf_text.parse_dxf_text(_dxf(header=[(9, "$INSUNITS"), (70, "4")], entities=ents))
    assert d.extents == pytest.approx((0, 0, 1000, 600))
    s = 1 / 304.8
    revit = (10 + 0 * s, 20 + 0 * s, 10 + 1000 * s, 20 + 600 * s)
    scale, ox, oy, how = dxf_text.fit_mapping(d.extents, revit, d.units_to_feet)
    assert how == "units"
    assert scale == pytest.approx(s)
    assert (ox, oy) == pytest.approx((10, 20))


def test_fit_without_units_and_zero_offset():
    scale, ox, oy, how = dxf_text.fit_mapping((0, 0, 100, 50), (0, 0, 10, 5), None)
    assert (scale, ox, oy, how) == (pytest.approx(0.1), 0.0, 0.0, "extents")


def test_fit_inconsistent_falls_back_to_units():
    assert dxf_text.fit_mapping((0, 0, 100, 50), (0, 0, 10, 50), 2.0) == (2.0, 0.0, 0.0, "units_only")
    assert dxf_text.fit_mapping((0, 0, 100, 50), (0, 0, 10, 50), None) is None


def test_binary_dxf_rejected():
    with pytest.raises(ValueError):
        dxf_text.parse_dxf_bytes(b"AutoCAD Binary DXF\r\n\x1a\x00")


def test_multileader_text():
    ents = [(0, "MULTILEADER"), (8, u"Выноски"), (300, "CONTEXT_DATA{"), (40, "1"),
            (10, "5"), (20, "5"), (41, "3"), (290, "1"),
            (304, u"Кабель\\PВВГнг"), (11, "0"), (21, "0"), (12, "40"), (22, "50"),
            (13, "1"), (23, "0"), (171, "2"),
            (302, "LEADER{"), (10, "0"), (20, "0"), (12, "999"), (303, "}"),
            (301, "}"), (170, "1")]
    d = dxf_text.parse_dxf_text(_dxf(entities=ents))
    t = d.texts[0]
    assert t.text == u"Кабель\nВВГнг"
    assert (t.x, t.y, t.height) == pytest.approx((40, 50, 3))
    assert (t.halign, t.valign, t.kind) == ("center", "top", "MULTILEADER")
    assert t.layer == u"Выноски"
    assert d.counts() == {"MULTILEADER": 1}


def test_constant_attdef_and_table_block():
    blocks = ([(0, "BLOCK"), (2, u"МАРКА"), (10, "0"), (20, "0"),
               (0, "ATTDEF"), (8, "0"), (10, "1"), (20, "1"), (40, "1"), (1, u"пост"), (2, "TAG"), (70, "2"),
               (0, "ATTDEF"), (8, "0"), (10, "1"), (20, "1"), (40, "1"), (1, u"перем"), (2, "TAG2"), (70, "0"),
               (0, "ENDBLK")] +
              [(0, "BLOCK"), (2, "*T1"), (10, "0"), (20, "0")] + _text(u"ячейка", 2, 3) + [(0, "ENDBLK")])
    ents = [(0, "INSERT"), (2, u"МАРКА"), (10, "10"), (20, "10"),
            (0, "ACAD_TABLE"), (2, "*T1"), (10, "100"), (20, "200"), (41, "0.06"), (70, "0"), (71, "5")]
    d = dxf_text.parse_dxf_text(_dxf(blocks=blocks, entities=ents))
    by = dict((t.text, (t.x, t.y)) for t in d.texts)
    assert set(by) == {u"пост", u"ячейка"}
    assert by[u"пост"] == pytest.approx((11, 11))
    assert by[u"ячейка"] == pytest.approx((102, 203))


def test_unsupported_types_are_counted():
    ents = [(0, "ACAD_PROXY_ENTITY"), (8, "0"), (0, "HATCH"), (8, "0")]
    d = dxf_text.parse_dxf_text(_dxf(entities=ents))
    assert d.unsupported == {"ACAD_PROXY_ENTITY": 1}
