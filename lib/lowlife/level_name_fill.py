# -*- coding: utf-8 -*-
"""
Логика кнопки «Обновить имя уровня» (LOI.panel/UpdateLevelName.pushbutton):
записывает имя уровня в текстовый параметр (настройка target_param_name,
см. level_name_settings.py) у ВЫБРАННЫХ элементов.

Уровень элемента:
  1. Element.LevelId (lowlife.geometry.get_element_level) — тот уровень,
     что указан в свойствах экземпляра;
  2. если его нет (типично — семейство, размещённое на грани связи или по
     рабочей плоскости без уровня), — по высоте: ближайший уровень документа
     НЕ ВЫШЕ низа элемента (pick_level_by_elevation). Высота — Z точки
     вставки, иначе низ кривой/габарита.

Значение в параметре перезаписывается всегда («обновить»), даже если там
уже что-то записано.

Модуль импортирует Revit API лениво (внутри функций), поэтому чистая
pick_level_by_elevation тестируется вне Revit (tests/test_level_name_fill.py).
"""

# Допуск по высоте, футы (~3 мм): элемент, стоящий ровно на отметке уровня,
# но из-за округления чуть ниже неё, относится к этому уровню, а не к нижнему.
ELEVATION_TOL_FT = 0.01


def pick_level_by_elevation(z, levels_with_elevation, tol=ELEVATION_TOL_FT):
    """
    levels_with_elevation — [(отметка, уровень), ...] в той же системе
    координат, что z (у Revit — Level.ProjectElevation и Z точки в
    координатах модели). Возвращает уровень с наибольшей отметкой <= z + tol;
    если элемент ниже всех уровней — самый нижний. None — уровней нет.
    """
    if not levels_with_elevation:
        return None

    ordered = sorted(levels_with_elevation, key=lambda pair: pair[0])
    best = ordered[0][1]

    for elevation, level in ordered:
        if elevation <= z + tol:
            best = level
        else:
            break

    return best


class FillResult(object):
    def __init__(self):
        self.from_level_id = 0   # записано по уровню из свойств элемента
        self.by_elevation = 0    # записано по высоте (у элемента нет уровня)
        self.no_level = 0        # не удалось определить ни уровень, ни высоту
        self.failed = []         # элементы, где параметр не найден/нередактируемый

    @property
    def written(self):
        return self.from_level_id + self.by_elevation


def element_elevation(el):
    """Z элемента в координатах модели: точка вставки, иначе низ кривой,
    иначе низ габарита. None — ничего из этого не нашлось."""
    from Autodesk.Revit.DB import LocationPoint, LocationCurve

    try:
        loc = el.Location
        if isinstance(loc, LocationPoint):
            return loc.Point.Z
        if isinstance(loc, LocationCurve):
            curve = loc.Curve
            return min(curve.GetEndPoint(0).Z, curve.GetEndPoint(1).Z)
    except:
        pass

    try:
        bbox = el.get_BoundingBox(None)
        if bbox is not None:
            return bbox.Min.Z
    except:
        pass

    return None


def _levels_with_project_elevation(doc):
    """[(Level.ProjectElevation, Level)] — ProjectElevation отсчитывается от
    начала координат модели, как и Z точек элементов (Level.Elevation — от
    базовой точки/точки съёмки и с Z элемента напрямую не сравнима)."""
    from lowlife import geometry

    pairs = []
    for lv in geometry.get_document_levels(doc):
        try:
            pairs.append((lv.ProjectElevation, lv))
        except:
            pass
    return pairs


def resolve_level(doc, el, levels_with_elevation):
    """(Level, способ) — способ "level_id" или "elevation"; (None, None),
    если уровень не определился."""
    from lowlife import geometry

    level = geometry.get_element_level(doc, el)
    if level is not None:
        return level, "level_id"

    z = element_elevation(el)
    if z is None:
        return None, None

    level = pick_level_by_elevation(z, levels_with_elevation)
    if level is None:
        return None, None
    return level, "elevation"


def fill_level_names(doc, elements, target_param_name):
    """
    Пишет имя уровня в target_param_name каждого элемента из elements.
    Вызывать внутри revit.Transaction. Возвращает FillResult.
    """
    from lowlife import geometry, params as params_mod

    result = FillResult()
    levels = _levels_with_project_elevation(doc)

    for el in elements:
        level, how = resolve_level(doc, el, levels)
        if level is None:
            result.no_level += 1
            continue

        if not params_mod.set_param_any(el, target_param_name, geometry.level_name(level)):
            result.failed.append(el)
            continue

        if how == "level_id":
            result.from_level_id += 1
        else:
            result.by_elevation += 1

    return result
