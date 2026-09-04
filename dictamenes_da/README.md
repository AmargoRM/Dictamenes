# Dictámenes-DA

Complemento QGIS 3.x creado a partir de `dictamen_generator_integrado_v10`.

## Cambios de esta versión

- Los calendarios vacíos ahora abren en el mes vigente, no en 1900/1990.
- La generación reutiliza el último análisis espacial cuando los datos no han cambiado, evitando recargar las capas GeoJSON pesadas.
- Panel lateral más angosto y compacto para no tapar el mapa.
- Entradas de fecha con calendario emergente y formato visible `dd/MM/aa`.
- Captura directa de coordenadas desde el mapa para Inicio, Final y puntos de control.
- Análisis espacial ejecutado como tarea de QGIS en segundo plano.
- Generación de Word a partir del machote original incluido en `assets/template/`, sustituyendo campos en el OOXML sin reconstruir el documento desde cero.

## Instalación

1. En QGIS: `Complementos > Administrar e instalar complementos > Instalar a partir de ZIP`.
2. Seleccione `dictamenes_da_qgis_plugin.zip`.
3. Active el complemento `Dictámenes-DA`.
4. Abra el panel con el icono o desde el menú `Dictámenes-DA`.

## Uso básico

1. Defina CRS de entrada.
2. Complete datos administrativos y fuentes.
3. Use `Capturar inicio`, `Capturar final` o `Capturar fila` y haga clic sobre el mapa.
4. Presione `Analizar` para completar ubicación, cuenca, hoja y suelo.
5. Presione `Generar Word` para crear el dictamen con el formato del machote.
