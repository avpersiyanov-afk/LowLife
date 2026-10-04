# -*- coding: utf-8 -*-
__title__ = u"LowLife"
__doc__ = u"О программе: логотип, версия расширения и ссылка на репозиторий"
__author__ = "Pipers"

import os

from System import Uri
from System.Diagnostics import Process
from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage
from pyrevit import forms

from lowlife import about, wordmark_wpf

HERE = os.path.dirname(os.path.abspath(__file__))


def _bitmap(name):
    bmp = BitmapImage()
    bmp.BeginInit()
    bmp.UriSource = Uri(os.path.join(HERE, name))
    bmp.CacheOption = BitmapCacheOption.OnLoad
    bmp.EndInit()
    return bmp


class AboutWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(HERE, "about.xaml"))
        self.logo_img.Source = _bitmap("logo.png")
        self.wordmark_path.Data = wordmark_wpf.build_geometry()
        self.tagline_tb.Text = about.TAGLINE
        self.disciplines_tb.Text = about.DISCIPLINES
        self.version_tb.Text = about.version_text()
        self.repo_run.Text = about.REPO_URL
        self.repo_link.Click += lambda s, e: Process.Start(about.REPO_URL)
        self.close_btn.Click += lambda s, e: self.Close()


AboutWindow().ShowDialog()
