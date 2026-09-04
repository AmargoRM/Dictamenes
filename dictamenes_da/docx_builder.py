# -*- coding: utf-8 -*-
"""Generador DOCX basado en el machote original.

Esta versión no reconstruye el documento desde cero. Abre el .docx de
assets/template y sustituye únicamente los campos/fragmentos del machote,
replicando la lógica del HTML v10 con Python estándar para QGIS.
"""
from __future__ import annotations

import os
import re
import zipfile
from datetime import datetime
from xml.dom import minidom

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'

# --- Fuente oficial del dictamen -------------------------------------------
# El machote hereda "Calibri (Cuerpo) 11" del tema del documento. Todo el
# cuerpo debe ser Times New Roman 11. El encabezado y el pie de pagina usan
# las fuentes del membrete institucional y NO se tocan.
FUENTE_OFICIAL = "Times New Roman"
TAM_OFICIAL = "22"  # OOXML mide en medios puntos: 22 = 11 pt

# Orden que exige el esquema OOXML dentro de <w:rPr>. Si se insertan nodos
# fuera de este orden Word puede declarar el archivo danado.
_ORDEN_RPR = [
    "w:rStyle", "w:rFonts", "w:b", "w:bCs", "w:i", "w:iCs", "w:caps", "w:smallCaps",
    "w:strike", "w:dstrike", "w:outline", "w:shadow", "w:emboss", "w:imprint",
    "w:noProof", "w:snapToGrid", "w:vanish", "w:webHidden", "w:color", "w:spacing",
    "w:w", "w:kern", "w:position", "w:sz", "w:szCs", "w:highlight", "w:u", "w:effect",
    "w:bdr", "w:shd", "w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang",
    "w:eastAsianLayout", "w:specVanish", "w:oMath",
]

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _template_path(plugin_dir: str) -> str:
    return os.path.join(plugin_dir, "assets", "template", "DA-UHSAN-XXXX-2026_ID.docx")


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


def _filename(data: dict) -> str:
    oficio = (data.get("oficio") or "").strip()
    fecha = data.get("fecha_oficio") or ""
    dp = date_parts(fecha)
    year = dp["year"] if dp else str(datetime.now().year)
    if oficio:
        base = f"DA-UHSAN-{oficio}-{year}_dictamen.docx"
    elif data.get("id_solicitud"):
        base = f"DA-UHSAN-{data.get('id_solicitud')}-{year}_dictamen.docx"
    else:
        base = "dictamen_cuerpo_agua_generado.docx"
    return _safe_filename(base)


def _text_nodes(node):
    return list(node.getElementsByTagName("w:t"))


def _node_text(node) -> str:
    out = []
    for t in _text_nodes(node):
        if t.firstChild:
            out.append(t.firstChild.data)
    return "".join(out)


def run_text(run) -> str:
    return _node_text(run)


def set_run_text(run, text) -> None:
    text = "" if text is None else str(text)
    doc = run.ownerDocument
    nodes = _text_nodes(run)
    if not nodes:
        t = doc.createElementNS(W_NS, "w:t")
        run.appendChild(t)
        nodes = [t]
    first = nodes[0]
    while first.firstChild:
        first.removeChild(first.firstChild)
    first.appendChild(doc.createTextNode(text))
    first.setAttribute("xml:space", "preserve")
    for n in nodes[1:]:
        while n.firstChild:
            n.removeChild(n.firstChild)
        n.appendChild(doc.createTextNode(""))


def _first_child(node, tag):
    children = node.getElementsByTagName(tag)
    return children[0] if children else None


def remove_node(node) -> None:
    if node is not None and node.parentNode is not None:
        node.parentNode.removeChild(node)


def unwrap_element(el) -> None:
    if el is None or el.parentNode is None:
        return
    parent = el.parentNode
    while el.firstChild:
        parent.insertBefore(el.firstChild, el)
    parent.removeChild(el)


def _insertar_ordenado(rpr, nodo) -> None:
    """Mete un nodo dentro de <w:rPr> respetando el orden del esquema OOXML."""
    try:
        pos = _ORDEN_RPR.index(nodo.nodeName)
    except ValueError:
        rpr.appendChild(nodo)
        return
    for hijo in list(rpr.childNodes):
        if hijo.nodeType != hijo.ELEMENT_NODE:
            continue
        try:
            pos_hijo = _ORDEN_RPR.index(hijo.nodeName)
        except ValueError:
            continue
        if pos_hijo > pos:
            rpr.insertBefore(nodo, hijo)
            return
    rpr.appendChild(nodo)


def _asegurar_rpr(run):
    """Devuelve el <w:rPr> del fragmento; lo crea como primer hijo si falta."""
    rpr = _first_child(run, "w:rPr")
    if rpr is None:
        rpr = run.ownerDocument.createElementNS(W_NS, "w:rPr")
        run.insertBefore(rpr, run.firstChild)
    return rpr


