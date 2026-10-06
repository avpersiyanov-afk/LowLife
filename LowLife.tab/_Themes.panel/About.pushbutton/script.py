# -*- coding: utf-8 -*-
__title__ = u"LowLife"
__doc__ = u"О программе: логотип, версия расширения, поддерживаемые версии Revit, таблица параметров, ссылка на репозиторий и лицензия"
__author__ = "Pipers"

import os

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System import Uri
from System.Diagnostics import Process, ProcessStartInfo
from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage
from pyrevit import forms

from lowlife import about, wordmark_wpf

HERE = os.path.dirname(os.path.abspath(__file__))


def _open_url(url):
    # UseShellExecute — иначе в Revit 2025+ (.NET 8) ссылка не откроется в браузере.
    info = ProcessStartInfo(url)
    info.UseShellExecute = True
    Process.Start(info)


def _bitmap(path):
    bmp = BitmapImage()
    bmp.BeginInit()
    bmp.UriSource = Uri(path)
    bmp.CacheOption = BitmapCacheOption.OnLoad
    bmp.EndInit()
    return bmp


def _revit_version():
    try:
        return __revit__.Application.VersionNumber
    except Exception:
        return None


class AboutWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(HERE, "about.xaml"))
        self.logo_img.Source = _bitmap(os.path.join(HERE, "logo.png"))
        try:
            self.wordmark_img.Source = wordmark_wpf.build_image()
        except Exception:
            # Название шрифтом не собралось — показываем авторскую графику.
            self.wordmark_img.Source = _bitmap(os.path.join(
                about.extension_root(), "docs", "brand", "lowlife-wordmark.png"))
        self.tagline_tb.Text = about.TAGLINE
        self.disciplines_tb.Text = about.DISCIPLINES
        self.version_tb.Text = about.version_text()
        self.revit_tb.Text = about.revit_version_text(_revit_version())
        self.revit_support_tb.Text = about.revit_support_summary()
        self.params_link.Click += lambda s, e: _open_url(about.PARAMS_URL)
        self.repo_run.Text = about.REPO_URL
        self.repo_link.Click += lambda s, e: _open_url(about.REPO_URL)
        self.license_run.Text = about.LICENSE_TEXT
        self.license_link.Click += lambda s, e: _open_url(about.LICENSE_URL)
        self.copyright_tb.Text = about.COPYRIGHT
        self.close_btn.Click += lambda s, e: self.Close()


AboutWindow().ShowDialog()
