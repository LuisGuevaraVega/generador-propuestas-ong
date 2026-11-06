# Generador de propuestas técnicas y económicas para ONG

> 🚧 En construcción: proyecto final de la Diplomatura de Ciencia de Datos para las Ciencias Sociales y la Gestión Pública (Q-Lab PUCP), noviembre de 2026.

## 1. One-liner

_Por definir._ Borrador: ayudamos a ONG y organizaciones de trabajadores a encontrar convocatorias y a co-crear propuestas técnicas y económicas que cumplen las bases del donante, mediante una entrevista guiada con IA.

## 2. Founder

**Luis Gabriel Guevara Vega**: especialista en monitoreo y evaluación de proyectos sociales. _(foto y detalle por completar)_

## 3. Problema

_Por completar con las 3 conversaciones de `docs/research/`._

Hipótesis: los equipos de ONG pierden días buscando convocatorias dispersas y armando propuestas técnicas (marco lógico, indicadores) y económicas (presupuesto por actividad) en Word y Excel, y las propuestas se observan por incoherencias o por no cumplir los topes de las bases.

## 4. Solución e insight

_Por completar._

- **Gratis:** feed diario de convocatorias de desarrollo económico local en Perú, con historial acumulado.
- **Pro:** botón "Generar propuesta" con tres modos:
  1. **Borrador desde el TdR:** lee el TdR de la convocatoria y propone un proyecto completo como guía.
  2. **Desde mis propuestas anteriores:** reutiliza ideas y estilo de propuestas pasadas (RAG), citando cada fragmento.
  3. **Entrevista guiada:** preguntas por sección, respondidas por texto o voz; la IA redacta solo con esas respuestas.
- **La propuesta es de la organización:** cada sección se edita o se regenera con una instrucción; la matriz y el
  presupuesto se editan en tablas. La "huella de autoría" (solo en la app) muestra de dónde salió cada pieza.
- **Reglas verificadas con código, no con el prompt:** topes del TdR y del formato base (financiamiento, contrapartida,
  reserva, administrativos, duración, personal, topes por rubro y gastos no elegibles), indicadores SMART y un
  **verificador de cifras** que marca todo número del borrador que no aparece en ninguna fuente.
- **Puntaje estimado** con los criterios de evaluación del propio TdR.
- **Datos públicos:** indicadores de la ENAHO 2024 por departamento para la sección del problema y tipo de cambio del BCRP.
- **Exportación:** Word (propuesta técnica) y Excel con fórmulas (propuesta económica), y como respaldo los
  Formatos 02 y 03 de Fondoempleo.

Formato base: inspirado en la guía de solicitud del BMZ para ONG ([Leitfaden zum Projektantrag](https://bengo.engagement-global.de/files/2_Mediathek/Mediathek_Microsites/bengo/Service/Dokumente/Handreichungen/de/leitfaden-projektantrag.pdf), nov 2025), en [`data/formatos/formato_base.json`](data/formatos/formato_base.json). Cuando hay TdR, sus reglas (monto, duración, contrapartida, topes) reemplazan a las del formato base. Reglas de Fondoempleo guardadas para un formato específico futuro en [`data/reglas/fondoempleo_eat.json`](data/reglas/fondoempleo_eat.json).

## 5. Why now

_Por completar._

## 6. Demo

Por ahora corre solo en local:

```bash
pip install -r requirements.txt
cp .env.example .env   # y completar GEMINI_API_KEY
streamlit run app/streamlit_app.py
```

Flujo: feed de convocatorias (con buscador y filtro de microfinanzas) → **✨ Generar propuesta** → asistente
de 2 pasos:
1. **Tu proyecto:** el TdR de la convocatoria se lee solo y se resume arriba (monto, duración, contrapartida,
   cierre); luego organización, idea, departamento y modo (borrador desde el TdR, desde propuestas anteriores
   o entrevista por texto/voz).
2. **Revisa y descarga:** qué corregir (reglas del donante, cifras a validar, puntaje), edición del texto por
   sección, matriz y presupuesto, y descarga en Word y Excel (formato base o Fondoempleo).

Pruebas automáticas (sin llamar a APIs): `python -m pytest` (24 pruebas).

Actualizar los datos de la ENAHO: skill de Claude Code `datos-enaho-propuesta`
(`.claude/skills/`), que baja los microdatos del INEI, calcula los indicadores y los valida
contra las cifras oficiales (pobreza 2024: 27.6 % nacional y los 25 departamentos exactos).

_Capturas y diagrama de arquitectura: por completar._

## 7. Modelo de negocio

_Precios por definir después de las conversaciones con usuarios._

Costo variable medido por la app (tokens de Gemini registrados en cada llamada, tabla de precios en
[`data/precios_modelos.json`](data/precios_modelos.json)):

| Acción | Llamadas | Costo aproximado |
|---|---|---|
| Generar una propuesta completa | 3 a 4 | US$ 0.02 a 0.08 (menos de S/ 0.30) |
| Auditoría del presupuesto y puntaje estimado | 2 | US$ 0.01 a 0.02 |
| Adaptar al formato Fondoempleo | 1 | US$ 0.01 a 0.03 |

La voz (Whisper) corre en la laptop del usuario: costo de API cero.

## 8. Herramientas del curso

| Herramienta | Sesión | Para qué la usa el producto | Dónde está |
|---|---|---|---|
| Scraping y APIs | 03 | Feed de convocatorias y descarga del TdR desde el enlace (PDF, Word, HTML, Google Drive) | `data/convocatorias/`, `ai/documentos.py` |
| LLM con salidas estructuradas | 08 | Extraer las reglas del TdR y redactar propuesta, matriz y presupuesto en JSON validado | `ai/esquemas.py`, `ai/generador.py`, `ai/llm.py` |
| RAG | 08 | Reutilizar ideas de propuestas anteriores de la organización, citando cada fragmento | `ai/documentos.py` (`Recuperador`), `ai/generador.py` |
| Voz a texto con Whisper | 13 | Responder la entrevista hablando; corre en la laptop, el audio no sale de ella | `ai/voz.py` |
| APIs públicas (BCRP) | 03 / 04 | Tipo de cambio diario para convertir el presupuesto a la moneda del TdR y a soles | `ai/tipo_cambio.py` |
| Skills de Claude Code con la ENAHO | 16 | Indicadores de pobreza, desempleo e informalidad juvenil por departamento, validados contra el INEI | `.claude/skills/datos-enaho-propuesta/`, `ai/enaho.py` |
| Evaluación de productos de datos | 12 | Pruebas automáticas, verificador de cifras y puntaje con los criterios del donante | `tests/`, `ai/verificador.py`, `ai/auditor.py` |

## 9. Qué hizo el agente

Este repositorio se construye con Claude Code como co-founder técnico. _Detalle por completar al final del sprint._

## Datos

Solo datos públicos (bases de Fondoempleo y del BMZ, convocatorias publicadas, ENAHO 2024 agregada por departamento,
tipo de cambio del BCRP) y casos de ejemplo sintéticos. Los microdatos de la ENAHO (`datos/`) y el historial de
propuestas (`historial/`) no se suben al repo. No se usan datos personales ni documentos de ninguna organización.

## Licencia

MIT. Ver [LICENSE](LICENSE).
