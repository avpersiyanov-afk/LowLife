#!/usr/bin/env python3
"""Build clearly labelled UI diagrams and the Russian opening-task PDF.

Run with CPython, Pillow and reportlab. Role tabs/actions come from the manifest.
These are documentation diagrams, never screenshots or evidence of a Revit run.
"""
from pathlib import Path
import html
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from lowlife import opening_tasks_manifest as manifest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image as PdfImage,
                               PageBreak, Table, TableStyle)

DEST = ROOT / 'docs/opening-tasks-guide'
FONT_DIR = Path('/usr/share/fonts/truetype/dejavu')
FONT = FONT_DIR / 'DejaVuSans.ttf'
BOLD = FONT_DIR / 'DejaVuSans-Bold.ttf'
COMMON = {'remark_show': 'Показать группу', 'refresh': 'Обновить обмен', 'journal_open': 'Открыть таблицу',
          'settings': 'Настройки', 'parts_refresh': 'Обновить номера корпусов',
          'journal_setup': 'Подключение таблицы', 'highlight': 'Подсветить на виде'}


def diagram(role, tab_index, filename):
    """Schematic of the actual WPF hierarchy; action labels are not invented."""
    im = Image.new('RGB', (1460, 970), '#edf2f7')
    d = ImageDraw.Draw(im)
    def font(size=18, bold=False):
        return ImageFont.truetype(str(BOLD if bold else FONT), size)
    def text(x, y, value, size=18, fill='#182638', bold=False):
        d.text((x,y),value,font=font(size,bold),fill=fill)
    def rect(box, fill='white', outline='#bac4cf'):
        d.rectangle(box,fill=fill,outline=outline,width=1)
    def control(x,y,label,dropdown=False):
        width=int(d.textlength(label,font=font(17)))+28+(20 if dropdown else 0)
        rect((x,y,x+width,y+31),'#fafafa')
        text(x+10,y+5,label,17)
        if dropdown:text(x+width-21,y+5,'▾',17)
        return width+8
    def badge(n,y):
        d.ellipse((24,y,58,y+34),fill='#1769a8')
        text(35,y+5,str(n),18,'white',True)
    name={'VIS':'ВИС','KR':'КР','AR':'АР'}[role]
    text(24,17,'СХЕМА ИНТЕРФЕЙСА • учебные данные • не снимок Revit',17,'#526578')
    rect((75,57,1430,792),'white')
    rect((75,57,1430,96),'#f2f2f2')
    text(91,67,'Задания '+name,18)
    text(1395,67,'×',20)
    purpose='Подготовка и выдача заданий' if role=='VIS' else 'Рассмотрение и создание отверстий'
    text(95,113,'Задания '+name+' — '+purpose+' | Учебная модель',21,bold=True)
    groups=manifest.action_groups(role)
    labels=dict(manifest.actions(role));labels.update(COMMON)
    x=95
    for i,(title,actions) in enumerate(groups):
        width=int(d.textlength(title,font=font(18)))+30
        rect((x,155,x+width,191),'#e0edf9' if i==tab_index else '#f3f3f3')
        text(x+14,163,title,18,bold=i==tab_index)
        x+=width+2
    badge(1,155)
    x,y=104,204
    for key in groups[tab_index][1]:
        if key=='change_part':
            continue  # available from the table context menu
        width=int(d.textlength(labels[key],font=font(17)))+34
        if x+width>1405:x,y=104,y+39
        x+=control(x,y,labels[key])
    badge(2,206)
    y=max(294,y+48)
    text(96,y,'Объект: УЧЕБНЫЙ-01',17)
    control(360,y-4,'НЧ-1',True)
    badge(3,y-5)
    text(96,y+38,'Обмен: сохранить модель → обновить связь смежника в Revit → «Обновить обмен».',16,'#526578')
    rect((96,y+71,1408,y+103),'white')
    text(108,y+78,'Поиск по номеру, GUID, модели, уровню и размерам…',16,'#6a7887')
    x=96;fy=y+114
    for label in ['Все номера корпусов','Все статусы','Все дисциплины','Все уровни','Все конструкции','Все замечания']:
        x+=control(x,fy,label,True)
    x=96;fy+=39
    for label in ['Все ответы','Все получатели','Все выпуски']:
        x+=control(x,fy,label,True)
    text(x+6,fy+6,'□ Требуют внимания',16)
    x+=230
    x+=control(x,fy,'Сбросить фильтры')
    control(x,fy,'Выбрать показанные')
    badge(4,y+78)
    top=fy+49
    columns=[('Номер корпуса',165),('Задание',210),('Статус',245),('Получатель',145),('Дисциплина',145),('Модель',205),('Уровень',197)]
    x=96
    for label,width in columns:
        rect((x,top,x+width,top+37),'#f0f2f5')
        text(x+8,top+10,label,15,bold=True);x+=width
    for i in range(3):
        yy=top+38+i*37
        rect((96,yy,1408,yy+36),'#dcecff' if i==0 else 'white')
        values=['НЧ-1','ОВиК-ОТВ-0000'+str(i+1),['Выдано','Изменено после выдачи','Черновик'][i] if role=='VIS' else ['Принято','Новое','Замечание'][i],
                'АР' if role=='AR' or (role=='VIS' and tab_index==1) else 'КР','ОВиК','Учебная модель','Этаж 01']
        x=96
        for value,(_,width) in zip(values,columns):text(x+8,yy+9,value,14);x+=width
    rect((96,top+150,1408,top+164),'#e6e9ed')
    rect((99,top+153,820,top+161),'#bbc5cf')
    text(96,top+178,'Выбрано: 1 | ОВиК-ОТВ-00001 | Размеры: 500 × 300 мм',16)
    text(96,top+205,'GUID и ID элемента • смещение • замечание получателя — в карточке выбранной строки',15,'#526578')
    badge(5,top+48);badge(6,top+177)
    captions=['1  Вкладки команд: выберите этап работы.', '2  Кнопки выбранной вкладки; пояснение — при наведении.',
              '3  Шифр из модели и номер корпуса из Google-справочника.', '4  Поиск и фильтры работают совместно; скрытые строки не изменяются.',
              '5  Выберите строки: Ctrl / Shift — несколько; прокрутите вправо для остальных столбцов.',
              '6  Карточка выбора: размеры, GUID, смещение и замечание.']
    for i,label in enumerate(captions):text(78,811+i*23,label,16)
    im.save(DEST/'images'/filename,optimize=True)


