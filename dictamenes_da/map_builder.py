# -*- coding: utf-8 -*-
"""Generación del mapa de referencia (Figura 1) y capas de puntos.

- Fondo Google Satélite Híbrido (XYZ, requiere internet).
- Capa de red hídrica (Red.hidrica.min.geojson) como contexto.
- Cuadrícula CRTM05 (EPSG:5367) solo con marcas externas (ticks) y etiquetas.
- Simbología por tipo de fuente:
    * Naciente / fuentes puntuales: círculo azul tamaño 3.
    * Ríos / quebradas: cruz; inicio verde, final verde oscuro.
    * Puntos de control: círculo rojo tamaño 2.
- Etiquetas con el nombre de la fuente, ubicadas a la izquierda del punto.

Todo debe correr en el HILO PRINCIPAL de QGIS (no en un QgsTask).
"""
from __future__ import annotations

import os

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsLayout,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemMapGrid,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsRuleBasedRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

CRTM05 = "EPSG:5367"
GOOGLE_HYBRID_URI = (
    "type=xyz&url=https://mt1.google.com/vt/lyrs%3Dy%26x%3D%7Bx%7D%26y%3D%7By%7D%26z%3D%7Bz%7D"
    "&zmax=20&zmin=0"
)
RIVER_FILE = "Red.hidrica.min.geojson"

_LINE_TYPES = ("Río", "Rio", "Quebrada")
_NICE_INTERVALS = [50, 100, 250, 500, 1000, 2000, 5000, 10000, 25000, 50000]


def _nice_grid_interval(width_m: float) -> float:
    if width_m <= 0:
        return 1000.0
    target = width_m / 5.0
    for value in _NICE_INTERVALS:
        if value >= target:
            return float(value)
    return float(_NICE_INTERVALS[-1])


def collect_map_points(snapshot: dict):
    """Transforma los puntos del formulario a CRTM05 y arma sus atributos.

    Devuelve lista de dicts: x, y, nombre, tipo, numero, rol, etq.
    """
    input_auth = snapshot.get("input_crs") or CRTM05
    src_crs = QgsCoordinateReferenceSystem(input_auth)
    dst_crs = QgsCoordinateReferenceSystem(CRTM05)
    transform = None
    if src_crs != dst_crs:
        transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())

    def to_crtm(x_text, y_text):
        try:
            pt = QgsPointXY(float(x_text), float(y_text))
        except (TypeError, ValueError):
            return None
        return transform.transform(pt) if transform is not None else pt

    points = []
    for idx, src in enumerate(snapshot.get("sources", []), start=1):
        num = (src.get("numero_fuente") or str(idx)).strip()
        tipo = (src.get("tipo_fuente") or "").strip()
        nombre = (src.get("nombre_fuente") or "").strip()
        for kx, ky, kn, rol in (
            ("start_x", "start_y", "start_number", "Inicio"),
            ("end_x", "end_y", "end_number", "Final"),
        ):
            if not str(src.get(kx, "")).strip() or not str(src.get(ky, "")).strip():
                continue
            pt = to_crtm(src.get(kx), src.get(ky))
            if pt is None:
                continue
            pnum = (src.get(kn) or "").strip()
            # Etiqueta igual al Cuadro 1: "Fuente N - Rol (Punto X)".
            etq = f"Fuente {num} - {rol}"
            if pnum:
                etq += f" (Punto {pnum})"
            points.append({
                "x": pt.x(), "y": pt.y(), "nombre": nombre, "tipo": tipo,
                "numero": num, "rol": rol, "etq": etq,
            })
    for row, cp in enumerate(snapshot.get("control_points", []), start=1):
        if not str(cp.get("x", "")).strip() or not str(cp.get("y", "")).strip():
            continue
        pt = to_crtm(cp.get("x"), cp.get("y"))
        if pt is None:
            continue
        base = (cp.get("label") or f"Control {row}").strip()
        pnum = (cp.get("number") or "").strip()
        etq = base + (f" (Punto {pnum})" if pnum else "")
        points.append({
            "x": pt.x(), "y": pt.y(), "nombre": base, "tipo": "Control",
            "numero": pnum, "rol": "Control", "etq": etq,
        })
    return points


