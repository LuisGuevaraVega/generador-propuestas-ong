# Referencia: variables e indicadores

## Módulos usados (ENAHO 2024, código 966)

| Módulo | Archivo | Una fila por | Factor |
|---|---|---|---|
| 34 Sumaria | `sumaria-2024.dta` | hogar (33,691) | `factor07` (× `mieperho` para personas) |
| 02 Miembros del hogar | `enaho01-2024-200.dta` | persona (117,721; 108,664 residentes) | `facpob07` |
| 05 Empleo e ingresos | `enaho01a-2024-500.dta` (~190 MB) | persona de 14 años a más | `fac500a` |

Llaves: `conglome`, `vivienda`, `hogar` (+ `codperso` para personas), siempre como texto.

## Variables

| Variable | Módulo | Significado |
|---|---|---|
| `pobreza` | 34 | 1 pobre extremo, 2 pobre no extremo, 3 no pobre → `pobre = pobreza <= 2` |
| `p204`, `p205`, `p206` | 02, 05 | miembro del hogar / ausente 30 días / presente 30 días (filtro de residentes) |
| `p207` | 02, 05 | sexo: 1 hombre, 2 mujer |
| `p208a` | 02, 05 | edad en años cumplidos |
| `ocu500` | 05 | 1 ocupado, 2 desocupado abierto, 3 desocupado oculto, 4 no PEA |
| `p558a5` | 05 | 5 = no está afiliado a ningún sistema de pensiones, 0 = afiliado |
| `i524a1, d529t, i530a, d536, i538a1, d540t, i541a, d543, d544t` | 05 | componentes anuales del ingreso laboral (ocupación principal y secundaria, pagos en especie, autoconsumo y extraordinarios) |

La ENAHO 2024 publicada no incluye `ocupinf` (informalidad oficial); por eso se usa `p558a5` como aproximación.

## Indicadores de `data/enaho/indicadores_<anio>.csv`

| Columna | Definición | Población |
|---|---|---|
| `pobreza_pct` | % de personas en pobreza monetaria | todas |
| `pobreza_jovenes_pct` | % de jóvenes en pobreza monetaria | residentes de 18 a 29 años |
| `desempleo_jovenes_pct` | desocupados abiertos / (ocupados + desocupados abiertos) | 18 a 29 años |
| `ocupados_jovenes_sin_pension_pct` | % de ocupados sin afiliación a pensiones (proxy de informalidad) | ocupados de 18 a 29 años |
| `ingreso_laboral_mensual_jovenes_soles` | suma de componentes del ingreso laboral / 12 | ocupados de 18 a 29 años |
| `poblacion_jovenes` | personas de 18 a 29 años (expandido) | residentes |
| `muestra_jovenes` | casos sin expandir en el módulo 05 | 18 a 29 años |

`ccdd = "00"` es el total nacional.

## Cifras de control (2024)

Pobreza nacional 27.6 %; Lambayeque 14.0 %; Cusco 18.5 %; Cajamarca 45.0 %; Ica 6.0 %;
residentes habituales 108,664. Las 25 cifras oficiales están en `referencias/pobreza_departamento_2024.csv`.

## Para agregar un indicador

1. Busca la variable en el diccionario del módulo (PDF dentro del zip) y confirma sus códigos con `value_counts()`.
2. Agrégala a la lectura por trozos de `leer()`, calcula el indicador ponderado con `por_departamento()` y súmalo a `tabla`.
3. Documenta la definición en esta tabla y corre el script: la validación de pobreza debe seguir pasando.
