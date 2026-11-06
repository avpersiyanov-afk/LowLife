# -*- coding: utf-8 -*-
"""Modal graphic preview: task rectangles and the resulting opening envelope."""
from pyrevit import forms
from System.Windows.Controls import Canvas, TextBlock
from System.Windows.Media import Brushes, DoubleCollection
from System.Windows.Shapes import Rectangle, Line
from lowlife.i18n import tr
from lowlife import opening_tasks_preview_core as core


def show(records):
    projection=core.project(records)
    class Preview(forms.WPFWindow):
        def __init__(self):
            forms.WPFWindow.__init__(self,u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
              xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Width="980" Height="760"
              MinWidth="850" MinHeight="650" WindowStartupLocation="CenterScreen">
              <Grid Margin="20"><Grid.RowDefinitions><RowDefinition Height="Auto"/>
                <RowDefinition Height="*"/><RowDefinition Height="140"/><RowDefinition Height="Auto"/>
              </Grid.RowDefinitions>
              <TextBlock x:Name="heading" FontSize="17" TextWrapping="Wrap" Margin="0,0,0,10"/>
              <Viewbox Grid.Row="1" Stretch="Uniform"><Canvas x:Name="diagram" Width="850" Height="410" Background="White"/></Viewbox>
              <TextBox x:Name="legend" Grid.Row="2" IsReadOnly="True" TextWrapping="Wrap" VerticalScrollBarVisibility="Auto" Margin="0,10,0,10"/>
              <StackPanel Grid.Row="3" Orientation="Horizontal" HorizontalAlignment="Right">
                <Button x:Name="accept" Padding="16,8" Margin="0,0,12,0"/>
                <Button x:Name="cancel" Padding="16,8" IsCancel="True"/>
              </StackPanel></Grid></Window>''',literal_string=True)
            self.result=False
            self.Title=tr(u'Предпросмотр объединения',u'Merge preview')
            self.heading.Text=tr(u'Синие контуры — задания ВИС. Оранжевый — итоговое отверстие. Размеры в мм; допустимость объединения проверяет КР.',
                                 u'Blue outlines: VIS tasks. Orange: resulting opening. Dimensions in mm; KR must verify the merge is acceptable.')
            self.accept.Content=tr(u'Объединить и принять',u'Merge and accept')
            self.cancel.Content=tr(u'Отмена',u'Cancel')
            self.accept.Click+=self.confirm
            self.cancel.Click+=lambda s,e:self.Close()
            x,y,w,h=projection['outline']
            scale=min(660.0/max(w,1),265.0/max(h,1))
            left=95+(660-w*scale)/2
            top=50+(265-h*scale)/2
            for i,rectangle in enumerate(projection['rectangles']):
                a,b,rw,rh=rectangle
                px=left+(a-x)*scale
                py=top+(y+h-b-rh)*scale
                self.rect(px,py,rw*scale,rh*scale,Brushes.RoyalBlue,False)
                self.label(px+4,py+4,str(i+1))
            self.rect(left,top,w*scale,h*scale,Brushes.DarkOrange,True)
            self.label(95,350,tr(u'Итог: {:.0f} × {:.0f} мм',u'Result: {:.0f} × {:.0f} mm').format(float(w),float(h)))
            self.label(95,380,tr(u'Проекция на стену',u'Wall projection') if projection['geometry']['kind']=='wall' else tr(u'Проекция на плиту',u'Floor projection'))
            lines=[]
            for i,r in enumerate(records):
                lines.append(u'{} | {} | {} | r{} | {}'.format(i+1,r.get('discipline',''),r['task_id'],r['revision'],
                      u' × '.join(u'{:.0f}'.format(float(v)) for v in r['geometry']['size_mm'])))
            lines.append(tr(u'Ранее принятые отверстия могут быть обновлены или заменены. Если замена затрагивает марки/размеры, операция будет остановлена.',
                            u'Previously accepted openings may be updated or replaced. Replacement affecting tags/dimensions will be blocked.'))
            self.legend.Text=u'\n'.join(lines)
        def label(self,x,y,value):
            text=TextBlock();text.Text=value;text.FontSize=15
            Canvas.SetLeft(text,x);Canvas.SetTop(text,y);self.diagram.Children.Add(text)
        def rect(self,x,y,w,h,color,dashed):
            rect=Rectangle();rect.Width=max(w,1);rect.Height=max(h,1);rect.Stroke=color;rect.StrokeThickness=3 if dashed else 2
            if dashed:
                rect.StrokeDashArray=DoubleCollection([5.,3.])
            Canvas.SetLeft(rect,x);Canvas.SetTop(rect,y);self.diagram.Children.Add(rect)
        def confirm(self,sender,event):
            self.result=True;self.Close()
    window=Preview();window.ShowDialog()
    return window.result