def _text_format_white(size=9):
    tf = QgsTextFormat()
    tf.setSize(size)
    tf.setColor(QColor(255, 255, 255))
    try:
        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(1)
        buf.setColor(QColor(0, 0, 0))
        tf.setBuffer(buf)
    except Exception:
        pass
    return tf


def _labeling_left(field="etq", size=9):
    pal = QgsPalLayerSettings()
    pal.fieldName = field
    pal.enabled = True
    pal.setFormat(_text_format_white(size))
    # Etiqueta a la izquierda del punto, sin superponerse.
    try:
        pal.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
        pal.predefinedPositionOrder = [
            QgsPalLayerSettings.MiddleLeft,
            QgsPalLayerSettings.TopLeft,
            QgsPalLayerSettings.BottomLeft,
        ]
        pal.dist = 2
    except Exception:
        try:
            pal.placement = QgsPalLayerSettings.AroundPoint
            pal.dist = 2
        except Exception:
            pass
    return QgsVectorLayerSimpleLabeling(pal)


def make_points_layer(points, name="Puntos dictamen"):
    """Crea una capa de puntos en memoria con simbología por tipo y etiquetas a la izquierda."""
    layer = QgsVectorLayer(f"Point?crs={CRTM05}", name, "memory")
    provider = layer.dataProvider()
    fields = QgsFields()
    for fname in ("nombre", "tipo", "numero", "rol", "etq", "x", "y"):
        fields.append(QgsField(fname, QVariant.String))
    provider.addAttributes(fields)
    layer.updateFields()
    feats = []
    for p in points:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(p["x"], p["y"])))
        f.setAttributes([
            p.get("nombre", ""), p.get("tipo", ""), p.get("numero", ""),
            p.get("rol", ""), p.get("etq", ""),
            f"{p['x']:.0f}", f"{p['y']:.0f}",
        ])
        feats.append(f)
    provider.addFeatures(feats)
    layer.updateExtents()
    _apply_source_symbology(layer)
    layer.setLabeling(_labeling_left())
    layer.setLabelsEnabled(True)
    return layer


def _marker(name, color, size, outline=None, outline_w="0.4"):
    return QgsMarkerSymbol.createSimple({
        "name": name,
        "color": color,
        "outline_color": outline or color,
        "outline_width": outline_w,
        "size": str(size),
    })


def _apply_source_symbology(layer):
    line_list = "'" + "','".join(_LINE_TYPES) + "'"
    root = QgsRuleBasedRenderer.Rule(None)

    def add(expr, symbol, label):
        rule = QgsRuleBasedRenderer.Rule(symbol)
        if expr:
            rule.setFilterExpression(expr)
        rule.setLabel(label)
        root.appendChild(rule)

    # Ríos/quebradas: cruz; inicio verde, final verde oscuro.
    add(f""" "tipo" IN ({line_list}) AND "rol"='Inicio' """,
        _marker("cross", "0,170,0", 4, outline_w="0.8"), "Río/Quebrada inicio")
    add(f""" "tipo" IN ({line_list}) AND "rol"='Final' """,
        _marker("cross", "0,90,0", 4, outline_w="0.8"), "Río/Quebrada final")
    # Puntos de control: círculo rojo tamaño 2.
    add(""" "rol"='Control' """, _marker("circle", "230,30,30", 2, outline="255,255,255"), "Control")
    # Resto (naciente / fuentes puntuales): círculo azul tamaño 3.
    else_rule = QgsRuleBasedRenderer.Rule(_marker("circle", "0,90,220", 3, outline="255,255,255"))
    else_rule.setFilterExpression("ELSE")
    else_rule.setLabel("Naciente / puntual")
    root.appendChild(else_rule)

    layer.setRenderer(QgsRuleBasedRenderer(root))


def _load_river(plugin_dir: str):
    path = os.path.join(plugin_dir, "assets", "layers", RIVER_FILE)
    if not os.path.exists(path):
        return None
    layer = QgsVectorLayer(path, "Red hídrica", "ogr")
    if not layer.isValid():
        return None
    layer.setCrs(QgsCoordinateReferenceSystem(CRTM05))
    try:
        symbol = QgsLineSymbol.createSimple({"color": "70,130,220,255", "width": "0.3"})
        layer.renderer().setSymbol(symbol)
    except Exception:
        pass
    _apply_river_labeling(layer)
    return layer


