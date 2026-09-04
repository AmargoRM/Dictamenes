# -*- coding: utf-8 -*-
from __future__ import annotations

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .dockwidget import DictamenesDADockWidget


class DictamenesDAPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None
        self.dock = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.svg")
        self.action = QAction(QIcon(icon_path), "Dictámenes-DA", self.iface.mainWindow())
        self.action.setObjectName("dictamenes_da_action")
        self.action.setToolTip("Generar dictámenes de cuerpo de agua con captura de puntos en mapa")
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Dictámenes-DA", self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Dictámenes-DA", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock = None

    def run(self):
        if self.dock is None:
            self.dock = DictamenesDADockWidget(self.iface, self.plugin_dir, self.iface.mainWindow())
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.show()
        self.dock.raise_()
