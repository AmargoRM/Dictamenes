# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import traceback

from qgis.PyQt.QtCore import Qt, pyqtSignal, QDate, QTimer
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
    QgsTask,
)

from .docx_builder import write_docx
from .layer_manager import EmbeddedLayerManager
from .map_tool import DictamenMapClickTool


SOURCE_TYPES = [
    "", "Naciente", "Quebrada", "Río", "Lago / Laguna", "Océano / Mar", "Canal",
    "Depresión Natural", "Pozo / galería / afloramiento provocado / mina / túnel / embalse",
    "No hay cuerpo de agua", "Otro",
]

CRITERIA = [
    "",
    "Cuerpo de agua del dominio público de carácter permanente",
    "Cuerpo de agua del dominio público de carácter intermitente",
    "Cuerpo de agua que no corresponde al dominio público",
    "No aplica",
    "Estructura antrópica / criterio técnico especial",
]

DESCRIPTION_LIBRARY = {
    "Naciente": [
        "El cuerpo de agua presenta un afloramiento puntual y claramente definido, donde el agua emerge de un único punto identificable.",
        "El cuerpo de agua presenta afloramientos múltiples o dispersos, con surgencias de agua en varios puntos próximos entre sí que conforman una misma naciente.",
        "A partir de la naciente se desarrolla un cauce superficial definido, con flujo continuo y márgenes identificables.",
        "El cauce asociado presenta lecho con presencia de roca, grava, cantos o material aluvial, evidenciando un cauce natural.",
        "La naciente da origen a un cuerpo de agua tipo quebrada aguas abajo.",
        "Se identifica vegetación hidrófila característica de ambientes acuáticos o semiacuáticos en el entorno inmediato de la naciente.",
        "Se identifica bosque de galería asociado al cauce o al área de influencia de la naciente.",
        "Se observan evidencias de intervención antrópica en el entorno inmediato de la naciente.",
    ],
    "Río / Quebrada": [
        "Cuerpo de agua con flujo evidente y medible de agua, presencia de cauce definido.",
        "El cauce asociado presenta lecho con presencia de roca, grava, cantos o material aluvial, evidenciando un cauce natural.",
        "Se identifica vegetación hidrófila característica de ambientes acuáticos o semiacuáticos en el entorno inmediato del río o quebrada.",
        "Se identifica bosque de galería asociado al cauce.",
        "Cuerpo de agua que se origina a partir de la incorporación de flujos base y/o aportes laterales identificados en su sección inicial.",
        "Se identifica una conformación de cauce tipo meándrico.",
        "Se identifica una conformación de cauce tipo anastomosado.",
    ],
    "Depresión Natural": [
        "El cuerpo de agua presenta secciones de flujo amplias, con velocidades de agua lentas, lo que favorece la proliferación de vegetación hidrófila en su superficie.",
        "Se identifica vegetación hidrófila asociada a medios acuáticos o semiacuáticos.",
        "El cuerpo de agua presenta características atribuibles a ecosistemas de humedal, por lo que se recomienda solicitar el respectivo criterio al Sistema Nacional de Áreas de Conservación.",
        "Se identifica una cárcava sin flujo de agua, originada por la acción erosiva del agua de escorrentía, la cual en función de la pendiente de la zona converge hasta el sitio evaluado.",
    ],
    "Canal": [
        "Se identifica un canal excavado en el suelo sin ningún tipo de recubrimiento, el cual muestra sección transversal uniforme y recorrido rectilíneo, característico de estructuras artificiales.",
        "No corresponde a un cuerpo de agua del dominio público, sino a una estructura antrópica diseñada para la evacuación o transporte de agua.",
    ],
}


def source_library_key(source_type: str):
    if source_type == "Naciente":
        return "Naciente"
    if source_type in ("Río", "Quebrada"):
        return "Río / Quebrada"
    if source_type == "Depresión Natural":
        return "Depresión Natural"
    if source_type == "Canal":
        return "Canal"
    return None




def _line(text="", placeholder=""):
    w = QLineEdit()
    w.setText(text or "")
    if placeholder:
        w.setPlaceholderText(placeholder)
    w.setMinimumWidth(0)
    return w


