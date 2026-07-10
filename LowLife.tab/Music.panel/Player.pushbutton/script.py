# -*- coding: utf-8 -*-

from pyrevit import forms
import ctypes


# Windows Media Keys

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


class MusicWindow(forms.WPFWindow):

    def __init__(self):
        xaml = """
        <Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                Title="LowLife Music"
                Width="250"
                Height="120"
                WindowStartupLocation="CenterScreen">

            <StackPanel>

                <TextBlock Text="🎵 LowLife Music"
                           HorizontalAlignment="Center"
                           FontSize="18"
                           Margin="10"/>

                <StackPanel Orientation="Horizontal"
                            HorizontalAlignment="Center">

                    <Button Name="Prev"
                            Content="⏮"
                            Width="50"/>

                    <Button Name="Play"
                            Content="▶️"
                            Width="50"/>

                    <Button Name="Next"
                            Content="⏭"
                            Width="50"/>

                </StackPanel>


                <StackPanel Orientation="Horizontal"
                            HorizontalAlignment="Center">

                    <Button Name="VolDown"
                            Content="🔉"
                            Width="50"/>

                    <Button Name="VolUp"
                            Content="🔊"
                            Width="50"/>

                </StackPanel>

            </StackPanel>

        </Window>
        """

        forms.WPFWindow.__init__(self, xaml)


    def Prev_click(self, sender, args):
        press_key(VK_MEDIA_PREV)


    def Play_click(self, sender, args):
        press_key(VK_MEDIA_PLAY_PAUSE)


    def Next_click(self, sender, args):
        press_key(VK_MEDIA_NEXT)


    def VolDown_click(self, sender, args):
        press_key(VK_VOLUME_DOWN)


    def VolUp_click(self, sender, args):
        press_key(VK_VOLUME_UP)



MusicWindow().ShowDialog()