def connection():
    im=Image.new('RGB',(1160,720),'#edf2f7');d=ImageDraw.Draw(im)
    f=lambda size,bold=False:ImageFont.truetype(str(BOLD if bold else FONT),size)
    def t(x,y,s,size=20,color='#182638',bold=False):d.text((x,y),s,font=f(size,bold),fill=color)
    t(28,20,'СХЕМА ОКНА • пример без адреса и токена • не снимок Revit',18,'#526578')
    d.rectangle((90,70,1070,663),fill='white',outline='#bac4cf')
    t(116,91,'Подключение журнала',25,bold=True)
    t(116,143,'Проект: УЧЕБНЫЙ-01 | Отдел: Определится по токену',19)
    t(116,176,'ID модели: учебный пример',17,'#526578')
    for yy,label,value,hint in [(225,'Адрес Google Apps Script','Адрес веб-приложения, заканчивающийся на /exec','Адрес выдаёт администратор. Ссылка на саму таблицу не подходит.'),
                                (355,'Токен','••••••••••••••••••••','Токен отдела. Отдел определяется автоматически; повторный выбор не нужен.')]:
        t(116,yy,label,20,bold=True)
        d.rectangle((116,yy+35,1044,yy+76),fill='white',outline='#9aabbc')
        t(130,yy+45,value,18,'#526578');t(116,yy+88,hint,17,'#657585')
    t(116,488,'Сохраняется в вашем профиле Windows для всех моделей отдела.',18,'#526578')
    for yy,label in [(542,'Инструкция подключения Google'),(595,'Проверить и сохранить')]:
        d.rectangle((116,yy,1044,yy+39),fill='#eef2f6',outline='#a7b4c2');t(138,yy+8,label,19)
    im.save(DEST/'images/connection.png',optimize=True)


