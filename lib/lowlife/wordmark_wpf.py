# -*- coding: utf-8 -*-
"""Название LowLife шрифтом в WPF — геометрия из букв шрифта, а не картинка.

Каждая буква превращается в контур через FormattedText.BuildGeometry,
отражается/поворачивается вокруг центра своего контура (так «Γ» остаётся
на месте «L», а не съезжает по высоте строки) и ставится вплотную к
предыдущей с небольшим зазором. Повёрнутая буква центрируется по высоте
заглавных. Результат — Geometry для Path (Fill = цвет, Stretch = Uniform).
Только для IronPython внутри Revit (нужны сборки WPF).
"""

from System.Globalization import CultureInfo
from System.Windows import FlowDirection, FontStretches, FontStyles, FontWeights, Point
from System.Windows.Media import (Brushes, FillRule, FontFamily, FormattedText, GeometryGroup,
                                  RotateTransform, ScaleTransform, TransformGroup,
                                  TranslateTransform, Typeface)

from lowlife import about

EM = 100.0


def _glyph(ch, typeface):
    args = [ch, CultureInfo.InvariantCulture, FlowDirection.LeftToRight, typeface, EM, Brushes.White]
    try:
        ft = FormattedText(*(args + [1.0]))  # с pixelsPerDip (.NET 4.6.2+)
    except TypeError:
        ft = FormattedText(*args)
    return ft.BuildGeometry(Point(0, 0))


def build_geometry(letters=None, font_family=None, gap_em=0.05):
    typeface = Typeface(FontFamily(font_family or about.WORDMARK_FONT),
                        FontStyles.Normal, FontWeights.Bold, FontStretches.Normal)
    cap = _glyph(u"L", typeface).Bounds
    cap_cy = cap.Top + cap.Height / 2.0

    word = GeometryGroup()
    word.FillRule = FillRule.Nonzero
    x = 0.0
    for ch, op in (letters or about.WORDMARK_LETTERS):
        letter = GeometryGroup()
        letter.Children.Add(_glyph(ch, typeface))
        b = letter.Bounds
        cx, cy = b.Left + b.Width / 2.0, b.Top + b.Height / 2.0
        transform = TransformGroup()
        if op == "mirror_x":
            transform.Children.Add(ScaleTransform(-1.0, 1.0, cx, cy))
        elif op == "mirror_y":
            transform.Children.Add(ScaleTransform(1.0, -1.0, cx, cy))
        elif op:
            transform.Children.Add(RotateTransform(float(op), cx, cy))
        letter.Transform = transform
        tb = letter.Bounds  # уже с учётом отражения/поворота
        dy = cap_cy - (tb.Top + tb.Height / 2.0) if op not in (None, "mirror_x", "mirror_y") else 0.0
        transform.Children.Add(TranslateTransform(x - tb.Left, dy))
        word.Children.Add(letter)
        x += tb.Width + gap_em * EM
    return word
