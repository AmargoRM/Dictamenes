# -*- coding: utf-8 -*-
"""Generación del mapa de referencia (Figura 1) para el dictamen.

Arma un layout de QGIS con:
- Fondo Google Satélite Híbrido (XYZ, requiere internet).
- Cuadrícula CRTM05 (EPSG:5367) mostrada SOLO como marcas externas (ticks) y
  etiquetas de coordenadas en el borde; sin líneas cruzando el mapa.
- Puntos de las fuentes (Inicio/Final) y puntos de control.
- Título con los nombres de las fuentes, escala gráfica y flecha de norte.
- Exporta a PNG de aproximadamente media página.

Todo debe correr en el HILO PRINCIPAL de QGIS (no en un QgsTask), porque el
render y la descarga de tiles no son seguros fuera del hilo principal.
"""
from __future__ import annotations

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor

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
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
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

# Intervalos "bonitos" de cuadrícula, en metros.
_NICE_INTERVALS = [50, 100, 250, 500, 1000, 2000, 5000, 10000, 25000, 50000]


def _nice_grid_interval(width_m: float) -> float:
    """Elige un intervalo de cuadrícula para tener ~4-6 líneas a lo ancho."""
    if width_m <= 0:
        return 1000.0
    target = width_m / 5.0
    for value in _NICE_INTERVALS:
        if value >= target:
            return float(value)
    return float(_NICE_INTERVALS[-1])


def _collect_points(snapshot: dict):
    """Devuelve [(crtmX, crtmY, etiqueta, es_final), ...] transformando en el hilo principal."""
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
        if transform is not None:
            pt = transform.transform(pt)
        return pt

    points = []
    for idx, src in enumerate(snapshot.get("sources", []), start=1):
        num = (src.get("numero_fuente") or str(idx)).strip()
        for key_x, key_y, key_n, role in (
            ("start_x", "start_y", "start_number", src.get("start_label") or "Inicio"),
            ("end_x", "end_y", "end_number", src.get("end_label") or "Final"),
        ):
            if not str(src.get(key_x, "")).strip() or not str(src.get(key_y, "")).strip():
                continue
            pt = to_crtm(src.get(key_x), src.get(key_y))
            if pt is None:
                continue
            pnum = (src.get(key_n) or "").strip()
            etq = f"P{pnum} {role}".strip() if pnum else f"F{num} {role}"
            points.append((pt.x(), pt.y(), etq, role.lower().startswith("f")))
    for row, cp in enumerate(snapshot.get("control_points", []), start=1):
        if not str(cp.get("x", "")).strip() or not str(cp.get("y", "")).strip():
            continue
        pt = to_crtm(cp.get("x"), cp.get("y"))
        if pt is None:
            continue
        etq = (cp.get("label") or f"Control {row}").strip()
        points.append((pt.x(), pt.y(), etq, False))
    return points


def _source_title(snapshot: dict) -> str:
    nombres = []
    for src in snapshot.get("sources", []):
        nombre = (src.get("nombre_fuente") or "").strip()
        tipo = (src.get("tipo_fuente") or "").strip()
        etq = nombre or tipo
        if etq and etq not in nombres:
            nombres.append(etq)
    if not nombres:
        return "Mapa de ubicación de la zona de estudio"
    return " y ".join(nombres) if len(nombres) <= 3 else ", ".join(nombres)


def _points_layer(points):
    layer = QgsVectorLayer(f"Point?crs={CRTM05}", "puntos_dictamen", "memory")
    provider = layer.dataProvider()
    fields = QgsFields()
    fields.append(QgsField("etq", QVariant.String))
    fields.append(QgsField("final", QVariant.Int))
    provider.addAttributes(fields)
    layer.updateFields()
    feats = []
    for x, y, etq, es_final in points:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        f.setAttributes([etq, 1 if es_final else 0])
        feats.append(f)
    provider.addFeatures(feats)
    layer.updateExtents()

    symbol = QgsMarkerSymbol.createSimple({
        "name": "circle",
        "color": "255,45,45,255",
        "outline_color": "255,255,255,255",
        "outline_width": "0.4",
        "size": "3",
    })
    layer.renderer().setSymbol(symbol)

    pal = QgsPalLayerSettings()
    pal.fieldName = "etq"
    pal.enabled = True
    text_format = QgsTextFormat()
    text_format.setSize(9)
    try:
        buf = text_format.buffer()
        buf.setEnabled(True)
        buf.setSize(1)
        buf.setColor(QColor(0, 0, 0))
        text_format.setBuffer(buf)
        text_format.setColor(QColor(255, 255, 255))
    except Exception:
        pass
    pal.setFormat(text_format)
    try:
        pal.placement = QgsPalLayerSettings.OverPoint
        pal.dist = 2
    except Exception:
        pass
    layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    layer.setLabelsEnabled(True)
    return layer


