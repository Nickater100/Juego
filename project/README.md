# 🏰 Proyecto RPG – Lordship & Consequences

## Descripción general

Este proyecto es un **RPG 2D narrativo y táctico**, con exploración top-down y combate por turnos estilo *Fire Emblem*, centrado en **decisiones de gobierno**, **gestión de NPCs** y **consecuencias humanas ocultas**.

El jugador encarna a un **lord heredero** que recibe un pequeño pueblo independiente.  
A partir de ese momento, deberá **gobernar, reclutar, administrar recursos, tomar decisiones morales ambiguas y enfrentar guerras**, tanto externas como internas.

El foco del juego NO está en el grind ni en la optimización numérica, sino en:

> **Tomar decisiones con información incompleta y vivir sus consecuencias narrativas, económicas y militares.**

---

## 🎯 Pilares de diseño

- **Decisiones > Mecánicas**
- **Información incompleta**
- **NPCs como personas, no como stats**
- **Consecuencias emergentes**
- **Moralidad oculta, nunca explícita**
- **El mapa como narrativa**

---

## 🗺️ Mundo y exploración

- El mundo está compuesto por **mapas diseñados a mano** en **Tiled**.
- Cada mapa:
  - tiene colisiones por capa
  - puertas que conectan mapas
  - capas de objetos para NPCs, eventos y triggers
- El jugador explora en vista **top-down**, con movimiento por tiles.

### Herramientas
- **Tiled (JSON)** para mapas
- Engine propio en **Python + Pygame**
- Sin RPG Maker (decisión consciente)

---

## 🚪 Puertas y mapas

Las puertas:
- están definidas en Tiled como **object layers**
- usan propiedades para indicar:
  - mapa destino
  - spawn
- incluyen sistema **anti-rebote** (lock hasta salir del área)

Esto permite:
- diseño data-driven
- cero hardcode de transiciones
- mapas reutilizables

---

## 🧍‍♂️ NPCs (núcleo del juego)

Los NPCs son **entidades persistentes** con identidad y memoria.

Cada NPC puede:
- ser reclutado como soldado
- ser asignado a un rol civil (mercader, herrero, consejero)
- abandonar, traicionar o manipular al jugador
- morir permanentemente

### Importante
- **Tiled NO dibuja NPCs**
- Tiled solo define:
  - posición
  - id
  - tipo
  - referencias a diálogos o roles
- El engine se encarga del render y la lógica

---

## 🧠 Sistema de moralidad (oculto)

El juego utiliza **7 ejes morales fundamentales**, definidos en JSON y compartidos por todo el sistema.

📄 `assets/data/morality_axes.json`

Ejemplos de ejes:
- Altruismo ↔ Avaricia
- Lealtad ↔ Ambición
- Compasión ↔ Crueldad
- Orden ↔ Pragmatismo
- Tradición ↔ Progreso
- Honor ↔ Utilitarismo
- Fe ↔ Escepticismo

### Principios clave
- El jugador **NUNCA ve números**
- No existen “buenas” o “malas” decisiones
- Las moralidades **no disparan acciones directas**
- Las consecuencias emergen por acumulación de tensiones

Ejemplo:
- un mercader avaricioso puede subir precios
- un soldado ambicioso puede traicionar en batalla
- un consejero cruel puede intentar asesinar al jugador

---

## 🏛️ Gobierno del pueblo

El pueblo es un **sistema vivo**, no un hub estático.

El jugador puede:
- asignar NPCs a trabajos
- elegir consejeros
- invertir dinero en edificios
- mejorar infraestructura
- decidir políticas (impuestos, castigos, reformas)

Cada decisión:
- afecta la economía
- afecta NPCs específicos
- genera consecuencias a corto y largo plazo

---

## ⚔️ Combate (Fire Emblem-like)

El combate:
- es **táctico, por turnos**
- ocurre en mapas separados
- utiliza unidades reclutadas (NPCs conocidos)

Características:
- muerte permanente
- traición posible en medio de la batalla
- decisiones previas influyen directamente en el combate

Ejemplo:
- un soldado con baja lealtad puede cambiar de bando
- un consejero puede provocar una batalla mortal interna
- perder ciertas batallas implica **game over narrativo**

---

## 🌍 Reinos enemigos y expansión

- El mundo reacciona al crecimiento del jugador
- Aparecen reinos enemigos
- La expansión no es solo militar:
  - administrar territorios
  - manejar conflictos internos
  - sostener legitimidad

---

## 🏗️ Progresión del reino

- El jugador puede construir o mejorar:
  - tiendas
  - forjas
  - defensas
  - edificios civiles
- Cada edificio:
  - desbloquea nuevas decisiones
  - introduce nuevos conflictos
  - requiere NPCs adecuados para funcionar bien

---

## 🧩 Arquitectura técnica (resumen)

### Lenguaje
- Python

### Motor
- Pygame
- Engine propio

### Estados principales
- `WorldState` → exploración y narrativa
- `BattleState` → combate táctico
- `PauseState`, etc.

### Filosofía
- Data-driven
- Estados desacoplados
- JSON para diseño, código para lógica

---

## 📁 Estructura del proyecto (simplificada)

project/
├─ assets/
│ ├─ maps/ # Mapas Tiled (JSON)
│ ├─ sprites/ # Sprites y retratos
│ └─ data/
│ ├─ morality_axes.json
│ ├─ dialogues/
│ ├─ events/
│ └─ buildings.json
│
├─ engines/
│ └─ world_engine/
│ ├─ world_state.py
│ ├─ map_loader.py
│ └─ collision.py
│
├─ core/
│ ├─ entities/
│ ├─ game_state.py # Flags, party, progreso
│ └─ config.py
│
└─ main.py


---

## 🧠 Filosofía final

Este proyecto busca que el jugador **no juegue a optimizar sistemas**, sino a **interpretar personas**.

Si el jugador puede:
- predecir perfectamente las consecuencias
- maximizar números visibles
- evitar dilemas reales

entonces el diseño falló.

La ambigüedad es **intencional**.

---

## 📌 Estado actual del desarrollo

- ✔️ Engine base funcional
- ✔️ Mapas con Tiled
- ✔️ Puertas y transiciones estables
- ✔️ Sistema de diálogo
- ✔️ Flags de historia
- ✔️ Diseño completo del sistema de moralidad

### Próximos hitos recomendados
1. Integrar NPCs data-driven desde Tiled
2. Asociar NPCs a ejes morales
3. Implementar primeras decisiones políticas
4. Combat MVP táctico
5. Primer arco narrativo completo

---

## ✍️ Nota para futuras sesiones

Este README define:
- **qué es el juego**
- **qué no es**
- **por qué está diseñado así**

Cualquier cambio debe respetar estos pilares, o redefinirlos explícitamente.
