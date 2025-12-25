# 🏰 Proyecto RPG – Lordship & Consequences

## Descripción general

Este proyecto es un **RPG 2D narrativo y táctico**, con exploración top-down y combate por turnos estilo *Fire Emblem*, centrado en **decisiones de gobierno**, **gestión de NPCs** y **consecuencias humanas ocultas**.

El jugador encarna a un **lord heredero** que recibe un pequeño pueblo independiente tras la muerte de su padre.  
Desde el primer momento deberá **asignar roles**, **reclutar soldados**, **administrar recursos**, **interpretar personas** y **enfrentar conflictos internos y externos**.

El foco del juego **NO** está en el grind ni en la optimización matemática, sino en:

> **Tomar decisiones con información incompleta y vivir sus consecuencias narrativas, económicas y militares.**

---

## 🎯 Pilares de diseño

- Decisiones > Mecánicas
- Información incompleta
- NPCs como personas, no como stats
- Consecuencias emergentes
- Moralidad oculta (nunca explícita)
- El mapa como narrativa
- Persistencia: lo que ocurre, permanece

---

## 🗺️ Mundo y exploración

- Exploración **top-down** con movimiento por tiles.
- Mundo compuesto por **mapas diseñados a mano en Tiled (JSON)**.
- Cada mapa puede contener:
  - capas de tiles (`ground`, `objects`, `collision`)
  - puertas entre mapas
  - object layers para:
    - `markers` (spawns, puntos narrativos)
    - `triggers` (eventos)
    - `puertas`
    - `interactuable`

### Herramientas
- **Tiled (export JSON)**
- **Python + Pygame**
- Engine propio (decisión consciente, sin RPG Maker)

---

## 🚪 Puertas y transiciones

Las puertas:
- se definen como `objectgroup` en Tiled
- usan propiedades (`map`, `spawn_x`, `spawn_y`, etc.)
- incluyen sistema **anti-rebote**
- bloquean reentrada hasta salir del área

Las transiciones son:
- **data-driven**
- reutilizables
- sin lógica hardcodeada por mapa

---

## 🧍‍♂️ NPCs (núcleo del juego)

Los NPCs son **entidades persistentes**, con identidad propia y memoria.

Un NPC puede:
- vivir en el mundo
- ser reclutado como soldado
- ser asignado a un rol civil
- abandonar el mapa
- traicionar al jugador
- morir permanentemente

### Importante
- **Tiled NO dibuja NPCs**
- Tiled solo define:
  - marcadores de spawn
  - triggers
  - zonas narrativas
- El engine instancia NPCs dinámicamente según el `GameState`

---

## 🎭 Representación visual de NPCs

Cada NPC tiene sprites **por contexto**, no por rol:

- `portrait` → retrato en diálogos
- `walk` → exploración
- `hurt` → estado herido
- `battle` → animaciones de combate

⚠️ **La apariencia NO cambia según rol o moralidad**  
Esto evita metajuego visual y refuerza la ambigüedad narrativa.

---

## 🧠 Sistema de moralidad (oculto)

El juego utiliza **7 ejes morales fundamentales**, definidos en JSON y compartidos por todo el sistema.

📄 `assets/data/morality_axes.json`

Ejemplos:
- Altruismo ↔ Avaricia
- Lealtad ↔ Ambición
- Compasión ↔ Crueldad
- Orden ↔ Pragmatismo
- Tradición ↔ Progreso
- Honor ↔ Utilitarismo
- Fe ↔ Escepticismo

### Principios clave
- El jugador **nunca ve números**
- No existen decisiones “buenas” o “malas”
- Los ejes no disparan acciones directas
- Las consecuencias emergen por acumulación

Ejemplos:
- un mercader avaricioso sube precios
- un soldado ambicioso traiciona en batalla
- un consejero cruel puede intentar asesinar al jugador

---

## 🏛️ Gobierno del pueblo

El pueblo es un **sistema vivo**, no un hub estático.

El jugador puede:
- asignar NPCs a trabajos
- elegir consejeros
- invertir dinero
- construir o mejorar edificios
- tomar decisiones políticas (impuestos, castigos, reformas)

Cada decisión:
- afecta la economía
- afecta NPCs específicos
- puede generar eventos narrativos
- puede escalar a conflictos mayores

---

## 🎬 Escena inicial: La Herencia

El juego comienza en el mapa `town_01`.

- El jugador aparece frente a su casa.
- Marian Vell (antiguo consejero del padre) está a su lado.
- Los otros 4 NPCs iniciales están **formados en fila**, esperando.

Marian informa:
- la muerte del padre
- la necesidad inmediata de gobernar
- la primera tarea: **asignar roles**

### Restricciones iniciales
- 2 soldados → se unen a la party
- 1 consejero
- 1 encargado de la tienda de armas
- 1 encargado de la posada

Al confirmar:
- consejero entra a la casa y desaparece del mapa
- encargados de tiendas caminan hacia la salida derecha y desaparecen
- soldados se unen al jugador

Los destinos finales existen conceptualmente, pero **los mapas interiores aún no están creados**.

---

## ⚔️ Combate (Fire Emblem-like)

- Combate táctico por turnos
- Mapas separados del overworld
- Unidades reclutadas = NPCs conocidos
- Muerte permanente
- Traición posible durante el combate

Las decisiones previas afectan directamente:
- lealtad
- comportamiento en batalla
- eventos de traición o sacrificio

---

## 🌍 Reinos enemigos y expansión

- El mundo reacciona al crecimiento del jugador
- Surgen reinos enemigos
- La expansión no es solo militar:
  - administración
  - legitimidad
  - conflictos internos

---

## 🏗️ Progresión del reino

El jugador puede:
- construir edificios
- mejorar infraestructura
- desbloquear sistemas narrativos
- introducir nuevos conflictos

Cada edificio:
- requiere NPCs adecuados
- puede fallar si se gestiona mal
- tiene consecuencias narrativas

---

## 🧩 Arquitectura técnica

### Lenguaje
- Python

### Motor
- Pygame
- Engine propio

### Estados principales
- `WorldState` → exploración y narrativa
- `BattleState` → combate táctico
- `PauseState`, etc.

### Persistencia
- `GameState` guarda:
  - flags de historia
  - party
  - estado de NPCs (rol, activo/offmap)
- Soporta guardado/carga

---

## 📁 Estructura del proyecto

project/
├─ assets/
│ ├─ maps/
│ ├─ sprites/
│ └─ data/
│ ├─ morality_axes.json
│ ├─ events/
│ ├─ dialogues/
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
│ ├─ game_state.py
│ └─ config.py
│
└─ main.py


---

## 📌 Estado actual del desarrollo

- ✔️ Engine base funcional
- ✔️ Mapas con Tiled
- ✔️ Puertas estables
- ✔️ Sistema de diálogo
- ✔️ Sistema de NPC persistente
- ✔️ Escena inicial diseñada e implementada parcialmente
- ✔️ Movimiento y despawn narrativo de NPCs
- ⚠️ Event runner JSON (en progreso)
- ⚠️ UI de asignación de roles (pendiente)

---

## 🧠 Filosofía final

Este juego busca que el jugador **interprete personas**, no sistemas.

Si el jugador puede:
- predecir siempre el resultado
- optimizar sin riesgo
- evitar dilemas humanos

entonces el diseño falló.

La ambigüedad es **intencional**.

---

## ✍️ Nota para futuras sesiones

Este README define:
- la visión del juego
- las reglas de diseño
- el estado técnico actual

Cualquier cambio debe:
- respetar estos pilares
- o redefinirlos explícitamente