def _extent_and_scale(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    width = maxx - minx
    height = maxy - miny
    span = max(width, height)
    if span < 50:  # un solo punto o muy juntos: ventana de 500 m
        span = 500.0
    margin = span * 0.35
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    half = (span / 2.0) + margin
    extent = QgsRectangle(cx - half, cy - half, cx + half, cy + half)
    return extent


def build_reference_map(iface, plugin_dir: str, snapshot: dict, out_png_path: str) -> str:
    """Construye el mapa y lo exporta a PNG. Devuelve la ruta o lanza excepción."""
    points = _collect_points(snapshot)
    if not points:
        raise ValueError("No hay coordenadas para dibujar el mapa.")

    project = QgsProject.instance()
    base = QgsRasterLayer(GOOGLE_HYBRID_URI, "Google Híbrido", "wms")
    if not base.isValid():
        raise RuntimeError("No se pudo cargar el fondo Google Híbrido (¿hay internet?).")
    pts_layer = _points_layer(points)

    # Registrar temporalmente en el proyecto para que el layout los renderice.
    project.addMapLayer(base, False)
    project.addMapLayer(pts_layer, False)
    added = [base.id(), pts_layer.id()]
    try:
        layout = QgsLayout(project)
        layout.initializeDefaults()
        page = layout.pageCollection().pages()[0]
        page.setPageSize(QgsLayoutSize(180, 125, QgsUnitTypes.LayoutMillimeters))

        title = QgsLayoutItemLabel(layout)
        title.setText(_source_title(snapshot))
        title.setFont(_bold_font(12))
        title.attemptMove(QgsLayoutPoint(0, 3, QgsUnitTypes.LayoutMillimeters))
        title.attemptResize(QgsLayoutSize(180, 9, QgsUnitTypes.LayoutMillimeters))
        try:
            from qgis.PyQt.QtCore import Qt
            title.setHAlign(Qt.AlignHCenter)
        except Exception:
            pass
        layout.addLayoutItem(title)

        map_item = QgsLayoutItemMap(layout)
        map_item.attemptMove(QgsLayoutPoint(13, 14, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(154, 100, QgsUnitTypes.LayoutMillimeters))
        map_item.setCrs(QgsCoordinateReferenceSystem(CRTM05))
        map_item.setLayers([pts_layer, base])
        extent = _extent_and_scale(points)
        map_item.setExtent(extent)
        map_item.setFrameEnabled(True)
        layout.addLayoutItem(map_item)

        _configure_grid(map_item, extent)

        _add_scalebar(layout, map_item)
        _add_north(layout)

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


def _bold_font(size):
    from qgis.PyQt.QtGui import QFont
    f = QFont()
    f.setPointSize(size)
    f.setBold(True)
    return f


def _configure_grid(map_item, extent):
    interval = _nice_grid_interval(extent.width())
    grid = map_item.grid()
    grid.setEnabled(True)
    grid.setCrs(QgsCoordinateReferenceSystem(CRTM05))
    grid.setIntervalX(interval)
    grid.setIntervalY(interval)
    # Solo marcas externas: no dibujar líneas dentro del mapa.
    grid.setStyle(QgsLayoutItemMapGrid.FrameAnnotationsOnly)
    grid.setFrameStyle(QgsLayoutItemMapGrid.ExteriorTicks)
    grid.setFrameWidth(1.5)
    grid.setAnnotationEnabled(True)
    grid.setAnnotationPrecision(0)
    try:
        grid.setAnnotationFormat(QgsLayoutItemMapGrid.DecimalWithSuffix)
    except Exception:
        pass
    for border in (
        QgsLayoutItemMapGrid.Left,
        QgsLayoutItemMapGrid.Right,
        QgsLayoutItemMapGrid.Top,
        QgsLayoutItemMapGrid.Bottom,
    ):
        try:
            grid.setAnnotationDisplay(QgsLayoutItemMapGrid.ShowAll, border)
            grid.setAnnotationPosition(QgsLayoutItemMapGrid.OutsideMapFrame, border)
        except Exception:
            pass
    try:
        grid.setAnnotationDirection(QgsLayoutItemMapGrid.Horizontal, QgsLayoutItemMapGrid.Left)
        grid.setAnnotationDirection(QgsLayoutItemMapGrid.Horizontal, QgsLayoutItemMapGrid.Right)
        grid.setAnnotationDirection(QgsLayoutItemMapGrid.Horizontal, QgsLayoutItemMapGrid.Top)
        grid.setAnnotationDirection(QgsLayoutItemMapGrid.Horizontal, QgsLayoutItemMapGrid.Bottom)
    except Exception:
        pass
    try:
        from qgis.PyQt.QtGui import QFont
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
        bar.attemptMove(QgsLayoutPoint(15, 108, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(bar)
    except Exception:
        pass


def _add_north(layout):
    """Flecha de norte simple usando una etiqueta con una flecha unicode."""
    try:
        arrow = QgsLayoutItemLabel(layout)
        arrow.setText("N\n↑")
        from qgis.PyQt.QtGui import QFont
        f = QFont("Arial")
        f.setPointSize(13)
        f.setBold(True)
        arrow.setFont(f)
        arrow.attemptMove(QgsLayoutPoint(158, 16, QgsUnitTypes.LayoutMillimeters))
        arrow.attemptResize(QgsLayoutSize(10, 14, QgsUnitTypes.LayoutMillimeters))
        try:
            from qgis.PyQt.QtCore import Qt
            arrow.setHAlign(Qt.AlignHCenter)
        except Exception:
            pass
        layout.addLayoutItem(arrow)
    except Exception:
        pass