def pdf():
    pdfmetrics.registerFont(TTFont('Guide',str(FONT)))
    pdfmetrics.registerFont(TTFont('GuideBold',str(BOLD)))
    pdfmetrics.registerFontFamily('Guide',normal='Guide',bold='GuideBold',italic='Guide',boldItalic='GuideBold')
    styles=getSampleStyleSheet()
    for name in ['Normal','BodyText','Heading1','Heading2','Heading3']:
        styles[name].fontName='GuideBold' if name.startswith('Heading') else 'Guide'
        styles[name].leading=13
        styles[name].fontSize=9.5
        styles[name].spaceBefore=0
        styles[name].spaceAfter=4
    styles['Heading1'].fontSize=19;styles['Heading1'].leading=24
    styles['Heading2'].fontSize=13;styles['Heading2'].leading=18
    styles.add(ParagraphStyle('Cell',fontName='Guide',fontSize=8,leading=11))
    def inline(s):
        s=re.sub(r'\[([^]]+)\]\([^)]+\)',r'\1',s)
        s=html.escape(s).replace('`','')
        return re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',s)
    story=[]
    for index,file in enumerate(['README.md','common.md','vis.md','kr.md','ar.md']):
        if index:story.append(PageBreak())
        content=(DEST/file).read_text()
        if file=='README.md':
            content=content.split('## Обновление иллюстраций для сопровождения')[0]
        lines=content.splitlines();i=0
        while i<len(lines):
            line=lines[i].strip();i+=1
            if not line:continue
            if line.startswith('!['):
                path=re.search(r'\]\(([^)]+)\)',line).group(1)
                w,h=Image.open(DEST/path).size
                story.append(PdfImage(str(DEST/path),width=483,height=483*h/w));story.append(Spacer(1,8));continue
            if line.startswith('|'):
                table=[line]
                while i<len(lines) and lines[i].strip().startswith('|'):table.append(lines[i].strip());i+=1
                rows=[]
                for row in table:
                    if re.match(r'^\|[\s:|\-]+\|$',row):continue
                    rows.append([Paragraph(inline(c.strip()),styles['Cell']) for c in row.strip('|').split('|')])
                count=len(rows[0]);t=Table(rows,colWidths=[483/count]*count,repeatRows=1,hAlign='LEFT')
                t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e5edf6')),
                    ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#c5cfda')),('VALIGN',(0,0),(-1,-1),'TOP'),
                    ('LEFTPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
                story.extend([t,Spacer(1,8)]);continue
            if line.startswith('#'):
                level=len(line)-len(line.lstrip('#'));style=styles['Heading1' if level==1 else 'Heading2']
                story.append(Paragraph(inline(line.lstrip('# ')),style));continue
            paragraph=line
            while i<len(lines) and lines[i].strip() and not re.match(r'^(#|!\[|\||\d+\.|- )',lines[i].strip()):
                paragraph+=' '+lines[i].strip();i+=1
            story.append(Paragraph(inline(paragraph),styles['BodyText']));story.append(Spacer(1,3))
    def footer(canvas,doc):
        canvas.setFont('Guide',8);canvas.setFillColor(colors.HexColor('#526578'))
        canvas.drawString(40,25,'LowLife • Задания на отверстия • схемы интерфейса, учебные данные')
        canvas.drawRightString(555,25,str(doc.page))
    SimpleDocTemplate(str(DEST/'LowLife-OpeningTasks-Guide.pdf'),pagesize=(595,842),
        leftMargin=56,rightMargin=56,topMargin=40,bottomMargin=42,
        title='LowLife — инструкции ВИС, КР и АР',author='LowLife').build(story,onFirstPage=footer,onLaterPages=footer)


if __name__=='__main__':
    (DEST/'images').mkdir(parents=True,exist_ok=True)
    for role,index,name in [('VIS',0,'vis-kr.png'),('VIS',1,'vis-ar.png'),('VIS',2,'vis-control.png'),
                            ('KR',0,'kr-review.png'),('KR',1,'kr-views.png'),('AR',0,'ar-review.png'),
                            ('VIS',4,'settings.png')]:diagram(role,index,name)
    connection();pdf()
    print('Built 8 UI diagrams and LowLife-OpeningTasks-Guide.pdf')
