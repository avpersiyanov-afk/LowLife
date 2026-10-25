# -*- coding: utf-8 -*-

__title__ = u"Зум к\nэлементу"
__doc__ = (
    u"Приближает вид к элементу. Если элемент уже выбран в модели — просто "
    u"зумирует к нему (к нескольким выбранным — к их общему габариту), в том "
    u"числе к элементам связей, выбранным через Tab. Если "
    u"ничего не выбрано — спрашивает ID элемента и ищет его в модели и во "
    u"всех загруженных связях. Если "
    u"элемента не видно на активном виде, подсказывает, на какой уровень "
    u"(план/разрез/3D) переключиться, чтобы он был заметен."
)
__author__ = "Pipers"

import clr
from lowlife.i18n import tr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import XYZ

from pyrevit import revit, forms

from lowlife import linked_elements, select_list

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

TITLE = tr(u"Зум к элементу")


def ask_element_by_id():
    raw = forms.ask_for_string(
        default="",
        prompt=tr(u"Введите ID элемента (модели или связи), к которому нужно приблизить вид:"),
        title=TITLE
    )

    if raw is None:
        # Пользователь закрыл окно — тихо выходим.
        forms.alert(tr(u"Операция отменена."), exitscript=True)

    raw = raw.strip()
    if not raw:
        forms.alert(tr(u"ID не введён."), exitscript=True)

    try:
        int_id = int(raw)
    except ValueError:
        forms.alert(tr(u"«{}» — это не число. ID элемента должен быть целым числом.").format(raw), exitscript=True)

    found = linked_elements.find_by_id(doc, int_id)
    if not found:
        forms.alert(
            tr(u"Элемент с ID {} не найден ни в текущей модели, ни в "
            u"загруженных связях. Возможно, он удалён или его связь "
            u"выгружена.").format(int_id),
            exitscript=True
        )
    if len(found) == 1:
        return found[0]

    # Один и тот же ID есть в нескольких моделях — спрашиваем, какой нужен.
    # Подписи уникальны даже для двух экземпляров одной связи.
    labels = []
    for it in found:
        label = it.label()
        n = 2
        while label in labels:
            label = u"{} #{}".format(it.label(), n)
            n += 1
        labels.append(label)
    by_label = dict(zip(labels, found))
    picked = select_list.SelectFromList.show(
        labels,
        title=tr(u"Элемент с ID {} есть в нескольких моделях").format(int_id),
        button_name=tr(u"Зум"),
        multiselect=False,
    )
    if not picked:
        forms.alert(tr(u"Операция отменена."), exitscript=True)
    return by_label[picked]


def zoom_center_on_points(points, pad_ft=6.0):
    """
    Ставит облако points (список XYZ) в центр активного вида.

    Отличие от route_preview.zoom_to_fit_points: тот прямоугольник для
    маршрута всегда широкий и вытянутый — близко к соотношению сторон
    экрана, поэтому ZoomAndCenterRectangle центрирует его точно. Для одного
    (или нескольких рядом) элемента прямоугольник почти квадратный,
    расхождение с экраном максимальное — и ZoomAndCenterRectangle
    центрирует с заметным смещением. Поэтому здесь прямоугольник заранее
    расширяется до соотношения сторон окна вида (GetWindowRectangle) —
    тогда центрирование точное.
    """
    pts = [p for p in points if p is not None]
    if not pts:
        return

    uiview = None
    for uv in uidoc.GetOpenUIViews():
        if uv.ViewId == view.Id:
            uiview = uv
            break
    if uiview is None:
        return

    min_x = min(p.X for p in pts)
    max_x = max(p.X for p in pts)
    min_y = min(p.Y for p in pts)
    max_y = max(p.Y for p in pts)
    z = sum(p.Z for p in pts) / len(pts)

    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0
    half_x = (max_x - min_x) / 2.0 + pad_ft
    half_y = (max_y - min_y) / 2.0 + pad_ft

    try:
        rect = uiview.GetWindowRectangle()
        win_w = abs(rect.Right - rect.Left)
        win_h = abs(rect.Bottom - rect.Top)
        if win_w > 0 and win_h > 0:
            aspect = float(win_w) / float(win_h)
            if half_x / half_y < aspect:
                half_x = half_y * aspect
            else:
                half_y = half_x / aspect
    except:
        pass

    try:
        uiview.ZoomAndCenterRectangle(
            XYZ(cx - half_x, cy - half_y, z),
            XYZ(cx + half_x, cy + half_y, z),
        )
    except:
        pass
    try:
        uidoc.RefreshActiveView()
    except:
        pass


def hint_where_to_look(items):
    item = items[0]
    level_name = linked_elements.level_name(item)
    elev_m = linked_elements.elevation_m(item)

    active_level = getattr(view, "GenLevel", None)
    active_level_name = active_level.Name if active_level is not None else None

    elev_line = tr(u"\nОтметка элемента ≈ {:.2f} м.").format(elev_m) if elev_m is not None else u""
    if item.is_linked:
        elev_line += tr(u"\nЭлемент из связи «{}».").format(item.link_name)

    if level_name and active_level_name and level_name == active_level_name:
        forms.alert(
            tr(u"Элемент относится к уровню активного вида («{}»), но на виде "
            u"не показан. Проверьте: видимость его категории (VG; для связи — "
            u"вкладка «Связанные файлы RVT»), фильтры вида, стадию (Phase) и "
            u"диапазон вида (View Range) — элемент может быть выше/ниже "
            u"секущей плоскости.{}").format(level_name, elev_line),
            title=TITLE
        )
    elif level_name:
        forms.alert(
            tr(u"Элемента не видно на активном виде. Похоже, он расположен на "
            u"уровне «{}». Переключитесь на план этого уровня (или на "
            u"подходящий разрез / 3D-вид) и запустите кнопку снова.{}").format(level_name, elev_line),
            title=TITLE
        )
    else:
        forms.alert(
            tr(u"Элемента не видно на активном виде, и определить его уровень "
            u"не удалось. Откройте 3D-вид или разрез, где элемент виден, и "
            u"запустите кнопку снова.{}").format(elev_line),
            title=TITLE
        )


# ------------------------------------------------------------
# ОСНОВНОЙ СЦЕНАРИЙ
# ------------------------------------------------------------

items = linked_elements.selected_items(uidoc)

if not items:
    items = [ask_element_by_id()]
    # Выделяем найденный по ID элемент, чтобы его было видно после зума.
    linked_elements.select_items(uidoc, items)

# Точки для зума — только по элементам, которые видны на активном виде.
visibility = linked_elements.Visibility(doc, view, items)
points = []
any_visible = False
for item in items:
    if not visibility.is_visible(item):
        continue
    any_visible = True
    pt = linked_elements.target_point(item, view)
    if pt is not None:
        points.append(pt)

if not any_visible:
    # Ни один из элементов не виден на активном виде — подсказываем куда смотреть.
    hint_where_to_look(items)
elif not points:
    forms.alert(
        tr(u"Элемент(ы) на виде есть, но определить его положение для зума не "
        u"удалось."),
        title=TITLE
    )
else:
    zoom_center_on_points(points)
