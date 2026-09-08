# -*- coding: utf-8 -*-
__title__ = "Тише"
__doc__ = "Уменьшает системную громкость Windows на один шаг."
__author__ = "Pipers"

from lowlife.media_keys import press_key, VK_VOLUME_DOWN

press_key(VK_VOLUME_DOWN)
