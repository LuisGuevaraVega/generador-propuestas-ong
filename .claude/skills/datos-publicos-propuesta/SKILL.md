---
name: datos-publicos-propuesta
description: Genera y valida las tablas de datos públicos del INEI por departamento (ENDES: anemia, desnutrición crónica, CRED, salud materna, violencia de género, agua y saneamiento; ENAHO: pobreza extrema, ruralidad, jefatura femenina, secundaria completa en jóvenes) que la app elige según el tema de cada convocatoria. Úsala cuando pidan más datos públicos o del INEI para una propuesta, actualizar data/contexto, cambiar de año o agregar un indicador o una fuente nueva.
argument-hint: [anio] [codigo-enaho]
---

# Datos públicos por departamento para propuestas

La app lee `data/contexto/*.csv` (formato largo: `ccdd, departamento, tema, indicador, valor, unidad, fuente,
anio, referencial, nota`) y `ai/contexto_publico.py` elige los indicadores cuyo `tema` calza con la convocatoria
y la idea (por ejemplo, "anemia" o "niños" activa *nutrición e infancia*). Pobreza y territorio van siempre.
Complementa la skill `datos-enaho-propuesta` (pobreza y empleo juvenil), que no se toca.

## Pasos

1. Año: `$0` (por defecto 2024). Código de la ENAHO: `$1` (966 = 2024).
2. **ENDES** (cuadros oficiales del INEI, no se recalcula nada):
   `python ${CLAUDE_SKILL_DIR}/scripts/endes.py --anio <anio>`
   Baja el informe «Indicadores de Resultados de los Programas Presupuestales» y copia el valor del año de
   cada cuadro de `CUADROS`. Si el INEI cambió la numeración de páginas de un año a otro, actualiza `CUADROS`
   con el índice del PDF (página impresa; el PDF va 2 páginas adelante).
3. **ENAHO ampliada** (microdatos; necesita los módulos 34, 02 y 03 en `datos/enaho/`):
   `python ${CLAUDE_SKILL_DIR}/scripts/enaho_ampliada.py --codigo <codigo> --anio <anio>`
   Si faltan módulos, bájalos de `https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/<codigo>-Modulo<NN>.zip`.
   `datos/` está en `.gitignore`: los microdatos nunca se suben.
4. Si un script termina con «VALIDACIÓN FALLIDA», no se guardó nada: detente y explica qué no cuadró.
   No relajes las tolerancias para que pase.
5. Corre `python -m pytest -q` y responde con 3 a 5 cifras (nacional y el departamento que interese).

## Validaciones (están en los scripts)

- ENDES: deben estar los 25 departamentos y el total; cada valor debe caer dentro de su intervalo de
  confianza; el total nacional de anemia y desnutrición debe coincidir con `REFERENCIA` (cifras del INEI).
- ENAHO: la pobreza extrema nacional debe coincidir con el INEI (`REFERENCIA`, tolerancia 0.15 puntos).
  Mismas reglas que la skill de la ENAHO: pesos, residentes habituales y departamento por `ubigeo`.

## Advertencias que debes repetir al usuario

- Las cifras de la ENDES entre paréntesis en el informe (muestra chica) quedan con `referencial = 1`.
- En la ENDES, Lima = Lima Metropolitana (43 distritos); la violencia de los últimos 12 meses es el promedio 2023-2024.
- Ruralidad, jefatura femenina, secundaria completa y la pobreza extrema por departamento son **cálculo propio**
  con microdatos (el INEI publica la pobreza extrema departamental solo por grupos).
- Para agregar un indicador: súmalo a `CUADROS` (ENDES) o a `indicadores` (ENAHO) con su `tema`; si el tema es
  nuevo, agrega sus palabras clave en `TEMAS` de `ai/contexto_publico.py` y una prueba en `tests/`.
