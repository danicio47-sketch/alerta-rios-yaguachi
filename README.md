# Alerta ríos de Yaguachi

Página pública con el caudal de los ríos del cantón San Jacinto de Yaguachi (Guayas, Ecuador) frente a sus periodos de retorno, la lluvia reciente y pronosticada, y los recintos expuestos.

**Referencial.** Es una estimación automática con modelos globales, no una alerta oficial del COE cantonal, la SNGR ni el INAMHI.

## Cómo funciona

- `generar.py` baja el caudal GloFAS v4 (Open-Meteo Flood API) de 8 ríos y la lluvia de Open-Meteo en 4 puntos, calcula el semáforo y escribe la página en `_site/`.
- `rios.json`, `umbrales.json` y `recintos.json` guardan lo que no cambia a diario: los puntos de cada río, los caudales de 2, 10 y 25 años (Gumbel sobre los máximos anuales 1997–2025 de la reanálisis GloFAS) y los 71 recintos con su población estimada (WorldPop 2020) y su exposición (HAND y distancia al río).
- `.github/workflows/actualizar.yml` corre el script a las 06:00 y a las 16:00 (hora de Ecuador), publica la página en GitHub Pages y guarda un resumen diario en `historial/`.

## Regla del semáforo

- Por río: el mayor entre el caudal de hoy y la mediana pronosticada de los próximos 7 días. Verde bajo Q2, amarillo desde Q2, naranja desde Q10, rojo desde Q25.
- El cantón toma el nivel del río más alto (sin contar ríos marcados como no fiables).
- Lluvia (la mayor, observada o pronosticada, en la cabecera o en el promedio de la cuenca): 50 mm en 24 h o 100 mm en 72 h suben a amarillo; 150 mm en 72 h con algún río sobre Q2 sube a naranja. Umbrales de prueba, a validar.

## Actualizar a mano

En la pestaña **Actions**, elegir "Actualizar alerta" y pulsar **Run workflow**.