def forzar_fuente_en_rpr(rpr, con_tamano=False) -> None:
    """Escribe Times New Roman explicito dentro de un <w:rPr> ya existente.

    Borra las referencias al tema (asciiTheme/hAnsiTheme/cstheme), que son las
    que hacen que Word muestre 'Calibri (Cuerpo)'. El tamano solo se toca
    cuando se pide, para no alterar los pies de figura ni los titulos.
    """
    if rpr is None:
        return
    doc = rpr.ownerDocument
    rfonts = _first_child(rpr, "w:rFonts")
    if rfonts is None:
        rfonts = doc.createElementNS(W_NS, "w:rFonts")
        _insertar_ordenado(rpr, rfonts)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme"):
        if rfonts.hasAttribute(attr):
            rfonts.removeAttribute(attr)
    rfonts.setAttribute("w:ascii", FUENTE_OFICIAL)
    rfonts.setAttribute("w:hAnsi", FUENTE_OFICIAL)
    rfonts.setAttribute("w:cs", FUENTE_OFICIAL)
    if not con_tamano:
        return
    for tag in ("w:sz", "w:szCs"):
        nodo = _first_child(rpr, tag)
        if nodo is None:
            nodo = doc.createElementNS(W_NS, tag)
            _insertar_ordenado(rpr, nodo)
        nodo.setAttribute("w:val", TAM_OFICIAL)


def forzar_fuente_en_run(run, con_tamano=False) -> None:
    forzar_fuente_en_rpr(_asegurar_rpr(run), con_tamano)


def normalizar_fuentes(xml_doc) -> None:
    """Pasada final: deja Times New Roman en TODO el cuerpo del documento.

    Cubre los fragmentos de texto y tambien la marca de parrafo (<w:pPr><w:rPr>),
    que es lo que Word reporta como 'Calibri (Cuerpo)' al hacer clic al final
    de una linea. No toca los tamanos heredados de cada estilo.
    """
    for run in list(xml_doc.getElementsByTagName("w:r")):
        forzar_fuente_en_run(run)
    for ppr in list(xml_doc.getElementsByTagName("w:pPr")):
        for hijo in list(ppr.childNodes):
            if hijo.nodeType == hijo.ELEMENT_NODE and hijo.nodeName == "w:rPr":
                forzar_fuente_en_rpr(hijo)


def normalizar_estilos(xml_bytes: bytes) -> str:
    """Cambia la fuente por defecto del documento de tema (Calibri) a Times.

    Solo toca el valor por defecto y los estilos que traen Calibri escrito,
    excepto los del encabezado/pie, que pertenecen al membrete institucional.
    """
    doc = minidom.parseString(xml_bytes)
    for defecto in doc.getElementsByTagName("w:rPrDefault"):
        for rpr in defecto.getElementsByTagName("w:rPr"):
            forzar_fuente_en_rpr(rpr)
    for estilo in doc.getElementsByTagName("w:style"):
        sid = (estilo.getAttribute("w:styleId") or "").lower()
        if "piedep" in sid or "encabezado" in sid:
            continue
        for rfonts in estilo.getElementsByTagName("w:rFonts"):
            for attr in ("w:ascii", "w:hAnsi"):
                if rfonts.getAttribute(attr).strip().lower() == "calibri":
                    rfonts.setAttribute(attr, FUENTE_OFICIAL)
    return serialize_ooxml(doc)


def is_highlighted(run) -> bool:
    rpr = _first_child(run, "w:rPr")
    if not rpr:
        return False
    hl = _first_child(rpr, "w:highlight")
    return bool(hl and hl.getAttribute("w:val") and hl.getAttribute("w:val") != "none")


def clear_highlight(run) -> None:
    rpr = _first_child(run, "w:rPr")
    if not rpr:
        return
    for tag in ("w:highlight", "w:shd", "w:u"):
        for n in list(rpr.getElementsByTagName(tag)):
            remove_node(n)


def is_placeholder_run(run, strict=True) -> bool:
    if not is_highlighted(run):
        return False
    t = run_text(run).strip()
    if not t:
        return False
    if not strict:
        return True
    return bool(re.match(r"^[0-9Xx\s\-\u2013]+$", t) and re.search(r"[Xx]", t))


def paragraph_text(p) -> str:
    return _node_text(p)


def build_doc_index(xml_doc):
    paragraphs = list(xml_doc.getElementsByTagName("w:p"))
    all_runs = list(xml_doc.getElementsByTagName("w:r"))
    run_global = {id(r): i for i, r in enumerate(all_runs)}
    para_info = []
    for p in paragraphs:
        runs = list(p.getElementsByTagName("w:r"))
        text = ""
        mapping = []
        for r in runs:
            t = run_text(r)
            mapping.append({"run": r, "start": len(text), "end": len(text) + len(t)})
            text += t
        para_info.append({"p": p, "runs": runs, "text": text, "map": mapping})
    return {"paragraphs": paragraphs, "allRuns": all_runs, "runGlobalIndex": run_global, "paraInfo": para_info}


def find_anchor_global_index(idx, anchor_text, occurrence=1):
    seen = 0
    for pi, info in enumerate(idx["paraInfo"]):
        pos = info["text"].find(anchor_text)
        if pos == -1:
            continue
        seen += 1
        if seen != occurrence:
            continue
        end_pos = pos + len(anchor_text)
        for m in info["map"]:
            if m["start"] >= end_pos:
                return idx["runGlobalIndex"].get(id(m["run"]))
        for pj in range(pi + 1, len(idx["paraInfo"])):
            if idx["paraInfo"][pj]["map"]:
                return idx["runGlobalIndex"].get(id(idx["paraInfo"][pj]["map"][0]["run"]))
        return None
    return None