def _apply_river_labeling(layer):
    """Etiqueta el río con NOMBRE, sobre la línea, azul e itálica."""
    try:
        pal = QgsPalLayerSettings()
        pal.fieldName = "NOMBRE"
        pal.enabled = True
        tf = QgsTextFormat()
        tf.setSize(7)
        tf.setColor(QColor(20, 70, 200))
        font = QFont("Arial")
        font.setItalic(True)
        tf.setFont(font)
        pal.setFormat(tf)
        try:
            pal.placement = QgsPalLayerSettings.Line
            pal.placementFlags = (
                QgsPalLayerSettings.OnLine | QgsPalLayerSettings.MapOrientation
            )
        except Exception:
            try:
                pal.placement = QgsPalLayerSettings.Curved
            except Exception:
                pass
        try:
            pal.setFormat(tf)
        except Exception:
            pass
        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.setLabelsEnabled(True)
    except Exception:
        pass


def _extent(points):
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    span = max(maxx - minx, maxy - miny)
    if span < 50:
        span = 500.0
    margin = span * 0.35
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    half = (span / 2.0) + margin
    return QgsRectangle(cx - half, cy - half, cx + half, cy + half)


_NICE_SCALES = [500, 1000, 2000, 2500, 5000, 7500, 10000, 15000, 20000,
                25000, 50000, 75000, 100000, 200000, 500000]


def _round_scale_up(scale: float) -> float:
    """Devuelve la escala 'cerrada' inmediata igual o mayor que la calculada."""
    for s in _NICE_SCALES:
        if s >= scale:
            return float(s)
    import math
    return float(math.ceil(scale / 100000.0) * 100000)


