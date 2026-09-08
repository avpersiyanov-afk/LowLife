# -*- coding: utf-8 -*-
__title__ = u"Громче"
__doc__ = u"Увеличивает системную громкость Windows на один шаг."
__author__ = "Pipers"

from lowlife.media_keys import press_key, VK_VOLUME_UP

press_key(VK_VOLUME_UP)
