# Guía de entrevista: gerentes de ONG como usuarios potenciales

Versión 2 (con MVP). Basada en "How to Talk to Users" de Y Combinator: preguntar por **lo que ya pasó**, no por opiniones sobre el futuro, y **mostrar el software solo al final**.

## Qué quiero aprender

| Hipótesis | Se confirma si… | Se cae si… |
|---|---|---|
| H1. Armar una propuesta técnica y económica cuesta muchas horas o dinero | Cuentan días-persona concretos o pagan a un consultor | "Lo hacemos en una tarde" |
| H2. Lo más difícil es que el presupuesto cuadre con el marco lógico y con las reglas del TdR | Recuerdan observaciones o rechazos por eso | Los rechazos son por otras razones (experiencia, contactos) |
| H3. Quieren que la propuesta sea "suya", no "hecha por IA" | Les preocupa el tono genérico o que el donante lo note | No les importa quién la escribe |
| H4. Pagarían por esto | Dan un monto y dicen quién aprueba el gasto | "Interesante" sin monto ni siguiente paso |

## Antes de la entrevista

- **Duración:** 35 a 40 minutos. Presencial o videollamada con pantalla compartida.
- **Lleva:** la app abierta en `localhost:8501`, una convocatoria elegida (por ejemplo el DAP de Australia) y esta guía.
- **Grabación:** pide permiso para grabar el audio. Puedes transcribirlo después con el propio Whisper de la app, que corre en tu laptop y no sube el audio.
- **Conflicto de interés:** dos de las tres personas son de tu ONG. Preséntalo como lo que es, una tarea del diplomado. No uses ni pidas documentos internos para el repo. En las notas, nada de nombres de personas ni de la organización.

**Frase de apertura (30 segundos):**

> "Es para el proyecto final de mi diplomatura en la PUCP. Estoy investigando cómo las organizaciones buscan fondos y arman sus propuestas. No te voy a vender nada; me sirve más que me cuentes cómo lo hacen de verdad, incluso lo que sale mal. ¿Puedo grabar el audio solo para mis notas? No pondré tu nombre ni el de la organización."

---

## Parte A. El problema (15 min): sin mostrar el software

### A1. Buscar convocatorias

1. ¿Cómo se enteraron de la **última** convocatoria a la que postularon? ¿Quién la encontró?
2. ¿Dónde buscan normalmente? (webs, correos, WhatsApp, REDINFOR, COEECI, contactos)
3. ¿Cuántas horas a la semana se van en buscar y filtrar? ¿Quién lo hace?
4. ¿Se les pasó alguna convocatoria buena por enterarse tarde? ¿Qué pasó?

### A2. Armar la propuesta

5. Cuéntame la **última propuesta** que armaron, de principio a fin. ¿Cuántas personas, cuántos días?
6. ¿Por dónde empiezan? ¿Usan una propuesta anterior como base? (señal para el modo "propuestas anteriores")
7. ¿Qué parte toma más tiempo: el diagnóstico, el marco lógico, los indicadores o el presupuesto?
8. ¿Cómo arman el presupuesto por actividad? ¿Excel propio, plantilla del donante, copiar de otra propuesta?
9. ¿Cómo revisan que cumpla el TdR (topes, contrapartida, gastos no elegibles)? ¿Quién lo revisa?
10. ¿Alguna vez les **observaron o rechazaron** una propuesta? ¿Por qué?
11. ¿Cuánto les cuesta una propuesta? Horas del equipo, o consultor externo: ¿cuánto cobra?
12. ¿Cuántas propuestas presentan al año y cuántas ganan, más o menos?

### A3. Uso actual de IA

13. ¿Ya usan ChatGPT u otra IA para esto? ¿Para qué parte exactamente?
14. ¿Qué no les gustó del resultado?
15. ¿Les preocuparía que el donante note que usaron IA? ¿Por qué?

---

## Parte B. Prueba del software (15 min): ellos manejan

Comparte pantalla o entrégales la laptop. **No expliques la app**: dales una tarea y observa.

> "Imagina que tu organización quiere postular a esta convocatoria. Usa esto como lo usarías de verdad y ve diciendo en voz alta lo que piensas."

| Paso | Qué observar (anota en silencio) |
|---|---|
| Feed de convocatorias | ¿Entienden qué es cada ficha? ¿Qué miran primero: monto, plazo, elegibilidad? |
| Botón "Generar propuesta" y lectura del TdR | ¿Confían en las reglas que extrajo? ¿Revisan algo a mano? |
| Elegir modo | ¿Cuál eligen primero y por qué? |
| Entrevista con voz | ¿Prefieren hablar o escribir? ¿Las preguntas se entienden? |
| Resultado: semáforo | ¿Entienden los ❌ y ⚠️? ¿Les sirve el aviso de "falta aporte propio"? |
| Word y Excel | ¿Abrirían el Word para editarlo? ¿El Excel se parece a cómo trabajan? |

