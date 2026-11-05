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

- **Gratis:** feed diario de convocatorias de desarrollo económico local en Perú.
- **Pro:** botón "Generar propuesta" que abre una entrevista guiada por secciones. La organización responde (por texto o voz) y aprueba cada sección: la propuesta es suya, la IA la ayuda a escribirla.
- Valida automáticamente las reglas del donante (topes, contrapartida, indicadores obligatorios) y estima el puntaje según la rúbrica pública.

Primer formato soportado: Fondoempleo (Formato 02 propuesta técnica y Formato 03 propuesta financiera). Reglas en [`data/reglas/fondoempleo_eat.json`](data/reglas/fondoempleo_eat.json).

## 5. Why now

_Por completar._

## 6. Demo

Por ahora corre solo en local:

```bash
pip install -r requirements.txt
cp .env.example .env   # y completar GEMINI_API_KEY
streamlit run app/streamlit_app.py
```

Flujo: feed de convocatorias → **✨ Generar propuesta** → leer el TdR → elegir modo
(borrador desde el TdR, desde propuestas anteriores o entrevista por texto/voz) →
semáforo de reglas del donante → descargar Word (técnica) y Excel (económica).

_Capturas y diagrama de arquitectura: por completar._

## 7. Modelo de negocio

_Por completar._

## 8. Herramientas del curso

| Herramienta | Sesión | Para qué la usa el producto | Dónde está |
|---|---|---|---|
| Scraping y APIs | 03 | Feed de convocatorias y descarga del TdR desde el enlace (PDF, Word, HTML, Google Drive) | `data/convocatorias/`, `ai/documentos.py` |
| LLM con salidas estructuradas | 08 | Extraer las reglas del TdR y redactar propuesta, matriz y presupuesto en JSON validado | `ai/esquemas.py`, `ai/generador.py`, `ai/llm.py` |
| RAG | 08 | Reutilizar ideas de propuestas anteriores de la organización, citando cada fragmento | `ai/documentos.py` (`Recuperador`), `ai/generador.py` |
| Voz a texto con Whisper | 13 | Responder la entrevista hablando; corre en la laptop, el audio no sale de ella | `ai/voz.py` |

## 9. Qué hizo el agente

Este repositorio se construye con Claude Code como co-founder técnico. _Detalle por completar al final del sprint._

## Datos

Solo datos públicos (bases de Fondoempleo, convocatorias publicadas) y casos de ejemplo sintéticos. No se usan datos personales ni documentos de ninguna organización.

## Licencia

MIT. Ver [LICENSE](LICENSE).
