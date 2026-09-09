# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.gui import QgsMapToolEmitPoint, QgsMapTool, QgsRubberBand
from qgis.core import QgsGeometry, QgsPointXY, QgsRectangle, QgsWkbTypes


class DictamenMapClickTool(QgsMapToolEmitPoint):
    """Map tool pequeño: emite el punto QGIS cuando el usuario suelta el clic."""
    canvas_clicked = pyqtSignal(object)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas

    def canvasReleaseEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        self.canvas_clicked.emit(point)


class RectangleMapTool(QgsMapTool):
    """Dibuja un rectángulo arrastrando el mouse y deja un recuadro visible.

    Emite rectangle_created(QgsRectangle) en coordenadas del lienzo. El recuadro
    (rubber band) queda visible hasta que se llame a clear().
    """
    rectangle_created = pyqtSignal(object)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.rubber = QgsRubberBand(canvas, QgsWkbTypes.PolygonGeometry)
        try:
            self.rubber.setColor(QColor(255, 0, 0))
            self.rubber.setFillColor(QColor(255, 0, 0, 40))
            self.rubber.setStrokeColor(QColor(255, 0, 0))
        except Exception:
            self.rubber.setColor(QColor(255, 0, 0))
        self.rubber.setWidth(2)
        self.start = None
        self.dragging = False

    def canvasPressEvent(self, event):
        self.start = self.toMapCoordinates(event.pos())
        self.dragging = True

    def canvasMoveEvent(self, event):
        if not self.dragging or self.start is None:
            return
        self._draw(self.start, self.toMapCoordinates(event.pos()))

    def canvasReleaseEvent(self, event):
        if self.start is None:
            return
        end = self.toMapCoordinates(event.pos())
        rect = QgsRectangle(self.start, end)
        self._draw(self.start, end)
        self.start = None
        self.dragging = False
        if rect.width() > 0 and rect.height() > 0:
            self.rectangle_created.emit(rect)

    def _draw(self, p1, p2):
        rect = QgsRectangle(p1, p2)
        self.rubber.reset(QgsWkbTypes.PolygonGeometry)
        pts = [
            QgsPointXY(rect.xMinimum(), rect.yMinimum()),
            QgsPointXY(rect.xMaximum(), rect.yMinimum()),
            QgsPointXY(rect.xMaximum(), rect.yMaximum()),
            QgsPointXY(rect.xMinimum(), rect.yMaximum()),
        ]
        self.rubber.setToGeometry(QgsGeometry.fromPolygonXY([pts]), None)

    def clear(self):
        try:
            self.rubber.reset(QgsWkbTypes.PolygonGeometry)
        except Exception:
            pass
