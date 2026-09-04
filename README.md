# Dictámenes-DA

Plugin de QGIS para generar dictámenes de cuerpo de agua (Dirección de Agua, Costa Rica).

## Funcionalidades

- Formulario nativo de QGIS con captura de coordenadas por clic en el mapa
- Análisis espacial automático: provincia, cantón, distrito, cuenca, hoja cartográfica, orden de suelo
- Biblioteca de descripciones técnicas por tipo de fuente
- Generación de documento Word sobre el machote oficial DA-UHSAN
- Soporte para múltiples fuentes dictaminadas por expediente
- **Guardar/Cargar formulario como JSON** para retomar dictámenes en progreso
- **Subir imagen por fuente**: se inserta automáticamente en "Figura 2. Cuerpo de agua en análisis"
- **Mapa de referencia automático** (Figura 1): fondo Google Híbrido, cuadrícula CRTM05 con marcas externas, escala automática, media página
- Captura de coordenadas sin decimales (números enteros)

## Instalación

Descargar el ZIP desde la sección [Releases](../../releases/latest) e instalar desde el administrador de complementos de QGIS:  
`Complementos → Administrar e instalar complementos → Instalar desde ZIP`.

## Requisitos

- QGIS 3.22 o superior

## Capas integradas

Las capas GeoJSON están incluidas en el plugin (vía Git LFS para los archivos grandes):

| Capa | Fuente |
|------|--------|
| Distritos, cantones, provincias | IGN Costa Rica |
| Cuencas hidrográficas | SINAC / MINAE |
| Hoja cartográfica 1:50 000 | IGN |
| Suelos | ITCR |

## Desarrollo

```
dictamenes_da/
├── __init__.py
├── dictamenes_da.py      # Punto de entrada del plugin
├── dockwidget.py         # Interfaz del formulario
├── docx_builder.py       # Generación del documento Word
├── layer_manager.py      # Análisis espacial con capas GeoJSON
├── map_tool.py           # Herramienta de captura de puntos en el mapa
├── icon.svg
├── metadata.txt
└── assets/
    ├── layers/           # Capas GeoJSON (archivos grandes vía Git LFS)
    └── template/         # Machote Word base
```
