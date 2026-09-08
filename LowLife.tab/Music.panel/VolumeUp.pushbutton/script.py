# -*- coding: utf-8 -*-
__title__ = "Громче"
__doc__ = "Увеличивает системную громкость Windows на один шаг."
__author__ = "Pipers"

from lowlife.media_keys import press_key, VK_VOLUME_UP

press_key(VK_VOLUME_UP)
