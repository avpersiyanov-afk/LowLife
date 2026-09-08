# -*- coding: utf-8 -*-
__title__ = u"Следующий\nтрек"
__doc__ = u"Переключает активный проигрыватель на следующий трек (медиаклавиша Windows Next)."
__author__ = "Pipers"

from lowlife.media_keys import press_key, VK_MEDIA_NEXT

press_key(VK_MEDIA_NEXT)