class DateEdit(QDateEdit):
    """Fecha con calendario emergente y valor vacío real para el formulario.

    QDateEdit usa la fecha mínima para representar un campo vacío. Si se deja
    así sin ajuste, el calendario abre en 1900/1990 y obliga a navegar décadas.
    Esta clase mantiene el valor vacío, pero al abrir el calendario mueve la
    vista al mes vigente.
    """

    EMPTY_DATE = QDate(1900, 1, 1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDisplayFormat("dd/MM/yy")
        self.setCalendarPopup(True)
        self.setMinimumDate(self.EMPTY_DATE)
        self.setSpecialValueText(" ")
        self.setDate(self.EMPTY_DATE)
        self.setMinimumWidth(0)
        calendar = self.calendarWidget()
        if calendar:
            today = QDate.currentDate()
            calendar.setCurrentPage(today.year(), today.month())

    def _move_popup_to_current_month(self):
        if self.date() != self.EMPTY_DATE:
            return
        calendar = self.calendarWidget()
        if not calendar:
            return
        today = QDate.currentDate()
        calendar.setCurrentPage(today.year(), today.month())

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        QTimer.singleShot(0, self._move_popup_to_current_month)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        QTimer.singleShot(0, self._move_popup_to_current_month)

    def clear(self):
        self.setDate(self.EMPTY_DATE)
        self._move_popup_to_current_month()

    def iso_value(self) -> str:
        if self.date() == self.EMPTY_DATE:
            return ""
        return self.date().toString("yyyy-MM-dd")

    def set_iso_value(self, value: str):
        if not value:
            self.clear()
            return
        qd = QDate.fromString(value, "yyyy-MM-dd")
        if qd.isValid():
            self.setDate(qd)
        else:
            self.clear()


def _date():
    return DateEdit()


class SourceCard(QGroupBox):
    capture_requested = pyqtSignal(object, object, str)

    def __init__(self, index: int, parent=None):
        super().__init__(f"Fuente {index}", parent)
        self.index = index
        self.description_checks = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.numero = _line(str(self.index))
        self.fecha_eval = _date()
        self.epoca = QComboBox()
        self.epoca.addItems(["", "seca", "lluviosa", "transición"])
        self.tipo = QComboBox()
        self.tipo.addItems(SOURCE_TYPES)
        self.nombre = _line()
        self.criterio = QComboBox()
        self.criterio.addItems(CRITERIA)
        self.afluente = _line()
        form.addRow("N. fuente", self.numero)
        form.addRow("Fecha eval.", self.fecha_eval)
        form.addRow("Época", self.epoca)
        form.addRow("Tipo", self.tipo)
        form.addRow("Nombre", self.nombre)
        form.addRow("Criterio", self.criterio)
        form.addRow("Afluente", self.afluente)
        root.addLayout(form)

        coords = QGroupBox("Coordenadas")
        coords_layout = QVBoxLayout(coords)
        coords_layout.setContentsMargins(8, 8, 8, 8)
        self.start_label = _line("Inicio")
        self.start_number = _line("", f"Ej. {self.index * 2 - 1}")
        self.start_x = _line()
        self.start_y = _line()
        self.btn_capture_start = QPushButton("Capturar inicio")

        self.end_label = _line("Final")
        self.end_number = _line("", f"Ej. {self.index * 2}")
        self.end_x = _line()
        self.end_y = _line()
        self.btn_capture_end = QPushButton("Capturar final")

        coords_layout.addWidget(QLabel("Inicio"))
        coords_layout.addLayout(self._coord_pair_layout(self.start_label, self.start_number, "Etiqueta", "Punto"))
        coords_layout.addLayout(self._coord_pair_layout(self.start_x, self.start_y, "X / Este / Long.", "Y / Norte / Lat."))
        coords_layout.addWidget(self.btn_capture_start)
        coords_layout.addWidget(QLabel("Final"))
        coords_layout.addLayout(self._coord_pair_layout(self.end_label, self.end_number, "Etiqueta", "Punto"))
        coords_layout.addLayout(self._coord_pair_layout(self.end_x, self.end_y, "X / Este / Long.", "Y / Norte / Lat."))
        coords_layout.addWidget(self.btn_capture_end)
        root.addWidget(coords)

        self.desc_box = QGroupBox("Descripciones técnicas")
        self.desc_layout = QVBoxLayout(self.desc_box)
        root.addWidget(self.desc_box)

        self.observaciones = QTextEdit()
        self.observaciones.setMinimumHeight(58)
        root.addWidget(QLabel("Observaciones adicionales"))
        root.addWidget(self.observaciones)

        self.btn_capture_start.clicked.connect(
            lambda: self.capture_requested.emit(self.start_x, self.start_y, f"Fuente {self.index} - Inicio")
        )
        self.btn_capture_end.clicked.connect(
            lambda: self.capture_requested.emit(self.end_x, self.end_y, f"Fuente {self.index} - Final")
        )
        self.tipo.currentTextChanged.connect(self._refresh_descriptions)
        self._refresh_descriptions()

    def _coord_pair_layout(self, a_widget, b_widget, a_label, b_label):
        line = QHBoxLayout()
        left = QVBoxLayout()
        right = QVBoxLayout()
        la = QLabel(a_label)
        lb = QLabel(b_label)
        la.setWordWrap(True)
        lb.setWordWrap(True)
        left.addWidget(la)
        left.addWidget(a_widget)
        right.addWidget(lb)
        right.addWidget(b_widget)
        line.addLayout(left, 1)
        line.addLayout(right, 1)
        return line

    def _refresh_descriptions(self):
        while self.desc_layout.count():
            item = self.desc_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.description_checks = []

        key = source_library_key(self.tipo.currentText())
        phrases = DESCRIPTION_LIBRARY.get(key, [])
        if not phrases:
            label = QLabel("Seleccione un tipo con biblioteca técnica para mostrar descripciones sugeridas.")
            label.setWordWrap(True)
            self.desc_layout.addWidget(label)
            self.description_checks.append(label)
            return

        from qgis.PyQt.QtWidgets import QCheckBox
        for phrase in phrases:
            cb = QCheckBox(phrase)
            cb.setToolTip(phrase)
            self.desc_layout.addWidget(cb)
            self.description_checks.append(cb)

    def values(self):
        return {
            "numero_fuente": self.numero.text().strip(),
            "fecha_evaluacion": self.fecha_eval.iso_value(),
            "epoca_zona": self.epoca.currentText().strip(),
            "tipo_fuente": self.tipo.currentText().strip(),
            "nombre_fuente": self.nombre.text().strip(),
            "criterio_fuente": self.criterio.currentText().strip(),
            "afluente_de": self.afluente.text().strip(),
            "start_label": self.start_label.text().strip() or "Inicio",
            "start_number": self.start_number.text().strip(),
            "start_x": self.start_x.text().strip(),
            "start_y": self.start_y.text().strip(),
            "end_label": self.end_label.text().strip() or "Final",
            "end_number": self.end_number.text().strip(),
            "end_x": self.end_x.text().strip(),
            "end_y": self.end_y.text().strip(),
            "descripciones": [
                cb.text() for cb in self.description_checks
                if hasattr(cb, "isChecked") and cb.isChecked()
            ],
            "observaciones": self.observaciones.toPlainText().strip(),
        }

    def restore(self, v: dict):
        self.numero.setText(v.get("numero_fuente", str(self.index)))
        self.fecha_eval.set_iso_value(v.get("fecha_evaluacion", ""))
        for combo, key in [
            (self.epoca, "epoca_zona"),
            (self.tipo, "tipo_fuente"),
            (self.criterio, "criterio_fuente"),
        ]:
            i = combo.findText(v.get(key, ""))
            if i >= 0:
                combo.setCurrentIndex(i)
        self.nombre.setText(v.get("nombre_fuente", ""))
        self.afluente.setText(v.get("afluente_de", ""))
        self.start_label.setText(v.get("start_label", "Inicio"))
        self.start_number.setText(v.get("start_number", ""))
        self.start_x.setText(v.get("start_x", ""))
        self.start_y.setText(v.get("start_y", ""))
        self.end_label.setText(v.get("end_label", "Final"))
        self.end_number.setText(v.get("end_number", ""))
        self.end_x.setText(v.get("end_x", ""))
        self.end_y.setText(v.get("end_y", ""))
        self.observaciones.setPlainText(v.get("observaciones", ""))
        # Restaurar checkboxes después de que _refresh_descriptions los reconstruyó
        from qgis.PyQt.QtWidgets import QCheckBox
        selected = set(v.get("descripciones", []))
        for cb in self.description_checks:
            if isinstance(cb, QCheckBox):
                cb.setChecked(cb.text() in selected)


def _build_point_record(layer_manager, input_auth, x_text, y_text, label, number, source_number, role, required_name, required=True):
    has_x = bool(str(x_text).strip())
    has_y = bool(str(y_text).strip())
    if not has_x and not has_y:
        if required:
            raise ValueError(f"{required_name} no tiene coordenadas.")
        return None
    if has_x != has_y:
        raise ValueError(f"{required_name} está incompleto: indique X y Y.")
    crtm = layer_manager.to_crtm(float(x_text), float(y_text), input_auth)
    lambert = layer_manager.to_lambert(crtm.x(), crtm.y(), "EPSG:5367")
    return {
        "label": label or role,
        "pointNumber": number or "",
        "sourceNumber": source_number or "",
        "pointRole": role,
        "inputCRS": input_auth,
        "inputX": float(x_text),
        "inputY": float(y_text),
        "crtmX": crtm.x(),
        "crtmY": crtm.y(),
        "lambertX": lambert.x(),
        "lambertY": lambert.y(),
    }


def build_data_from_snapshot(snapshot: dict, layer_manager: EmbeddedLayerManager, do_spatial=True) -> dict:
    data = {
        "input_crs": snapshot.get("input_crs"),
        "oficio": snapshot.get("oficio", ""),
        "fecha_oficio": snapshot.get("fecha_oficio", ""),
        "solicitante": snapshot.get("solicitante", ""),
        "correo": snapshot.get("correo", ""),
        "id_solicitud": snapshot.get("id_solicitud", ""),
        "fecha_inspeccion": snapshot.get("fecha_inspeccion", ""),
        "fecha_evaluacion": snapshot.get("fecha_evaluacion", ""),
        "sitio": snapshot.get("sitio", ""),
        "acompanantes": snapshot.get("acompanantes", ""),
        "profesional_responsable": snapshot.get("profesional_responsable", ""),
        "sources": [],
        "field_points": [],
        "control_points": [],
    }
    if do_spatial:
        layer_manager.load_all()
    input_auth = snapshot.get("input_crs") or "EPSG:5367"

    for idx, raw in enumerate(snapshot.get("sources", []), start=1):
        source_num = raw.get("numero_fuente") or str(idx)
        start = _build_point_record(
            layer_manager, input_auth,
            raw.get("start_x", ""), raw.get("start_y", ""), raw.get("start_label", "Inicio"), raw.get("start_number", ""),
            source_num, "Inicio", f"Fuente {source_num} - Inicio", required=True
        )
        end = _build_point_record(
            layer_manager, input_auth,
            raw.get("end_x", ""), raw.get("end_y", ""), raw.get("end_label", "Final"), raw.get("end_number", ""),
            source_num, "Final", f"Fuente {source_num} - Final", required=False
        )
        spatial = layer_manager.spatial_for(start, end) if do_spatial else {}
        source = {
            **raw,
            "numero_fuente": source_num,
            "point_start": start,
            "point_end": end,
            "field_points": [p for p in (start, end) if p],
            "technical_points": [p for p in (start, end) if p],
            **spatial,
        }
        source["warning"] = spatial.get("warning", "")
        data["sources"].append(source)
        data["field_points"].extend(source["field_points"])

    for row, raw in enumerate(snapshot.get("control_points", []), start=1):
        rec = _build_point_record(
            layer_manager, input_auth,
            raw.get("x", ""), raw.get("y", ""), raw.get("label") or f"Control {row}", raw.get("number", ""),
            "", "Referencia", f"Punto de control {row}", required=False
        )
        if rec:
            data["control_points"].append(rec)
            data["field_points"].append(rec)
    return data


class AnalysisTask(QgsTask):
    def __init__(self, widget, plugin_dir: str, snapshot: dict):
        super().__init__("Dictámenes-DA: análisis espacial", QgsTask.CanCancel)
        self.widget = widget
        self.plugin_dir = plugin_dir
        self.snapshot = snapshot
        self.result_data = None
        self.error_text = ""

    def run(self):
        try:
            manager = EmbeddedLayerManager(self.plugin_dir)
            self.result_data = build_data_from_snapshot(self.snapshot, manager, do_spatial=True)
            return True
        except Exception:
            self.error_text = traceback.format_exc()
            return False

    def finished(self, ok):
        if self.widget:
            self.widget._analysis_finished(self, ok)


class GenerateTask(QgsTask):
    def __init__(self, widget, plugin_dir: str, snapshot: dict, directory: str, analyzed_data=None):
        super().__init__("Dictámenes-DA: generar Word", QgsTask.CanCancel)
        self.widget = widget
        self.plugin_dir = plugin_dir
        self.snapshot = snapshot
        self.directory = directory
        self.analyzed_data = analyzed_data
        self.output_path = ""
        self.error_text = ""

    def run(self):
        try:
            if self.analyzed_data:
                data = self.analyzed_data
            else:
                manager = EmbeddedLayerManager(self.plugin_dir)
                data = build_data_from_snapshot(self.snapshot, manager, do_spatial=True)
            self.output_path = write_docx(data, self.directory, self.plugin_dir)
            return True
        except Exception:
            self.error_text = traceback.format_exc()
            return False

    def finished(self, ok):
        if self.widget:
            self.widget._generate_finished(self, ok)


class DictamenesDADockWidget(QDockWidget):
    def __init__(self, iface, plugin_dir, parent=None):
        super().__init__("Dictámenes-DA", parent)
        self.iface = iface
        self.plugin_dir = plugin_dir
        self.layer_manager = EmbeddedLayerManager(plugin_dir)
        self.map_tool = None
        self.previous_map_tool = None
        self.capture_target = None
        self.source_cards = []
        self.active_tasks = []
        self.last_snapshot_repr = ""
        self.last_analyzed_data = None
        self._restore_source_data = {}
        self._build_ui()

    def _build_ui(self):
        self.setMinimumWidth(360)
        self.setMaximumWidth(470)
        self.resize(420, 720)

        wrapper = QWidget()
        wrapper.setMaximumWidth(440)
        wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        intro = QLabel("Formulario QGIS para dictámenes DA. Use Capturar y luego haga clic sobre el mapa.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        crs_group = QGroupBox("CRS y fuentes")
        crs_form = QFormLayout(crs_group)
        crs_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.input_crs = QComboBox()
        self.input_crs.addItem("CRTM05 (EPSG:5367)", "EPSG:5367")
        self.input_crs.addItem("Lambert Norte (EPSG:5456)", "EPSG:5456")
        self.input_crs.addItem("WGS84 / lon-lat", "EPSG:4326")
        self.source_count = QSpinBox()
        self.source_count.setMinimum(1)
        self.source_count.setMaximum(20)
        self.source_count.setValue(1)
        self.fecha_evaluacion = _date()
        crs_form.addRow("CRS entrada", self.input_crs)
        crs_form.addRow("Fuentes", self.source_count)
        crs_form.addRow("Fecha eval. base", self.fecha_evaluacion)
        layout.addWidget(crs_group)

        self.sources_container = QWidget()
        self.sources_layout = QVBoxLayout(self.sources_container)
        self.sources_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.sources_container)

        control_group = QGroupBox("Puntos de control")
        control_layout = QVBoxLayout(control_group)
        self.control_table = QTableWidget(0, 4)
        self.control_table.setHorizontalHeaderLabels(["Etiqueta", "N.", "X", "Y"])
        self.control_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.control_table.setMinimumHeight(115)
        self.control_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        control_layout.addWidget(self.control_table)

        btns = QGridLayout()
        self.btn_add_control = QPushButton("Agregar")
        self.btn_capture_control = QPushButton("Capturar fila")
        self.btn_remove_control = QPushButton("Quitar")
        btns.addWidget(self.btn_add_control, 0, 0)
        btns.addWidget(self.btn_capture_control, 0, 1)
        btns.addWidget(self.btn_remove_control, 1, 0, 1, 2)
        control_layout.addLayout(btns)
        layout.addWidget(control_group)

        admin = QGroupBox("Datos administrativos")
        form = QFormLayout(admin)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.oficio = _line("", "0123")
        self.fecha_oficio = _date()
        self.solicitante = _line()
        self.correo = _line()
        self.id_solicitud = _line("", "1234-5678")
        self.fecha_inspeccion = _date()
        self.sitio = _line()
        self.acompanantes = _line()
        self.profesional = _line("", "Nombre del profesional")
        form.addRow("Oficio", self.oficio)
        form.addRow("Fecha oficio", self.fecha_oficio)
        form.addRow("Solicitante", self.solicitante)
        form.addRow("Correo", self.correo)
        form.addRow("ID solicitud", self.id_solicitud)
        form.addRow("Fecha inspección", self.fecha_inspeccion)
        form.addRow("Sitio", self.sitio)
        form.addRow("Acompañantes", self.acompanantes)
        form.addRow("Profesional", self.profesional)
        layout.addWidget(admin)

        actions = QGridLayout()
        self.btn_load_layers = QPushButton("Cargar capas")
        self.btn_analyze = QPushButton("Analizar")
        self.btn_generate = QPushButton("Generar Word")
        self.btn_clear = QPushButton("Limpiar")
        self.btn_save_form = QPushButton("Guardar formulario")
        self.btn_load_form = QPushButton("Cargar formulario")
        actions.addWidget(self.btn_load_layers, 0, 0)
        actions.addWidget(self.btn_analyze, 0, 1)
        actions.addWidget(self.btn_generate, 1, 0)
        actions.addWidget(self.btn_clear, 1, 1)
        actions.addWidget(self.btn_save_form, 2, 0)
        actions.addWidget(self.btn_load_form, 2, 1)
        layout.addLayout(actions)

        self.messages = QTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMinimumHeight(95)
        layout.addWidget(QLabel("Mensajes / resumen"))
        layout.addWidget(self.messages)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(wrapper)
        self.setWidget(scroll)

        self.source_count.valueChanged.connect(self._render_sources)
        self.fecha_evaluacion.dateChanged.connect(self._sync_base_date_to_empty_sources)
        self.btn_add_control.clicked.connect(self._add_control_row)
        self.btn_capture_control.clicked.connect(self._capture_control_selected)
        self.btn_remove_control.clicked.connect(self._remove_control_selected)
        self.btn_load_layers.clicked.connect(self._load_layers)
        self.btn_analyze.clicked.connect(self.analyze)
        self.btn_generate.clicked.connect(self.generate_docx)
        self.btn_clear.clicked.connect(self.clear_form)
        self.btn_save_form.clicked.connect(self.save_form)
        self.btn_load_form.clicked.connect(self.load_form)
        self._render_sources(1)

    def _render_sources(self, count):
        old_values = {}
        while self.sources_layout.count():
            item = self.sources_layout.takeAt(0)
            widget = item.widget()
            if widget:
                idx = getattr(widget, "index", len(old_values) + 1)
                old_values[idx] = widget.values()
                widget.setParent(None)
                widget.deleteLater()
        # _restore_source_data (de load_form) tiene prioridad sobre los valores actuales
        restore_data = dict(old_values)
        restore_data.update(self._restore_source_data)
        self.source_cards = []
        for index in range(1, int(count) + 1):
            card = SourceCard(index)
            if index in restore_data:
                card.restore(restore_data[index])
            else:
                card.fecha_eval.set_iso_value(self.fecha_evaluacion.iso_value())
            card.capture_requested.connect(self._start_capture)
            self.sources_layout.addWidget(card)
            self.source_cards.append(card)

    def _sync_base_date_to_empty_sources(self):
        base = self.fecha_evaluacion.iso_value()
        for card in self.source_cards:
            if not card.fecha_eval.iso_value():
                card.fecha_eval.set_iso_value(base)

    def _add_control_row(self):
        row = self.control_table.rowCount()
        self.control_table.insertRow(row)
        defaults = [f"Control {row + 1}", "", "", ""]
        for col, value in enumerate(defaults):
            self.control_table.setItem(row, col, QTableWidgetItem(value))

    def _remove_control_selected(self):
        rows = sorted({idx.row() for idx in self.control_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.control_table.removeRow(row)

    def _capture_control_selected(self):
        row = self.control_table.currentRow()
        if row < 0:
            self._add_control_row()
            row = self.control_table.rowCount() - 1
        for col in (2, 3):
            if not self.control_table.item(row, col):
                self.control_table.setItem(row, col, QTableWidgetItem(""))
        self._start_capture(self.control_table.item(row, 2), self.control_table.item(row, 3), f"Punto de control fila {row + 1}")

    def _start_capture(self, x_widget, y_widget, label):
        self.capture_target = (x_widget, y_widget, label)
        canvas = self.iface.mapCanvas()
        self.previous_map_tool = canvas.mapTool()
        self.map_tool = DictamenMapClickTool(canvas)
        self.map_tool.canvas_clicked.connect(self._finish_capture)
        canvas.setMapTool(self.map_tool)
        self._message(f"Captura activa: haga clic en el mapa para llenar {label}.")

    def _finish_capture(self, point):
        if not self.capture_target:
            return
        x_widget, y_widget, label = self.capture_target
        try:
            canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
            dst = QgsCoordinateReferenceSystem(self.input_crs.currentData())
            if canvas_crs != dst:
                tr = QgsCoordinateTransform(canvas_crs, dst, QgsProject.instance())
                point = tr.transform(point)
            decimals = 7 if self.input_crs.currentData() == "EPSG:4326" else 3
            x_widget.setText(f"{point.x():.{decimals}f}")
            y_widget.setText(f"{point.y():.{decimals}f}")
            self._message(f"Coordenada capturada para {label}: {point.x():.{decimals}f}, {point.y():.{decimals}f}")
        except Exception as exc:
            self._message("Error al capturar coordenada: " + str(exc))
        finally:
            canvas = self.iface.mapCanvas()
            if self.previous_map_tool:
                canvas.setMapTool(self.previous_map_tool)
            self.capture_target = None

    def _load_layers(self):
        self._message("Cargando capas integradas. Puede tardar por la capa distritocantonprovincia.")
        try:
            lines = self.layer_manager.load_all()
            self._message("\n".join(lines))
        except Exception as exc:
            self._message("Error al cargar capas: " + str(exc))
            self._message(traceback.format_exc())

    def _message(self, text):
        self.messages.append(str(text))

    def _item_text(self, row, col):
        item = self.control_table.item(row, col)
        return item.text().strip() if item else ""

    def collect_snapshot(self) -> dict:
        return {
            "input_crs": self.input_crs.currentData(),
            "oficio": self.oficio.text().strip(),
            "fecha_oficio": self.fecha_oficio.iso_value(),
            "solicitante": self.solicitante.text().strip(),
            "correo": self.correo.text().strip(),
            "id_solicitud": self.id_solicitud.text().strip(),
            "fecha_inspeccion": self.fecha_inspeccion.iso_value(),
            "fecha_evaluacion": self.fecha_evaluacion.iso_value(),
            "sitio": self.sitio.text().strip(),
            "acompanantes": self.acompanantes.text().strip(),
            "profesional_responsable": self.profesional.text().strip(),
            "sources": [card.values() for card in self.source_cards],
            "control_points": [
                {"label": self._item_text(row, 0), "number": self._item_text(row, 1), "x": self._item_text(row, 2), "y": self._item_text(row, 3)}
                for row in range(self.control_table.rowCount())
            ],
        }

    def analyze(self):
        snapshot = self.collect_snapshot()
        self.last_snapshot_repr = repr(snapshot)
        self.last_analyzed_data = None
        task = AnalysisTask(self, self.plugin_dir, snapshot)
        self.active_tasks.append(task)
        self.btn_analyze.setEnabled(False)
        self._message("Análisis enviado a segundo plano. Puede seguir usando QGIS mientras termina.")
        QgsApplication.taskManager().addTask(task)

    def _analysis_finished(self, task, ok):
        self.btn_analyze.setEnabled(True)
        if task in self.active_tasks:
            self.active_tasks.remove(task)
        if not ok:
            self._message("Error en análisis espacial:\n" + task.error_text)
            return
        data = task.result_data
        self.last_analyzed_data = data
        lines = [f"Análisis espacial completado. Cuadro 1: {len(data['field_points'])} punto(s). Fuente(s): {len(data['sources'])}."]
        for src in data["sources"]:
            lines.append(
                f"Fuente {src.get('numero_fuente')}: {src.get('provincia','')}, "
                f"{src.get('canton','')}, {src.get('distrito','')} | "
                f"Cuenca {src.get('cuenca_numero','')} {src.get('cuenca_nombre','')} | "
                f"Hoja {src.get('hoja_cartografica','')} | Suelo {src.get('orden_suelo','')}"
            )
            if src.get("warning"):
                lines.append("Advertencia: " + src["warning"])
        self._message("\n".join(lines))

    def generate_docx(self):
        if not self.profesional.text().strip():
            QMessageBox.warning(self, "Dato requerido", "Debe indicar el profesional responsable antes de generar el Word.")
            return
        snapshot = self.collect_snapshot()
        snapshot_repr = repr(snapshot)
        cached_data = self.last_analyzed_data if self.last_snapshot_repr == snapshot_repr else None
        directory = QFileDialog.getExistingDirectory(self, "Carpeta para guardar el dictamen")
        if not directory:
            return
        task = GenerateTask(self, self.plugin_dir, snapshot, directory, analyzed_data=cached_data)
        self.active_tasks.append(task)
        self.btn_generate.setEnabled(False)
        if cached_data:
            self._message("Generación enviada a segundo plano usando el análisis ya calculado. No se recargarán las capas GeoJSON.")
        else:
            self._message("Generación enviada a segundo plano. Se calculará el análisis espacial antes de crear el Word.")
        QgsApplication.taskManager().addTask(task)

    def _generate_finished(self, task, ok):
        self.btn_generate.setEnabled(True)
        if task in self.active_tasks:
            self.active_tasks.remove(task)
        if not ok:
            self._message("Error al generar Word:\n" + task.error_text)
            QMessageBox.critical(self, "Error", task.error_text.splitlines()[-1] if task.error_text else "Error desconocido")
            return
        self._message("Documento generado: " + task.output_path)
        QMessageBox.information(self, "Dictámenes-DA", "Documento generado:\n" + task.output_path)

    def save_form(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar formulario", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.collect_snapshot(), f, ensure_ascii=False, indent=2)
            self._message("Formulario guardado en: " + path)
        except Exception as exc:
            self._message("Error al guardar formulario: " + str(exc))

    def load_form(self):
        path, _ = QFileDialog.getOpenFileName(self, "Cargar formulario", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
            self._restore_snapshot(snapshot)
            self._message("Formulario cargado desde: " + path)
        except Exception as exc:
            self._message("Error al cargar formulario: " + str(exc))

    def _restore_snapshot(self, snapshot: dict):
        crs_val = snapshot.get("input_crs", "EPSG:5367")
        for i in range(self.input_crs.count()):
            if self.input_crs.itemData(i) == crs_val:
                self.input_crs.setCurrentIndex(i)
                break
        self.oficio.setText(snapshot.get("oficio", ""))
        self.fecha_oficio.set_iso_value(snapshot.get("fecha_oficio", ""))
        self.solicitante.setText(snapshot.get("solicitante", ""))
        self.correo.setText(snapshot.get("correo", ""))
        self.id_solicitud.setText(snapshot.get("id_solicitud", ""))
        self.fecha_inspeccion.set_iso_value(snapshot.get("fecha_inspeccion", ""))
        self.fecha_evaluacion.set_iso_value(snapshot.get("fecha_evaluacion", ""))
        self.sitio.setText(snapshot.get("sitio", ""))
        self.acompanantes.setText(snapshot.get("acompanantes", ""))
        self.profesional.setText(snapshot.get("profesional_responsable", ""))
        sources = snapshot.get("sources", [{}])
        self._restore_source_data = {i + 1: s for i, s in enumerate(sources)}
        self.source_count.setValue(max(1, len(sources)))
        self._restore_source_data = {}
        self.control_table.setRowCount(0)
        for raw in snapshot.get("control_points", []):
            row = self.control_table.rowCount()
            self.control_table.insertRow(row)
            for col, key in enumerate(["label", "number", "x", "y"]):
                self.control_table.setItem(row, col, QTableWidgetItem(raw.get(key, "")))

    def clear_form(self):
        for widget in [
            self.oficio, self.solicitante, self.correo, self.id_solicitud,
            self.sitio, self.acompanantes, self.profesional,
        ]:
            widget.clear()
        for widget in [self.fecha_oficio, self.fecha_inspeccion, self.fecha_evaluacion]:
            widget.clear()
        self.source_count.setValue(1)
        self._render_sources(1)
        self.control_table.setRowCount(0)
        self.messages.clear()
        self._message("Formulario limpio.")
