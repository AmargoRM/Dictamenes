# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import pyqtSignal
from qgis.gui import QgsMapToolEmitPoint


class DictamenMapClickTool(QgsMapToolEmitPoint):
    """Map tool pequeño: emite el punto QGIS cuando el usuario suelta el clic."""
    canvas_clicked = pyqtSignal(object)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas

    def canvasReleaseEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        self.canvas_clicked.emit(point)
