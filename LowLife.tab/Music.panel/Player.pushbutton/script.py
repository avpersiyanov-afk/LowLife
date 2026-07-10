# -*- coding: utf-8 -*-

from pyrevit import forms
import ctypes


VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1

VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF


def press_key(key):

    ctypes.windll.user32.keybd_event(
        key,
        0,
        0,
        0
    )

    ctypes.windll.user32.keybd_event(
        key,
        0,
        2,
        0
    )


class Player(forms.WPFWindow):

    def __init__(self):

        forms.WPFWindow.__init__(
            self,
            "Player.xaml"
        )


    def PlayButton_Click(self, sender, args):
        press_key(VK_MEDIA_PLAY_PAUSE)


    def NextButton_Click(self, sender, args):
        press_key(VK_MEDIA_NEXT)


    def PrevButton_Click(self, sender, args):
        press_key(VK_MEDIA_PREV)


    def VolUpButton_Click(self, sender, args):
        press_key(VK_VOLUME_UP)


    def VolDownButton_Click(self, sender, args):
        press_key(VK_VOLUME_DOWN)



Player().ShowDialog()