def build_reference_map(iface, plugin_dir: str, snapshot: dict, out_png_path: str,
                        extra_layer_ids=None) -> str:
    points = collect_map_points(snapshot)
    if not points:
        raise ValueError("No hay coordenadas para dibujar el mapa.")

    project = QgsProject.instance()
    base = QgsRasterLayer(GOOGLE_HYBRID_URI, "Google Híbrido", "wms")
    if not base.isValid():
        raise RuntimeError("No se pudo cargar el fondo Google Híbrido (¿hay internet?).")
    pts_layer = make_points_layer(points)
    river = _load_river(plugin_dir)

    # Capas extra elegidas por el usuario (ya existen en el proyecto: no se quitan).
    extra_layers = []
    for lid in (extra_layer_ids or []):
        lyr = project.mapLayer(lid)
        if lyr is not None:
            extra_layers.append(lyr)

    added = []
    project.addMapLayer(base, False)
    added.append(base.id())
    project.addMapLayer(pts_layer, False)
    added.append(pts_layer.id())
    if river is not None:
        project.addMapLayer(river, False)
        added.append(river.id())
    try:
        layout = QgsLayout(project)
        layout.initializeDefaults()
        page = layout.pageCollection().pages()[0]
        page.setPageSize(QgsLayoutSize(180, 120, QgsUnitTypes.LayoutMillimeters))

        map_item = QgsLayoutItemMap(layout)
        map_item.attemptMove(QgsLayoutPoint(13, 8, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(154, 100, QgsUnitTypes.LayoutMillimeters))
        map_item.setCrs(QgsCoordinateReferenceSystem(CRTM05))
        stack = [pts_layer] + extra_layers
        if river is not None:
            stack.append(river)
        stack.append(base)
        map_item.setLayers(stack)
        map_item.setExtent(_extent(points))
        # Escala en número cerrado; al redondear hacia arriba la ventana crece,
        # así que siempre sigue cubriendo todos los puntos.
        try:
            map_item.refresh()
            map_item.setScale(_round_scale_up(map_item.scale()))
        except Exception:
            pass
        map_item.setFrameEnabled(True)
        layout.addLayoutItem(map_item)

        _configure_grid(map_item, map_item.extent())
        _add_scalebar(layout, map_item)
        _add_north(layout)
        _add_legend(layout, map_item)

        exporter = QgsLayoutExporter(layout)
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 200
        result = exporter.exportToImage(out_png_path, settings)
        if result != QgsLayoutExporter.Success:
            raise RuntimeError("Falló la exportación del mapa a PNG (código %s)." % result)
        return out_png_path
    finally:
        for lid in added:
            project.removeMapLayer(lid)


def _add_legend(layout, map_item):
    """Pequeña leyenda con la simbología de las capas activas del mapa."""
    try:
        from qgis.core import QgsLayoutItemLegend, QgsLegendStyle
        legend = QgsLayoutItemLegend(layout)
        legend.setLinkedMap(map_item)
        legend.setTitle("Simbología")
        try:
            legend.setAutoUpdateModel(True)
        except Exception:
            pass
        try:
            legend.setStyleFont(QgsLegendStyle.Title, QFont("Arial", 8, QFont.Bold))
            legend.setStyleFont(QgsLegendStyle.SymbolLabel, QFont("Arial", 7))
            legend.setSymbolHeight(2.5)
            legend.setSymbolWidth(4)
        except Exception:
            pass
        try:
            legend.setBackgroundEnabled(True)
            legend.setBackgroundColor(QColor(255, 255, 255, 220))
            legend.setFrameEnabled(True)
        except Exception:
            pass
        legend.attemptMove(QgsLayoutPoint(15, 10, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(legend)
    except Exception:
        pass


def _configure_grid(map_item, extent):
    interval = _nice_grid_interval(extent.width())
    grid = map_item.grid()
    grid.setEnabled(True)
    grid.setCrs(QgsCoordinateReferenceSystem(CRTM05))
    grid.setIntervalX(interval)
    grid.setIntervalY(interval)
    grid.setStyle(QgsLayoutItemMapGrid.FrameAnnotationsOnly)
    grid.setFrameStyle(QgsLayoutItemMapGrid.ExteriorTicks)
    grid.setFrameWidth(1.5)
    grid.setAnnotationEnabled(True)
    grid.setAnnotationPrecision(0)
    for border in (
        QgsLayoutItemMapGrid.Left, QgsLayoutItemMapGrid.Right,
        QgsLayoutItemMapGrid.Top, QgsLayoutItemMapGrid.Bottom,
    ):
        try:
            grid.setAnnotationDisplay(QgsLayoutItemMapGrid.ShowAll, border)
            grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, border)
            grid.setAnnotationDirection(QgsLayoutItemMapGrid.Horizontal, border)
        except Exception:
            pass
    try:
        grid.setAnnotationFont(QFont("Arial", 7))
    except Exception:
        pass


def _add_scalebar(layout, map_item):
    try:
        bar = QgsLayoutItemScaleBar(layout)
        bar.setStyle("Single Box")
        bar.setLinkedMap(map_item)
        bar.setUnits(QgsUnitTypes.DistanceMeters)
        bar.applyDefaultSize()
        try:
            bar.setUnitLabel("m")
        except Exception:
            pass
        bar.attemptMove(QgsLayoutPoint(15, 101, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(bar)
    except Exception:
        pass


def _add_north(layout):
    try:
        arrow = QgsLayoutItemLabel(layout)
        arrow.setText("N\n↑")
        f = QFont("Arial")
        f.setPointSize(13)
        f.setBold(True)
        arrow.setFont(f)
        arrow.attemptMove(QgsLayoutPoint(158, 10, QgsUnitTypes.LayoutMillimeters))
        arrow.attemptResize(QgsLayoutSize(10, 14, QgsUnitTypes.LayoutMillimeters))
        try:
            from qgis.PyQt.QtCore import Qt
            arrow.setHAlign(Qt.AlignHCenter)
        except Exception:
            pass
        layout.addLayoutItem(arrow)
    except Exception:
        pass


def make_capture_layer(name="Puntos capturados (Dictámenes-DA)"):
    """Capa en memoria para marcar en vivo cada captura: esfera roja tamaño 2, etiqueta blanca."""
    layer = QgsVectorLayer(f"Point?crs={CRTM05}", name, "memory")
    provider = layer.dataProvider()
    fields = QgsFields()
    fields.append(QgsField("etq", QVariant.String))
    provider.addAttributes(fields)
    layer.updateFields()
    try:
        layer.renderer().setSymbol(_marker("circle", "230,30,30", 2, outline="255,255,255"))
    except Exception:
        pass
    layer.setLabeling(_labeling_left("etq", 8))
    layer.setLabelsEnabled(True)
    return layer
