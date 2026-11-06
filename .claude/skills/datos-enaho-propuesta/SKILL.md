---
name: datos-enaho-propuesta
description: Calcula y actualiza indicadores de la ENAHO del INEI por departamento (pobreza, pobreza juvenil, desempleo juvenil, jóvenes ocupados sin pensión e ingreso laboral de jóvenes de 18 a 29 años) para sustentar la sección del problema de una propuesta de proyecto. Úsala cuando pidan datos de la ENAHO o del INEI para una propuesta, actualizar data/enaho, agregar un indicador nuevo o cambiar de año de la encuesta.
argument-hint: [anio] [codigo-inei]
---

# Indicadores de la ENAHO para propuestas

La app lee `data/enaho/indicadores_<anio>.csv` y pone en la sección del problema las cifras del departamento
del proyecto, citadas como «ENAHO (INEI)». Esta skill genera y valida esa tabla.

## Pasos

1. Año y código: `$0` es el año (por defecto 2024) y `$1` el código del INEI (966 = 2024). Si piden otro año,
   busca su código en el portal de microdatos del INEI antes de seguir.
2. Revisa que existan `datos/enaho/<codigo>-Modulo34.zip`, `-Modulo02.zip` y `-Modulo05.zip`. Si faltan, bájalos:
   `https://proyectos.inei.gob.pe/iinei/srienaho/descarga/STATA/<codigo>-Modulo<NN>.zip`
   La carpeta `datos/` está en `.gitignore`: los microdatos nunca se suben al repo.
3. Corre exactamente:
   `python ${CLAUDE_SKILL_DIR}/scripts/indicadores.py --codigo <codigo> --anio <anio>`
4. Lee `data/enaho/validacion_<anio>.txt`. Si algún departamento difiere del INEI en más de 0.15 puntos, el script
   no guarda la tabla: detente y explica qué falló. No relajes la tolerancia para que pase.
5. Si es un año nuevo, primero agrega `referencias/pobreza_departamento_<anio>.csv` con las cifras oficiales del INEI.
6. Responde con un resumen de 3 a 5 cifras (nacional y el departamento que interese) y recuerda las advertencias.

## Reglas que no se discuten (están en el script)

- Toda cifra va ponderada: `factor07 × mieperho` para pobreza, `facpob07` para personas, `fac500a` para empleo.
- Solo residentes habituales: `(p204 == 1 & p205 == 2) | (p204 == 2 & p206 == 1)`.
- Departamento = `ubigeo[:2]` como texto, nunca por nombre. Lima (15) y Callao (07) van separados.
- Uniones con `validate="m:1"` y sin perder filas.

## Advertencias que debes repetir al usuario

- «Ocupados sin pensión» es una **aproximación** a la informalidad laboral, no la tasa oficial del INEI.
- Con muestras chicas (columna `muestra_jovenes` < 400), presenta la cifra como referencial.
- Fuente al citar: «INEI, ENAHO <anio>». Para agregar un indicador nuevo, lee primero `reference.md`.
