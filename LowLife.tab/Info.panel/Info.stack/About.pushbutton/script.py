# -*- coding: utf-8 -*-
__title__ = u"О программе"
__doc__ = u"О программе: логотип, версия расширения, поддерживаемые версии Revit, таблица параметров, ссылка на репозиторий и лицензия"
__author__ = "Pipers"

import os
from lowlife.i18n import tr

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System import Uri
from System.Diagnostics import Process, ProcessStartInfo
from System.Windows import Visibility
from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage
from pyrevit import forms

from lowlife import about, greeting_window, wordmark_wpf, xaml_i18n

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
        forms.WPFWindow.__init__(self, xaml_i18n.load(os.path.join(HERE, "about.xaml")), literal_string=True)
        self.logo_img.Source = _bitmap(os.path.join(HERE, "logo.png"))
        try:
            self.wordmark_img.Source = wordmark_wpf.build_image()
        except Exception:
            # Название шрифтом не собралось — показываем авторскую графику.
            self.wordmark_img.Source = _bitmap(os.path.join(
                about.extension_root(), "docs", "brand", "lowlife-wordmark.png"))
        self.tagline_tb.Text = tr(about.TAGLINE)
        self.disciplines_tb.Text = tr(about.DISCIPLINES)
        self.version_tb.Text = about.version_text()
        self.revit_tb.Text = about.revit_version_text(_revit_version())
        self.revit_support_tb.Text = about.revit_support_summary()
        self.params_link.Click += lambda s, e: _open_url(about.PARAMS_URL)
        self.repo_run.Text = about.REPO_URL
        self.repo_link.Click += lambda s, e: _open_url(about.REPO_URL)
        self.license_run.Text = tr(about.LICENSE_TEXT)
        self.license_link.Click += lambda s, e: _open_url(about.LICENSE_URL)
        self.copyright_tb.Text = about.COPYRIGHT
        self.greeting_cb.IsChecked = greeting_window.startup_enabled()
        self.greeting_cb.Checked += lambda s, e: greeting_window.set_startup_enabled(True)
        self.greeting_cb.Unchecked += lambda s, e: greeting_window.set_startup_enabled(False)
        self._init_usage()
        self.close_btn.Click += lambda s, e: self.Close()

    def _init_usage(self):
        # статистика запусков (pnotes/usage.py): действует сразу, без перезапуска Revit
        try:
            from pnotes import usage
            self.usage_cb.IsChecked = usage.is_enabled()
        except Exception:
            self.usage_cb.Visibility = Visibility.Collapsed
            return
        self.usage_cb.Checked += lambda s, e: _set_usage(True)
        self.usage_cb.Unchecked += lambda s, e: _set_usage(False)


def _set_usage(value):
    try:
        from pnotes import usage
        usage.set_enabled(value)
    except Exception as ex:
        forms.alert(tr(u'Не удалось сохранить настройку статистики: {}').format(ex), title=u'LowLife')


AboutWindow().ShowDialog()