**Preguntas después de usarlo:**

16. ¿Qué fue lo **más útil**? ¿Y lo que **sobra**?
17. ¿Cuál de los 3 modos usarías y en qué momento? (TdR, propuestas anteriores, entrevista)
18. Este borrador, ¿te ahorra trabajo o te da más trabajo corregirlo? ¿Cuántas horas te ahorraría?
19. ¿Sientes que la propuesta es **de tu organización**? ¿Qué le falta para que lo sea?
20. ¿Confiarías en el semáforo de reglas o lo revisarías igual a mano?
21. ¿Qué tendría que hacer para que lo usaras en la **próxima** convocatoria?

---

## Parte C. Negocio (5 min)

Primero lo que ya gastan, después el precio:

22. Hoy, ¿cuánto pagan (o pagarían) a un consultor por formular una propuesta?
23. Si esto les ahorra [las horas que dijeron], ¿cuánto sería un precio **razonable**? ¿A partir de qué precio sería **caro**? ¿Y tan barato que **no confiarías**?
24. ¿Prefieren pagar **por propuesta** o una **suscripción mensual**?
25. ¿Quién aprueba ese gasto en la organización? ¿Sale del presupuesto institucional o de un proyecto?

Hipótesis de precio que pruebo (no se las digas antes de la pregunta 23):

| Plan | Precio hipotético |
|---|---|
| Gratis | Feed diario de convocatorias |
| Por propuesta | S/ 150 por propuesta generada |
| ONG mensual | S/ 290 al mes, hasta 5 propuestas |

## Cierre (2 min)

26. ¿Te puedo escribir cuando tenga la siguiente versión para que la pruebes otra vez?
27. ¿A quién más me recomiendas preguntar? (otra ONG, un consultor, una red como COEECI)

---

## Preguntas extra según la persona

**Gerente de desarrollo económico** (formula y dirige proyectos)
- ¿Qué hace que una propuesta tuya gane? ¿Qué copian de propuestas ganadoras?
- ¿Cómo eligen los indicadores? ¿Alguna vez el donante les cambió la matriz?

**Gerente general** (finanzas y decisión de compra)
- ¿Cuántas horas de personal se van en formulación al año? ¿Se pagan con algún proyecto?
- ¿Qué errores de presupuesto les han costado dinero o una observación?
- Si el equipo pidiera comprar esta herramienta, ¿qué necesitarías ver para aprobarla?

**Especialista que formula para Fondoempleo** (norte del Perú)
- ¿Qué parte del Formato 02 y 03 de Fondoempleo te cuesta más?
- ¿Formulas para varias organizaciones? ¿Cuánto cobras por propuesta? (posible segmento: consultores)
- Si la app tuviera el formato exacto de Fondoempleo, ¿cuánto tiempo te ahorraría?

---

## Señales: buenas y malas

| Buena señal | Mala señal |
|---|---|
| Cuentan una historia concreta con fechas y cifras | Hablan en general: "a veces", "normalmente" |
| Ya pagan por esto (consultor, horas extra) | "Sería bueno tenerlo" sin costo actual |
| Piden usarlo en una convocatoria real | Elogios sin siguiente paso |
| Dan un precio y saben quién lo aprueba | "Depende" sin monto |

Los elogios no cuentan como validación. Lo que cuenta es **lo que ya hacen y lo que ya pagan**.

---

## Plantilla de notas (una por persona)

Guardar como `docs/research/entrevista_1.md`, `entrevista_2.md` y `entrevista_3.md`.

```
Fecha:
Perfil (anónimo): p. ej. "Gerente de desarrollo económico, ONG de Lima"
Medio: presencial / llamada / videollamada
Duración:

## El problema
Última propuesta (cuántas personas, cuántos días):
Parte más difícil:
Cómo revisan que cumpla el TdR:
Observaciones o rechazos y por qué:
Costo (horas, soles, consultor):
Propuestas al año / ganadas:
Uso actual de IA:

## Prueba del software
Modo que eligió y por qué:
Lo más útil:
Lo que sobra o confundió:
Horas que cree que ahorraría:
¿Siente la propuesta como propia?:

## Negocio
Precio razonable / caro / demasiado barato:
Por propuesta o mensual:
Quién aprueba el gasto:

## Frases textuales (2 o 3)
-

## Lo que me sorprendió

## Siguiente paso / a quién me recomendó
```

## Para el README después de las 3 entrevistas

Resumir en la sección **3. Problema** y **7. Modelo de negocio**:

- Horas o soles promedio por propuesta (cuánto les cuesta).
- Cómo lo resuelven hoy (Excel, Word, consultor, ChatGPT).
- La causa más común de observaciones o rechazos.
- Rango de precio que mencionaron y si prefieren pago por propuesta o mensual.
- Una frase textual por persona.
