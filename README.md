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
- **Mapa de referencia automático** (Figura 1): fondo Google Híbrido, red hídrica de contexto, cuadrícula CRTM05 con marcas externas, escala automática, media página
- Simbología por tipo: nacientes/puntuales círculo azul; ríos/quebradas cruz (inicio verde, final verde oscuro); etiqueta a la izquierda
- Captura de coordenadas sin decimales (números enteros), con marcado en vivo sobre el mapa
- Botón para generar una capa temporal de puntos con nombre, tipo y número
- Capa de red hídrica simplificada incluida (`Red.hidrica.min.geojson`), etiquetada sobre la línea en azul e itálica
- Etiqueta de puntos igual al Cuadro 1 ("Fuente N - Rol (Punto X)")
- Escala del mapa en números cerrados, cubriendo siempre todos los puntos
- Selección de capas del proyecto para incluir en el mapa, con edición de simbología/etiquetas
- Leyenda automática de las capas activas en el mapa
- Corrección de orientación (EXIF) de las fotos para que no salgan rotadas

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