def fill_single_after_anchor(idx, anchor_text, value, occurrence=1) -> bool:
    if value is None or value == "":
        return False
    gidx = find_anchor_global_index(idx, anchor_text, occurrence)
    if gidx is None:
        return False
    runs_block = []
    i = gidx
    scanned = 0
    all_runs = idx["allRuns"]
    while i < len(all_runs) and scanned < 40:
        r = all_runs[i]
        t = run_text(r)
        if is_placeholder_run(r) or is_highlighted(r):
            runs_block.append(r)
            i += 1
            scanned += 1
            continue
        if runs_block and re.match(r"^[\s\-\u2013/:]*$", t):
            i += 1
            scanned += 1
            continue
        if not runs_block and re.match(r"^[\s:：\-\u2013]*$", t):
            i += 1
            scanned += 1
            continue
        break
    if not runs_block:
        anchor_run = all_runs[gidx]
        parent = anchor_run.parentNode
        new_run = anchor_run.cloneNode(True)
        clear_highlight(new_run)
        set_run_text(new_run, " " + str(value))
        parent.insertBefore(new_run, anchor_run)
        return True
    lead = re.match(r"^\s+", run_text(runs_block[0]))
    lead_text = lead.group(0) if lead else ""
    for k, r in enumerate(runs_block):
        set_run_text(r, (lead_text + str(value)) if k == 0 else "")
        clear_highlight(r)
    return True


def clear_underline_in_paragraph_containing(idx, anchor_text) -> bool:
    for info in idx["paraInfo"]:
        if anchor_text in info["text"]:
            for r in info["runs"]:
                rpr = _first_child(r, "w:rPr")
                if rpr:
                    for u in list(rpr.getElementsByTagName("w:u")):
                        remove_node(u)
            return True
    return False


def replace_text_in_paragraph_containing(idx, search_text, replacement_text) -> bool:
    changed = False
    for info in idx["paraInfo"]:
        if search_text not in info["text"]:
            continue
        for r in info["runs"]:
            t = run_text(r)
            if search_text in t:
                set_run_text(r, t.replace(search_text, replacement_text))
                changed = True
    return changed


def normalize_text_for_match(text) -> str:
    import unicodedata
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def normalize_request_id(value) -> str:
    return re.sub(r"[\s,;:.\-\u2013\u2014]+$", "", re.sub(r"^ID\s*", "", value or "", flags=re.I).strip())


def replace_final_professional_signature(idx, name) -> bool:
    clean = (name or "").strip()
    if not clean:
        return False
    candidates = [pi for pi in idx["paraInfo"] if normalize_text_for_match(pi["text"]) == "leonardo corella blanco"]
    if not candidates:
        return False
    info = candidates[-1]
    if not info["runs"]:
        return False
    set_run_text(info["runs"][0], clean)
    clear_highlight(info["runs"][0])
    for r in info["runs"][1:]:
        set_run_text(r, "")
    return True


def replace_initial_professional_paragraph(idx, name, request_id) -> bool:
    clean_name = (name or "").strip()
    clean_id = normalize_request_id(request_id)
    if not clean_name and not clean_id:
        return False
    info = None
    for pi in idx["paraInfo"]:
        if "El suscrito" in pi["text"] and "Profesional en la Gestión del Recurso Hídrico" in pi["text"]:
            info = pi
            break
    if not info or not info["runs"]:
        return False
    new_text = info["text"]
    if clean_name:
        new_text = re.sub(
            r"El suscrito\s+.*?,\s*portador de la c[eé]dula de identidad n[uú]mero\s*2-750-908,\s*",
            "El suscrito " + clean_name + ", ",
            new_text,
            flags=re.I,
        )
        new_text = re.sub(r"El suscrito\s+Leonardo\s+Antonio\s+Corella\s+Blanco,?\s*",
                          "El suscrito " + clean_name + ", ", new_text, flags=re.I)
    if clean_id:
        new_text = re.sub(r"mediante\s+ID\s+[^,]+,\s*es que se le indica lo siguiente:?",
                          "mediante ID " + clean_id + ", es que se le indica lo siguiente:", new_text, flags=re.I)
        new_text = re.sub(r"mediante\s+ID\s+X+[\-\u2013]X+,?\s*",
                          "mediante ID " + clean_id + ", ", new_text, flags=re.I)
    new_text = re.sub(r",\s*,", ",", new_text)
    new_text = re.sub(r",\s*es que se le indica lo siguiente:\s*,?\s*es que se le indica lo siguiente:",
                      ", es que se le indica lo siguiente:", new_text, flags=re.I)
    new_text = re.sub(r"\s+([,.;:])", r"\1", new_text)
    new_text = re.sub(r"\s+", " ", new_text).strip()
    set_run_text(info["runs"][0], new_text)
    clear_highlight(info["runs"][0])
    for r in info["runs"][1:]:
        set_run_text(r, "")
    return True


def fill_sequence_after_anchor(idx, anchor_text, values, occurrence=1) -> bool:
    gidx = find_anchor_global_index(idx, anchor_text, occurrence)
    if gidx is None:
        return False
    vi = 0
    i = gidx
    scanned = 0
    all_runs = idx["allRuns"]
    while i < len(all_runs) and vi < len(values) and scanned < 30:
        r = all_runs[i]
        if is_placeholder_run(r):
            if values[vi] is not None and values[vi] != "":
                set_run_text(r, values[vi])
                clear_highlight(r)
            vi += 1
        i += 1
        scanned += 1
    return vi > 0


