# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unicodedata

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorLayer,
)


class EmbeddedLayerManager:
    """Carga y consulta las capas GeoJSON integradas del HTML original."""

    LAYER_FILES = {
        "distritocantonprovincia": "distritocantonprovincia.geojson",
        "cuencas": "cuencas.geojson",
        "hojacartografica": "hojacartografica.geojson",
        "indice_hojas": "indice_hojas.geojson",
        "suelos": "suelos.geojson",
    }

    KNOWN_CRS = {
        "distritocantonprovincia": "EPSG:5367",
        "cuencas": "EPSG:5367",
        "hojacartografica": "EPSG:5367",
        "indice_hojas": "EPSG:4326",
        "suelos": "EPSG:5367",
    }

    def __init__(self, plugin_dir: str):
        self.plugin_dir = plugin_dir
        self.layers = {}
        self.indexes = {}
        self._last_errors = []

    def _path(self, key: str) -> str:
        return os.path.join(self.plugin_dir, "assets", "layers", self.LAYER_FILES[key])

    def load_layer(self, key: str):
        if key in self.layers:
            return self.layers[key]
        path = self._path(key)
        layer = QgsVectorLayer(path, key, "ogr")
        if not layer.isValid():
            self._last_errors.append(f"No se pudo abrir {self.LAYER_FILES[key]}")
            return None

        # En el HTML, todas las capas salvo indice_hojas se tratan como CRTM05.
        # Forzar CRS evita diferencias por EPSG:8908 o GeoJSON sin CRS.
        layer.setCrs(QgsCoordinateReferenceSystem(self.KNOWN_CRS[key]))
        self.layers[key] = layer
        self.indexes[key] = QgsSpatialIndex(layer.getFeatures())
        return layer

    def load_all(self):
        for key in self.LAYER_FILES:
            self.load_layer(key)
        return self.status_lines()

    def status_lines(self):
        lines = []
        for key, filename in self.LAYER_FILES.items():
            layer = self.layers.get(key)
            if layer and layer.isValid():
                lines.append(f"✓ {filename}: {layer.featureCount()} geometrías")
            else:
                lines.append(f"⚠ {filename}: no cargada")
        return lines + self._last_errors

    def transform_xy(self, x, y, src_authid: str, dst_authid: str) -> QgsPointXY:
        src = QgsCoordinateReferenceSystem(src_authid)
        dst = QgsCoordinateReferenceSystem(dst_authid)
        point = QgsPointXY(float(x), float(y))
        if src == dst:
            return point
        tr = QgsCoordinateTransform(src, dst, QgsProject.instance())
        return tr.transform(point)

    def to_crtm(self, x, y, input_authid: str) -> QgsPointXY:
        return self.transform_xy(x, y, input_authid, "EPSG:5367")

    def to_lambert(self, x, y, input_authid: str = "EPSG:5367") -> QgsPointXY:
        return self.transform_xy(x, y, input_authid, "EPSG:5456")

    @staticmethod
    def _norm(text):
        text = "" if text is None else str(text)
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return text.lower().replace("_", "").replace(" ", "")

    def _attr(self, feat, *names):
        fields = feat.fields()
        wanted = {self._norm(n) for n in names}
        for field in fields:
            if self._norm(field.name()) in wanted:
                val = feat[field.name()]
                return "" if val is None else str(val)
        return ""

    def containing_feature(self, key: str, crtm_point: QgsPointXY):
        layer = self.load_layer(key)
        if not layer:
            return None

        known_auth = self.KNOWN_CRS.get(key, "EPSG:5367")
        if known_auth == "EPSG:5367":
            test_point = crtm_point
        else:
            test_point = self.transform_xy(crtm_point.x(), crtm_point.y(), "EPSG:5367", known_auth)

        geom = QgsGeometry.fromPointXY(test_point)
        index = self.indexes.get(key)
        candidate_ids = index.intersects(geom.boundingBox()) if index else []
        for fid in candidate_ids:
            request = QgsFeatureRequest(fid)
            for feat in layer.getFeatures(request):
                fgeom = feat.geometry()
                if fgeom and fgeom.intersects(geom):
                    return feat
        return None

    def spatial_for(self, start_record, end_record) -> dict:
        sp = {
            "provincia": "", "canton": "", "distrito": "",
            "hoja50": "", "codigo50": "", "hoja_cartografica": "",
            "cuenca_numero": "", "cuenca_nombre": "",
            "orden_suelo": "", "warning": "",
        }
        if not start_record and not end_record:
            return sp

        if start_record and end_record:
            crtm = QgsPointXY(
                (float(start_record["crtmX"]) + float(end_record["crtmX"])) / 2.0,
                (float(start_record["crtmY"]) + float(end_record["crtmY"])) / 2.0,
            )
        else:
            record = start_record or end_record
            crtm = QgsPointXY(float(record["crtmX"]), float(record["crtmY"]))

        feat = self.containing_feature("distritocantonprovincia", crtm)
        if feat:
            sp["provincia"] = self._attr(feat, "PROVINCIA")
            sp["canton"] = self._attr(feat, "CANTÓN", "CANTON")
            sp["distrito"] = self._attr(feat, "DISTRITO")

        feat = self.containing_feature("cuencas", crtm)
        if feat:
            sp["cuenca_numero"] = self._attr(feat, "Numero", "Cuenca_Num", "CUENCA_NUM")
            sp["cuenca_nombre"] = self._attr(feat, "Nombre", "NOMBRE")

        feat = self.containing_feature("hojacartografica", crtm)
        if feat:
            sp["hoja50"] = self._attr(feat, "hoja_50", "nombre")
            sp["codigo50"] = self._attr(feat, "codigo_50")
        if not sp["hoja50"]:
            feat = self.containing_feature("indice_hojas", crtm)
            if feat:
                sp["hoja50"] = self._attr(feat, "hoja_50", "nombre")
                sp["codigo50"] = self._attr(feat, "codigo_50")
        if sp["hoja50"] or sp["codigo50"]:
            sp["hoja_cartografica"] = (sp["hoja50"] + " / " + sp["codigo50"]).strip(" /")

        feat = self.containing_feature("suelos", crtm)
        if feat:
            sp["orden_suelo"] = self._attr(feat, "CARAC_TERR", "carac_terr")

        if start_record and end_record:
            start_pt = QgsPointXY(float(start_record["crtmX"]), float(start_record["crtmY"]))
            end_pt = QgsPointXY(float(end_record["crtmX"]), float(end_record["crtmY"]))
            fs = self.containing_feature("distritocantonprovincia", start_pt)
            fe = self.containing_feature("distritocantonprovincia", end_pt)
            ds = self._attr(fs, "DISTRITO") if fs else ""
            de = self._attr(fe, "DISTRITO") if fe else ""
            if ds and de and ds != de:
                sp["warning"] = "El punto inicial y final caen en distritos diferentes."
        return sp
