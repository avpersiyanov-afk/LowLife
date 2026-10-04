# -*- coding: utf-8 -*-
"""Название LowLife шрифтом в WPF — геометрия из букв шрифта, а не картинка.

Каждая буква превращается в контур через FormattedText.BuildGeometry,
отражается/поворачивается вокруг центра своего контура (так «Γ» остаётся
на месте «L», а не съезжает по высоте строки) и ставится вплотную к
предыдущей с небольшим зазором. Повёрнутая на произвольный угол буква
центрируется по высоте заглавных. Обычные буквы и акцентные (оранжевая «Γ»,
как в логотипе) собираются в два контура одного DrawingImage — так они
масштабируются вместе (Image.Stretch = Uniform) и не разъезжаются.
Только для IronPython внутри Revit (нужны сборки WPF).
"""

from System.Globalization import CultureInfo
from System.Windows import FlowDirection, FontStretches, FontStyles, FontWeights, Point
from System.Windows.Media import (Brushes, BrushConverter, DrawingGroup, DrawingImage, FillRule,
                                  FontFamily, FormattedText, GeometryDrawing, GeometryGroup,
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


def _transform_for(op, cx, cy):
    transform = TransformGroup()
    if op in ("mirror_x", "mirror_x_rot180"):
        transform.Children.Add(ScaleTransform(-1.0, 1.0, cx, cy))
    if op == "mirror_x_rot180":
        transform.Children.Add(RotateTransform(180.0, cx, cy))
    elif op not in (None, "mirror_x"):
        transform.Children.Add(RotateTransform(float(op), cx, cy))
    return transform


def build_geometries(letters=None, font_family=None, gap_em=0.05):
    """(основной контур, акцентный контур) названия — две GeometryGroup
    в общих координатах."""
    typeface = Typeface(FontFamily(font_family or about.WORDMARK_FONT),
                        FontStyles.Normal, FontWeights.Bold, FontStretches.Normal)
    cap = _glyph(u"L", typeface).Bounds
    cap_cy = cap.Top + cap.Height / 2.0

    main, accent = GeometryGroup(), GeometryGroup()
    main.FillRule = accent.FillRule = FillRule.Nonzero
    x = 0.0
    for ch, op, is_accent in (letters or about.WORDMARK_LETTERS):
        letter = GeometryGroup()
        letter.Children.Add(_glyph(ch, typeface))
        b = letter.Bounds
        transform = _transform_for(op, b.Left + b.Width / 2.0, b.Top + b.Height / 2.0)
        letter.Transform = transform
        tb = letter.Bounds  # уже с учётом отражения/поворота
        rotated = op not in (None, "mirror_x", "mirror_x_rot180")
        dy = cap_cy - (tb.Top + tb.Height / 2.0) if rotated else 0.0
        transform.Children.Add(TranslateTransform(x - tb.Left, dy))
        (accent if is_accent else main).Children.Add(letter)
        x += tb.Width + gap_em * EM
    return main, accent


def build_image(letters=None, font_family=None):
    """DrawingImage названия для Image.Source: белые буквы + оранжевая «Γ»."""
    main, accent = build_geometries(letters, font_family)
    conv = BrushConverter()
    drawing = DrawingGroup()
    drawing.Children.Add(GeometryDrawing(conv.ConvertFromString(about.MAIN_COLOR), None, main))
    drawing.Children.Add(GeometryDrawing(conv.ConvertFromString(about.ACCENT_COLOR), None, accent))
    return DrawingImage(drawing)