def _parse_date(date_str):
    if not date_str:
        return None
    s = str(date_str).strip()
    for pat in (r"^(\d{4})-(\d{1,2})-(\d{1,2})$", r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$"):
        m = re.match(pat, s)
        if not m:
            continue
        if pat.startswith("^(\\d{4})"):
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return y, mo, d
    return None


def date_parts(date_str):
    parsed = _parse_date(date_str)
    if not parsed:
        return None
    y, m, d = parsed
    return {"day": str(int(d)), "month": MESES[m - 1], "year": str(y), "yearSuffix": str(y)[-2:]}


def format_soil_order(value) -> str:
    v = (value or "").strip().strip(".。").lower()
    return (v + ".") if v else ""


# La epoca se elige en femenino ("epoca seca"), pero el parrafo del IMN habla de
# "periodo", que es masculino. Aqui se traduce de una forma a la otra.
EPOCA_MASCULINO = {
    "seca": "seco",
    "seco": "seco",
    "lluviosa": "lluvioso",
    "lluvioso": "lluvioso",
    "transicion": "de transición",
    "transición": "de transición",
}

_EPOCA_ACTUAL = re.compile(
    r"(realiz[oó]\s+en\s+el\s+periodo\s+)(?:de\s+transici[oó]n|seco|lluvioso|[Xx]{2,})",
    re.I,
)


def epoca_masculino(value) -> str:
    return EPOCA_MASCULINO.get((value or "").strip().lower(), "")


def fill_epoca_periodo(idx, epoca) -> bool:
    """Ajusta 'la visita se realizó en el periodo XXXX correspondiente a la zona Norte'
    segun la epoca elegida en la ventana. El anclaje exige el prefijo
    'realizo en el periodo', de modo que NO toca la cita climatologica del IMN que
    menciona 'el periodo seco en esta zona, el periodo lluvioso ...'."""
    palabra = epoca_masculino(epoca)
    if not palabra:
        return False
    changed = False
    for info in idx["paraInfo"]:
        if "presente caso en estudio" not in info["text"]:
            continue
        for r in info["runs"]:
            t = run_text(r)
            if not _EPOCA_ACTUAL.search(t):
                continue
            set_run_text(r, _EPOCA_ACTUAL.sub(lambda m: m.group(1) + palabra, t))
            clear_highlight(r)
            changed = True
        if changed:
            continue
        # Reserva: el prefijo y la palabra quedaron en runs separados.
        runs = info["runs"]
        prefijo = re.compile(r"realiz[oó]\s+en\s+el\s+periodo\s*$", re.I)
        objetivo = re.compile(r"^(\s*)(?:de\s+transici[oó]n|seco|lluvioso|[Xx]{2,})", re.I)
        for n in range(len(runs) - 1):
            if not prefijo.search(run_text(runs[n])):
                continue
            siguiente = runs[n + 1]
            t = run_text(siguiente)
            if objetivo.search(t):
                set_run_text(siguiente, objetivo.sub(lambda m: (m.group(1) or " ") + palabra, t, count=1))
                clear_highlight(siguiente)
                changed = True
                break
    return changed


def fill_descriptions_occurrence(idx, descriptions, occurrence=1) -> None:
    targets = ["DESCRIPCIÓN #1", "DESCRIPCIÓN #2", "DESCRIPCIÓN #3", "DESCRIPCIÓN #4"]
    last_p = None
    for n, label in enumerate(targets):
        matches = [pi for pi in idx["paraInfo"] if pi["text"].strip() == label]
        info = matches[occurrence - 1] if len(matches) >= occurrence else None
        if not info:
            continue
        last_p = info["p"]
        if n < len(descriptions):
            if info["runs"]:
                set_run_text(info["runs"][0], descriptions[n])
                clear_highlight(info["runs"][0])
                for r in info["runs"][1:]:
                    set_run_text(r, "")
    if len(descriptions) > 4 and last_p is not None:
        ref = last_p
        for desc in descriptions[4:]:
            clone = last_p.cloneNode(True)
            runs = list(clone.getElementsByTagName("w:r"))
            if runs:
                set_run_text(runs[0], desc)
                clear_highlight(runs[0])
                for r in runs[1:]:
                    set_run_text(r, "")
            ref.parentNode.insertBefore(clone, ref.nextSibling)
            ref = clone


def insert_paragraph_before_anchor_occurrence(idx, anchor_text, text, occurrence=1) -> bool:
    if not text:
        return False
    matches = [pi for pi in idx["paraInfo"] if anchor_text in pi["text"]]
    info = matches[occurrence - 1] if len(matches) >= occurrence else None
    if not info:
        return False
    clone = info["p"].cloneNode(True)
    runs = list(clone.getElementsByTagName("w:r"))
    if runs:
        set_run_text(runs[0], text)
        for r in runs[1:]:
            set_run_text(r, "")
        for r in runs:
            clear_highlight(r)
    info["p"].parentNode.insertBefore(clone, info["p"])
    return True


def technical_definition_key_for_tipo(tipo) -> str | None:
    t = normalize_text_for_match(tipo)
    if t == "naciente":
        return "naciente"
    if t == "quebrada":
        return "quebrada"
    if t == "rio":
        return "rio"
    if t in ("lago / laguna", "lago", "laguna"):
        return "lago_laguna"
    if t in ("oceano / mar", "oceano", "mar"):
        return "oceano_mar"
    if t == "canal":
        return "canal"
    if t == "depresion natural":
        return "depresion_natural"
    if any(x in t for x in ("pozo", "galeria", "afloramiento provocado", "mina", "tunel", "embalse")):
        return "pozos_galerias"
    return None


def technical_definition_start_key(text) -> str | None:
    t = re.sub(r"^[-\u2013•\s]+", "", normalize_text_for_match(text))
    tests = [
        (r"^naciente\s*:", "naciente"),
        (r"^quebrada\s*:", "quebrada"),
        (r"^rio\s*:", "rio"),
        (r"^lago\s*/\s*laguna\s*:", "lago_laguna"),
        (r"^oceano\s*/\s*mar\s*:", "oceano_mar"),
        (r"^canal\s*:", "canal"),
        (r"^depresion natural\s*:", "depresion_natural"),
        (r"^pozos,\s*galerias,\s*afloramiento provocado,\s*minas,\s*tuneles,\s*embalses\s*:", "pozos_galerias"),
    ]
    for rx, key in tests:
        if re.match(rx, t):
            return key
    return None


def keep_only_selected_technical_definition(xml_doc, tipo_fuente) -> bool:
    tipos = tipo_fuente if isinstance(tipo_fuente, list) else [tipo_fuente]
    selected = {technical_definition_key_for_tipo(t) for t in tipos}
    selected.discard(None)
    blocks = []
    current = None
    for p in list(xml_doc.getElementsByTagName("w:p")):
        text = paragraph_text(p)
        start_key = technical_definition_start_key(text)
        if start_key:
            current = {"key": start_key, "paragraphs": [p]}
            blocks.append(current)
            continue
        normalized = normalize_text_for_match(text)
        if current:
            if re.match(r"^asi mismo se muestra\s*:", normalized) or re.match(r"^permanente\s*:", normalized) or re.match(r"^intermitente\s*:", normalized) or re.match(r"^cuadro\s+2\.", normalized):
                current = None
            else:
                current["paragraphs"].append(p)
    if not blocks:
        return False
    for block in blocks:
        if block["key"] not in selected:
            for p in block["paragraphs"]:
                remove_node(p)
    return True


def cell_text(tc) -> str:
    return _node_text(tc)


def set_cell_text(tc, text, owner_doc) -> None:
    ps = list(tc.getElementsByTagName("w:p"))
    if ps:
        para = ps[0]
    else:
        para = owner_doc.createElementNS(W_NS, "w:p")
        tc.appendChild(para)
    runs = list(para.getElementsByTagName("w:r"))
    if runs:
        run = runs[0]
    else:
        # Celda vacia en el machote: el fragmento nuevo nace sin formato y
        # heredaria Calibri 11. Se le escribe Times New Roman 11 explicito.
        run = owner_doc.createElementNS(W_NS, "w:r")
        para.appendChild(run)
        runs = [run]
        forzar_fuente_en_run(run, con_tamano=True)
    set_run_text(run, text)
    clear_highlight(run)
    for r in runs[1:]:
        set_run_text(r, "")


def clear_table_row_cells(row, owner_doc) -> None:
    for tc in list(row.getElementsByTagName("w:tc")):
        set_cell_text(tc, "", owner_doc)


def field_point_display(p) -> str:
    if not p:
        return ""
    num = f"Punto {p.get('pointNumber')}" if p.get("pointNumber") else ""
    if p.get("sourceNumber") and (p.get("pointRole") or p.get("label")):
        role = p.get("pointRole") or p.get("label")
        return f"Fuente {p.get('sourceNumber')} - {role}{(' (' + num + ')') if num else ''}"
    return (p.get("label") or "Punto") + ((" (" + num + ")") if num else "")


def normalize_coord_points(points):
    if isinstance(points, list):
        return [p for p in points if p]
    if not points:
        return []
    return [p for p in [points.get("start"), points.get("end")] + points.get("controls", []) if p]


def _fmt2(v) -> str:
    try:
        return f"{float(v):.2f}"
    except Exception:
        return ""


def fill_coord_table(idx, points, owner_doc, options=None) -> bool:
    point_list = normalize_coord_points(points)
    options = options or {}
    mode = options.get("mode", "all")
    wanted = options.get("occurrence")
    tables = list(owner_doc.getElementsByTagName("w:tbl"))
    seen_eligible = 0
    changed = False
    for tbl in tables:
        tbl_text = _node_text(tbl)
        if "CRTM05" not in tbl_text or "Lambert" not in tbl_text:
            continue
        rows = list(tbl.getElementsByTagName("w:tr"))
        if len(rows) < 3:
            continue
        has_coord_col = any(any(re.match(r"^\s*Coordenada\s*$", cell_text(tc), flags=re.I) for tc in row.getElementsByTagName("w:tc")) for row in rows)
        has_point_col = any(any(re.match(r"^\s*Punto\s*$", cell_text(tc), flags=re.I) for tc in row.getElementsByTagName("w:tc")) for row in rows)
        is_technical = has_coord_col and has_point_col
        if mode == "field" and is_technical:
            continue
        if mode == "technical" and not is_technical:
            continue
        seen_eligible += 1
        if wanted and seen_eligible != wanted:
            continue
        point_col_idx = 1 if is_technical else 0
        coord_start_cell = 2 if is_technical else 1
        data_rows = []
        for i, row in enumerate(rows):
            if i < 2:
                continue
            cells = list(row.getElementsByTagName("w:tc"))
            if len(cells) >= coord_start_cell + 4:
                data_rows.append(row)
        if not data_rows:
            continue
        parent = data_rows[-1].parentNode or tbl
        while len(data_rows) < len(point_list):
            clone = data_rows[-1].cloneNode(True)
            clear_table_row_cells(clone, owner_doc)
            parent.appendChild(clone)
            data_rows.append(clone)
        while len(data_rows) > len(point_list) and data_rows:
            row = data_rows.pop()
            remove_node(row)
        for ridx, row in enumerate(data_rows):
            cells = list(row.getElementsByTagName("w:tc"))
            p = point_list[ridx] if ridx < len(point_list) else None
            if not p:
                clear_table_row_cells(row, owner_doc)
                continue
            if is_technical:
                set_cell_text(cells[0], p.get("pointRole") or p.get("label") or "", owner_doc)
            if has_point_col:
                set_cell_text(cells[point_col_idx], (p.get("pointNumber") or "") if is_technical else field_point_display(p), owner_doc)
            values = [_fmt2(p.get("crtmX")), _fmt2(p.get("crtmY")), _fmt2(p.get("lambertX")), _fmt2(p.get("lambertY"))]
            for i, v in enumerate(values):
                set_cell_text(cells[coord_start_cell + i], v, owner_doc)
            changed = True
    return changed


def fill_provincia_table(idx, values, owner_doc, occurrence=1) -> bool:
    seen = 0
    for tbl in list(owner_doc.getElementsByTagName("w:tbl")):
        rows = list(tbl.getElementsByTagName("w:tr"))
        if len(rows) < 2:
            continue
        header_cells = list(rows[0].getElementsByTagName("w:tc"))
        header_text = "|".join(cell_text(tc) for tc in header_cells)
        if "PROVINCIA" in header_text and "DISTRITO" in header_text and "SITIO" in header_text:
            seen += 1
            if seen != occurrence:
                continue
            cells = list(rows[1].getElementsByTagName("w:tc"))
            order = [values.get("provincia"), values.get("canton"), values.get("distrito"), values.get("sitio")]
            for i, val in enumerate(order):
                if i >= len(cells) or not val:
                    continue
                runs = list(cells[i].getElementsByTagName("w:r"))
                placeholder = next((r for r in runs if is_placeholder_run(r, False)), None) or (runs[0] if runs else None)
                if placeholder:
                    set_run_text(placeholder, val)
                    clear_highlight(placeholder)
            return True
    return False


def fill_all_office_numbers(idx, oficio, year) -> bool:
    if not oficio and not year:
        return False
    num = oficio or "XXXX"
    yr = year or "XXXX"
    changed = False
    for info in idx["paraInfo"]:
        if "DA-UHSAN-" not in info["text"]:
            continue
        pos = info["text"].find("DA-UHSAN-") + len("DA-UHSAN-")
        after_anchor = [m["run"] for m in info["map"] if m["end"] > pos]
        highlighted = []
        for r in after_anchor:
            t = run_text(r).strip()
            if is_highlighted(r) and re.match(r"^[0-9Xx\-\u2013]+$", t) and (re.search(r"[Xx]", t) or re.match(r"^[\-\u2013]+$", t)):
                highlighted.append(r)
        highlighted = highlighted[:5]
        x_runs = [r for r in highlighted if re.search(r"[Xx]", run_text(r))]
        if not x_runs:
            continue
        if len(x_runs) == 1:
            set_run_text(x_runs[0], f"{num}-{yr}")
        else:
            first_original = run_text(x_runs[0])
            set_run_text(x_runs[0], f"{num}-" if re.search(r"[\-\u2013]\s*$", first_original) else num)
            set_run_text(x_runs[1], yr)
            for r in x_runs[2:]:
                set_run_text(r, "")
        for r in highlighted:
            clear_highlight(r)
        changed = True
    return changed


def top_level_child_for_node(node):
    n = node
    while n is not None and n.parentNode is not None and n.parentNode.nodeName != "w:body":
        n = n.parentNode
    return n


def duplicate_source_blocks(xml_doc, count) -> bool:
    count = max(1, int(count or 1))
    if count <= 1:
        return False
    paras = list(xml_doc.getElementsByTagName("w:p"))
    start_para = next((p for p in paras if re.search(r"NUMERO\s+DE\s+FUENTE", paragraph_text(p), flags=re.I)), None)
    end_para = next((p for p in paras if "Se le informa para que realice lo que corresponda" in paragraph_text(p)), None)
    if not start_para or not end_para:
        return False
    start_node = top_level_child_for_node(start_para)
    end_node = top_level_child_for_node(end_para)
    if not start_node or not end_node or not start_node.parentNode or start_node.parentNode is not end_node.parentNode:
        return False
    body = start_node.parentNode
    block = []
    n = start_node
    while n is not None and n is not end_node:
        block.append(n)
        n = n.nextSibling
    if not block:
        return False
    for _i in range(2, count + 1):
        for node in block:
            body.insertBefore(node.cloneNode(True), end_node)
    return True


def _remove_elements_by_local_name(root, names) -> None:
    for name in names:
        for n in list(root.getElementsByTagName("w:" + name)):
            remove_node(n)


def _unwrap_elements_by_local_name(root, names) -> None:
    for name in names:
        for n in list(root.getElementsByTagName("w:" + name)):
            unwrap_element(n)


def strip_review_markup_and_highlights(xml_doc):
    _remove_elements_by_local_name(xml_doc, ["commentRangeStart", "commentRangeEnd", "commentReference"])
    _remove_elements_by_local_name(xml_doc, ["del", "moveFrom", "moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd"])
    _unwrap_elements_by_local_name(xml_doc, ["ins", "moveTo"])
    for rpr in list(xml_doc.getElementsByTagName("w:rPr")):
        for tag in ("w:highlight", "w:shd"):
            for n in list(rpr.getElementsByTagName(tag)):
                remove_node(n)
    _remove_elements_by_local_name(xml_doc, ["trackRevisions"])
    return xml_doc


def serialize_ooxml(xml_doc) -> str:
    xml = xml_doc.toxml()
    xml = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", xml, flags=re.I)
    return XML_DECL + xml


def _remove_relationships(xml_bytes: bytes, patterns) -> str:
    doc = minidom.parseString(xml_bytes)
    for rel in list(doc.getElementsByTagName("Relationship")):
        typ = rel.getAttribute("Type") or ""
        target = rel.getAttribute("Target") or ""
        if any(p.search(typ) or p.search(target) for p in patterns):
            remove_node(rel)
    return serialize_ooxml(doc)


def _remove_content_types(xml_bytes: bytes, patterns) -> str:
    doc = minidom.parseString(xml_bytes)
    for ov in list(doc.getElementsByTagName("Override")):
        part = ov.getAttribute("PartName") or ""
        if any(p.search(part) for p in patterns):
            remove_node(ov)
    return serialize_ooxml(doc)


def apply_substitutions(xml_bytes: bytes, fv: dict, part_path: str) -> str:
    xml_doc = minidom.parseString(xml_bytes)
    is_main = (not part_path) or part_path == "word/document.xml"
    sources = fv.get("sources") or [{
        "numero_fuente": fv.get("numero_fuente"),
        "fecha_evaluacion": fv.get("fecha_evaluacion"),
        "tipo_fuente": fv.get("tipo_fuente"),
        "nombre_fuente": fv.get("nombre_fuente"),
        "criterio_fuente": fv.get("criterio_fuente"),
        "afluente_de": fv.get("afluente_de"),
        "provincia": fv.get("provincia"),
        "canton": fv.get("canton"),
        "distrito": fv.get("distrito"),
        "sitio": fv.get("sitio"),
        "hoja_cartografica": fv.get("hoja_cartografica"),
        "cuenca_numero": fv.get("cuenca_numero"),
        "cuenca_nombre": fv.get("cuenca_nombre"),
        "epoca_zona": fv.get("epoca_zona"),
        "descripciones": fv.get("descripciones") or [],
        "orden_suelo": fv.get("orden_suelo"),
        "observaciones": fv.get("observaciones"),
        "field_points": fv.get("field_points") or [],
        "technical_points": fv.get("technical_points") or [],
    }]
    if is_main:
        duplicate_source_blocks(xml_doc, len(sources))
        keep_only_selected_technical_definition(xml_doc, [src.get("tipo_fuente") for src in sources])
    idx = build_doc_index(xml_doc)
    dp_office = date_parts(fv.get("fecha_oficio"))

    if not is_main:
        fill_all_office_numbers(idx, fv.get("oficio"), dp_office["year"] if dp_office else "")
        strip_review_markup_and_highlights(xml_doc)
        return serialize_ooxml(xml_doc)

    if idx["paraInfo"] and idx["paraInfo"][0]["map"]:
        dp = date_parts(fv.get("fecha_oficio"))
        if dp:
            gidx = idx["runGlobalIndex"].get(id(idx["paraInfo"][0]["map"][0]["run"]))
            vals = [dp["day"], dp["month"], dp["year"]]
            vi = 0
            i = gidx if gidx is not None else 0
            while i < len(idx["allRuns"]) and vi < len(vals):
                if is_placeholder_run(idx["allRuns"][i]):
                    set_run_text(idx["allRuns"][i], vals[vi])
                    clear_highlight(idx["allRuns"][i])
                    vi += 1
                i += 1

    fill_all_office_numbers(idx, fv.get("oficio"), dp_office["year"] if dp_office else "")
    fill_single_after_anchor(idx, "Solicitante:", fv.get("solicitante"))
    fill_single_after_anchor(idx, "Correo electrónico:", fv.get("correo"))
    fill_single_after_anchor(idx, "Referencia: Dictamen de cuerpo de agua solicitado. ID", fv.get("id_solicitud"))
    clear_underline_in_paragraph_containing(idx, "Referencia: Dictamen de cuerpo de agua solicitado. ID")
    fill_single_after_anchor(idx, "persona mediante ID", fv.get("id_solicitud"))
    if fv.get("id_solicitud"):
        replace_text_in_paragraph_containing(idx, "ID " + fv.get("id_solicitud") + "-", "ID " + fv.get("id_solicitud"))

    first = sources[0] if sources else {}
    dp_insp = date_parts(fv.get("fecha_inspeccion"))
    fill_single_after_anchor(idx, "Fecha de inspección:", f"{dp_insp['day']} de {dp_insp['month']} del {dp_insp['year']}" if dp_insp else "")
    fill_single_after_anchor(idx, "Provincia:", fv.get("provincia") or first.get("provincia"))
    fill_single_after_anchor(idx, "Cantón:", fv.get("canton") or first.get("canton"))
    fill_single_after_anchor(idx, "Distrito:", fv.get("distrito") or first.get("distrito"))
    fill_single_after_anchor(idx, "Sitio:", fv.get("sitio"))
    fill_single_after_anchor(idx, "Acompañantes:", fv.get("acompanantes"))
    replace_final_professional_signature(idx, fv.get("profesional_responsable"))
    replace_initial_professional_paragraph(idx, fv.get("profesional_responsable"), fv.get("id_solicitud"))

    fill_coord_table(idx, fv.get("field_points") or [], xml_doc, {"mode": "field"})

    for source_index, src in enumerate(sources):
        occ = source_index + 1
        dp_eval = date_parts(src.get("fecha_evaluacion") or fv.get("fecha_evaluacion"))
        fill_single_after_anchor(idx, "NUMERO DE FUENTE:", src.get("numero_fuente"), occ)
        fill_single_after_anchor(idx, "REFERENCIA: ID", fv.get("id_solicitud"), occ)
        fill_sequence_after_anchor(idx, "FECHA DE EVALUACIÓN:", [dp_eval["day"], dp_eval["month"], dp_eval["year"]] if dp_eval else [], occ)
        fill_provincia_table(idx, {
            "provincia": src.get("provincia"),
            "canton": src.get("canton"),
            "distrito": src.get("distrito"),
            "sitio": fv.get("sitio"),
        }, xml_doc, occ)
        fill_single_after_anchor(idx, "TIPO FUENTE:", src.get("tipo_fuente"), occ)
        fill_single_after_anchor(idx, "NOMBRE:", src.get("nombre_fuente"), occ)
        fill_single_after_anchor(idx, "CRITERIO SOBRE LA FUENTE:", src.get("criterio_fuente"), occ)
        fill_single_after_anchor(idx, "AFLUENTE DE:", src.get("afluente_de"), occ)
        fill_single_after_anchor(idx, "HOJA_CARTOGRÁFICA:", src.get("hoja_cartografica"), occ)
        fill_sequence_after_anchor(idx, "CUENCA:", [src.get("cuenca_numero"), src.get("cuenca_nombre")], occ)
        fill_coord_table(idx, src.get("technical_points") or [], xml_doc, {"mode": "technical", "occurrence": occ})
        if dp_insp:
            fill_sequence_after_anchor(idx, "De acuerdo con la inspección realizada el día",
                                       [dp_insp["day"], dp_insp["month"], dp_insp["yearSuffix"], src.get("epoca_zona") or fv.get("epoca_zona")], occ)
        fill_single_after_anchor(idx, "del tipo", src.get("tipo_fuente"), occ)
        fill_descriptions_occurrence(idx, src.get("descripciones") or [], occ)
        insert_paragraph_before_anchor_occurrence(idx, "La pendiente del sitio converge", src.get("observaciones"), occ)
        replace_text_in_paragraph_containing(idx, "capa de sueños", "capa de suelos")
        fill_single_after_anchor(idx, "se muestra que el orden del suelo en la zona de estudio corresponde a terreno", format_soil_order(src.get("orden_suelo")), occ)

    fill_epoca_periodo(idx, first.get("epoca_zona") or fv.get("epoca_zona"))

    strip_review_markup_and_highlights(xml_doc)
    normalizar_fuentes(xml_doc)
    return serialize_ooxml(xml_doc)


def clean_review_package(entries: dict) -> None:
    for path in [
        "word/comments.xml", "word/commentsExtended.xml", "word/commentsIds.xml",
        "word/commentsExtensible.xml", "word/people.xml",
    ]:
        entries.pop(path, None)
    review_patterns = [re.compile("comments", re.I), re.compile("people", re.I)]
    if "word/_rels/document.xml.rels" in entries:
        entries["word/_rels/document.xml.rels"] = _remove_relationships(entries["word/_rels/document.xml.rels"], review_patterns).encode("utf-8")
    if "[Content_Types].xml" in entries:
        entries["[Content_Types].xml"] = _remove_content_types(entries["[Content_Types].xml"], [re.compile(r"/word/comments", re.I), re.compile(r"/word/people", re.I)]).encode("utf-8")
    if "word/settings.xml" in entries:
        doc = minidom.parseString(entries["word/settings.xml"])
        strip_review_markup_and_highlights(doc)
        entries["word/settings.xml"] = serialize_ooxml(doc).encode("utf-8")


def write_docx(data: dict, output_dir: str, plugin_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    template = _template_path(plugin_dir)
    if not os.path.exists(template):
        raise FileNotFoundError("No se encontró el machote integrado: " + template)
    out_path = os.path.join(output_dir, _filename(data))
    with zipfile.ZipFile(template, "r") as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}

    for path in ("word/document.xml", "word/header1.xml", "word/footer1.xml"):
        if path not in entries:
            continue
        entries[path] = apply_substitutions(entries[path], data, path).encode("utf-8")
    if "word/styles.xml" in entries:
        entries["word/styles.xml"] = normalizar_estilos(entries["word/styles.xml"]).encode("utf-8")
    clean_review_package(entries)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, content in entries.items():
            zout.writestr(name, content)
    return out_path
