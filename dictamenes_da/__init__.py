# -*- coding: utf-8 -*-
def classFactory(iface):
    from .dictamenes_da import DictamenesDAPlugin
    return DictamenesDAPlugin(iface)
