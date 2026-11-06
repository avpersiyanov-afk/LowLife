# -*- coding: utf-8 -*-
"""Dimensioned WPF cross-section, using the same coordinates as tray routing."""
from lowlife.i18n import tr
from lowlife import fire_boxes_core as core


def draw(canvas, settings, section=None):
    from System import Double
    from System.Windows import Size
    from System.Windows.Controls import Canvas, TextBlock
    from System.Windows.Media import Brushes, RotateTransform
    from System.Windows.Shapes import Rectangle, Line

    section = section or core.mounting_section(settings)
    canvas.Children.Clear()
    supported = section['mounting_supported']
    gap = section['ceiling_gap'] if supported else 0
    scale = min(390.0/section['width'], 350.0/(section['height']+gap+60))
    cx, cy = 300.0, 360.0
    w, h = section['width'], section['height']
    cw, ch = section['cavity_width'], section['cavity_height']
    X = lambda value: cx + value*scale
    Y = lambda value: cy - value*scale

    def line_px(x1,y1,x2,y2,brush=Brushes.DimGray,thickness=1):
        item = Line()
        item.X1, item.Y1, item.X2, item.Y2 = x1,y1,x2,y2
        item.Stroke, item.StrokeThickness = brush,thickness
        canvas.Children.Add(item)

    def line(x1,z1,x2,z2,brush=Brushes.DimGray,thickness=1):
        line_px(X(x1),Y(z1),X(x2),Y(z2),brush,thickness)

    def rectangle(x,z,width,height,stroke,fill,thickness=1):
        item = Rectangle()
        item.Width, item.Height = width*scale,height*scale
        item.Stroke, item.Fill, item.StrokeThickness = stroke,fill,thickness
        Canvas.SetLeft(item,X(x-width/2))
        Canvas.SetTop(item,Y(z+height/2))
        canvas.Children.Add(item)

    def text(x,y,value,center=False,vertical=False,brush=Brushes.Black,size=14):
        item = TextBlock()
        item.Text, item.FontSize, item.Foreground = value,size,brush
        item.Background = Brushes.White
        item.Measure(Size(Double.PositiveInfinity,Double.PositiveInfinity))
        if vertical:
            item.LayoutTransform = RotateTransform(-90)
            x -= item.DesiredSize.Height
            y -= item.DesiredSize.Width/2
        elif center:
            x -= item.DesiredSize.Width/2
        Canvas.SetLeft(item,x)
        Canvas.SetTop(item,y)
        canvas.Children.Add(item)

    def horizontal(x1,x2,y,label,extension_y=None):
        if extension_y is not None:
            for x in (x1,x2):
                line_px(x,extension_y,x,y+5,Brushes.LightGray)
        line_px(x1,y,x2,y)
        for x in (x1,x2):
            line_px(x-4,y+4,x+4,y-4)
        text((x1+x2)/2,y+4,label,center=True,size=13)

    def vertical(x,y1,y2,label,extension_x=None):
        if extension_x is not None:
            for y in (y1,y2):
                line_px(extension_x,y,x+4,y,Brushes.LightGray)
        line_px(x,y1,x,y2)
        for y in (y1,y2):
            line_px(x-4,y+4,x+4,y-4)
        text(x-4,(y1+y2)/2,label,vertical=True,size=13)

    fmt = lambda value: u'{:g}'.format(float(value))
    text(25,15,tr(u'Поперечный разрез · размеры в мм',u'Cross-section · dimensions in mm'),size=17)
    rectangle(0,0,w,h,Brushes.DarkOrange,Brushes.Bisque,2)
    rectangle(0,0,cw,ch,Brushes.Gray,Brushes.WhiteSmoke)

    if settings['product'] == 'FIREBOX':
        rectangle(0,0,cw,ch,Brushes.SteelBlue,Brushes.LightBlue)
        text(cx,cy-10,tr(u'Пространство для кабелей',u'Cable space'),center=True)
    else:
        if supported:
            slab_y = Y(h/2+gap)
            # Slab fragment and anchor embedment are symbols; no slab thickness is inferred.
            line_px(X(-w/2)-25,slab_y,X(w/2)+25,slab_y,Brushes.DimGray,2)
            line_px(X(-w/2)-25,slab_y-20,X(w/2)+25,slab_y-20,Brushes.DimGray)
            for x in range(int(X(-w/2)-25),int(X(w/2)+25),12):
                line_px(x,slab_y,x+12,slab_y-20,Brushes.LightGray)
            text(cx,slab_y-42,tr(u'Перекрытие (условно)',u'Slab (symbolic)'),center=True)
            profile = section['profile_height']
            if profile:
                rectangle(0,-ch/2+profile/2,cw,profile,Brushes.Gray,Brushes.Gainsboro)
            for x in section['rods']:
                line(x,-ch/2,x,h/2+gap,Brushes.DimGray,2)
                line_px(X(x),slab_y-10,X(x),slab_y,Brushes.Black,4)
                # External exposed rod's fire protection, per ATR 90 sheet15 / 180 sheet14.
                line_px(X(x)-4,slab_y,X(x)-4,Y(h/2),Brushes.LightPink,3)
                line_px(X(x)+4,slab_y,X(x)+4,Y(h/2),Brushes.LightPink,3)
            for z in section['crossbars']:
                rectangle(0,z-section['crossbar_height']/2,
                          section['rods'][-1]-section['rods'][0]+20,
                          section['crossbar_height'],Brushes.DimGray,Brushes.Gainsboro)
            vertical(X(w/2)+25,Y(h/2+gap),Y(h/2),fmt(gap)+u' *')
            text(560,110,tr(u'Шпильки М8/М10 *',u'M8/M10 rods *'),size=13)
            text(560,132,tr(u'Розовое: огнезащита подвесов',u'Pink: rod fire protection'),size=12)
            text(560,155,tr(u'Траверсы 30×30',u'Crossbars 30×30'),size=13)
            text(560,177,tr(u'Стенка: {}',u'Wall: {}').format(fmt(section['wall'])),size=13)
            text(560,199,tr(u'В свету: {} × {}',u'Clear: {} × {}').format(fmt(cw),fmt(ch)),size=13)
            if profile:
                text(560,221,tr(u'Каркас днища: 50×40',u'Floor frame: 50×40'),size=13)
            text(560,250,tr(u'Стенка → шпилька: {} *',u'Wall → rod: {} *').format(fmt(section['rod_inset'])),size=12)
            tray_left = min(row['x']-row['width']/2 for row in section['trays'])
            text(560,271,tr(u'Шпилька → лоток: {}',u'Rod → tray: {}').format(fmt(tray_left-section['rods'][0])),size=12)
        for row in section['trays']:
            left,right = row['x']-row['width']/2,row['x']+row['width']/2
            bottom,top = row['z']-row['height']/2,row['z']+row['height']/2
            line(left,top,left,bottom,Brushes.SteelBlue,3)
            line(left,bottom,right,bottom,Brushes.SteelBlue,3)
            line(right,bottom,right,top,Brushes.SteelBlue,3)
            text(X(row['x']),Y(row['z'])-8,str(row['index']+1),center=True)
            horizontal(X(left),X(right),Y(top)-14,fmt(row['width']))
            vertical(X(right)+13,Y(top),Y(bottom),fmt(row['height']))
        if settings['arrangement'] == 'vertical':
            ordered = sorted(section['trays'],key=lambda row: row['z'])
            for lower,upper in zip(ordered,ordered[1:]):
                top = lower['z']+lower['height']/2
                bottom = upper['z']-upper['height']/2
                vertical(X(-w/2)-16,Y(bottom),Y(top),fmt(bottom-top))
        else:
            ordered = sorted(section['trays'],key=lambda row: row['x'])
            for left,right in zip(ordered,ordered[1:]):
                a,b = left['x']+left['width']/2,right['x']-right['width']/2
                horizontal(X(a),X(b),Y(section['tray_bottom'])-18,fmt(b-a))
        # Physical clearances around the complete tray group.
        vertical(X(w/2)+40,Y(ch/2),Y(section['tray_top']),fmt(section['top_clear']))
        vertical(X(w/2)+40,Y(section['tray_bottom']),Y(-ch/2),fmt(section['bottom_clear']))
        if section['middle_rod_missing']:
            text(25,590,tr(u'Нужен проект дополнительной подвески: шпилька пересекает лотки.',
                            u'Extra suspension must be designed: a central rod intersects trays.'),brush=Brushes.Firebrick,size=13)

    horizontal(X(-w/2),X(w/2),Y(-h/2)+40,fmt(w),Y(-h/2))
    vertical(X(-w/2)-40,Y(h/2),Y(-h/2),fmt(h),X(-w/2))
    if supported:
        horizontal(X(section['rods'][0]),X(section['rods'][-1]),Y(-h/2)+77,
                   tr(u'Между осями шпилек: {}',u'Rod axes: {}').format(fmt(section['rods'][-1]-section['rods'][0])))
        text(25,618,tr(u'* Проектные размеры. Шпильки и траверсы показаны на разрезе.',
                      u'* Project inputs. Rods and crossbars are shown in section.'),size=13)
