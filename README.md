# 📋 ObraPasaLista v1.1 — Análisis Real y Hoja de Ruta

**Sistema de Gestión de Partes Diarios de Obra**
**Versión analizada:** 1.1 (código real del repo, no una versión teórica)
**Stack:** Python 3 | Flask | SQLite3 (WAL) | `render_template_string` monolítico
**Fecha:** Julio 2026

> Este documento sustituye a `Analisis-Definitivo-ObraPasaLista.md` (v1.0), que describía
> un esquema y unos problemas que ya no coinciden con el código real. Todo lo de aquí está
> verificado línea a línea contra `src/app.py`.

---

## 🎯 OBJETIVO DEL SISTEMA

Aplicación web local (single-user, `127.0.0.1:5000`) para control diario y mensual de
operarios en obras de construcción: empresas, subcontratas, personas, rangos/categorías
laborales, partidas de obra, partes diarios con meteorología, y cierre mensual con
snapshot para facturación.

---

## 🗄️ ESQUEMA DE DATOS REAL (verificado en `app.py`)

```sql
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;

CREATE TABLE empresa(
    id_empresa INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    estado TEXT NOT NULL DEFAULT 'activa');

CREATE TABLE empresa_relacion(   -- subcontratas
    id_rel INTEGER PRIMARY KEY AUTOINCREMENT,
    id_empresa_principal   INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
    id_empresa_subcontrata INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
    tipo_relacion TEXT NOT NULL DEFAULT 'subcontrata',
    fecha_inicio DATE, fecha_fin DATE,
    UNIQUE(id_empresa_principal, id_empresa_subcontrata));

CREATE TABLE rango(              -- Peón / Oficial 2ª / Oficial 1ª / Capataz / Encargado
    id_rango INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '');

CREATE TABLE persona(
    id_persona INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL, apellido1 TEXT NOT NULL, apellido2 TEXT NOT NULL DEFAULT '',
    dni TEXT NOT NULL UNIQUE,
    id_empresa INTEGER REFERENCES empresa(id_empresa) ON UPDATE CASCADE ON DELETE SET NULL,
    oficio TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'activa');

CREATE TABLE persona_rango(       -- histórico de rango por fechas
    id_pr INTEGER PRIMARY KEY AUTOINCREMENT,
    id_persona INTEGER NOT NULL REFERENCES persona(id_persona) ON DELETE CASCADE,
    id_rango   INTEGER NOT NULL REFERENCES rango(id_rango)   ON DELETE RESTRICT,
    fecha_inicio DATE NOT NULL, fecha_fin DATE);

CREATE TABLE obra(
    id_obra INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'activa');

CREATE TABLE obra_empresa(        -- relación N:M obra-empresa
    id_oe INTEGER PRIMARY KEY AUTOINCREMENT,
    id_obra    INTEGER NOT NULL REFERENCES obra(id_obra)       ON DELETE RESTRICT,
    id_empresa INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
    rol TEXT NOT NULL DEFAULT 'principal',
    UNIQUE(id_obra, id_empresa));

CREATE TABLE partida_obra(
    id_partida INTEGER PRIMARY KEY AUTOINCREMENT,
    id_obra INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE CASCADE,
    codigo TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '',
    UNIQUE(id_obra, codigo));

CREATE TABLE config(
    id_config INTEGER PRIMARY KEY,
    limite_horas_dia REAL NOT NULL DEFAULT 24.0 CHECK(limite_horas_dia>0));

CREATE TABLE diario(              -- 1 diario = 1 obra + 1 fecha (NO por empresa)
    id_diario INTEGER PRIMARY KEY AUTOINCREMENT,
    id_obra INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE RESTRICT,
    fecha DATE NOT NULL,
    meteo_estado  TEXT NOT NULL DEFAULT 'soleado',
    meteo_detalle TEXT NOT NULL DEFAULT '',
    meteo_temp_c  REAL,
    UNIQUE(id_obra, fecha));

CREATE TABLE diario_linea(        -- la empresa vive AQUÍ, no en diario
    id_dl INTEGER PRIMARY KEY AUTOINCREMENT,
    id_diario  INTEGER NOT NULL REFERENCES diario(id_diario)       ON DELETE CASCADE,
    id_empresa INTEGER NOT NULL REFERENCES empresa(id_empresa)     ON DELETE RESTRICT,
    id_persona INTEGER NOT NULL REFERENCES persona(id_persona)     ON DELETE RESTRICT,
    id_rango   INTEGER          REFERENCES rango(id_rango)         ON DELETE SET NULL,
    id_partida INTEGER          REFERENCES partida_obra(id_partida)ON DELETE SET NULL,
    asunto TEXT NOT NULL DEFAULT '',
    horas REAL NOT NULL DEFAULT 0 CHECK(horas>=0 AND horas<=24));

CREATE TABLE mensual(
    id_mensual INTEGER PRIMARY KEY AUTOINCREMENT,
    id_obra    INTEGER NOT NULL REFERENCES obra(id_obra)       ON DELETE RESTRICT,
    id_empresa INTEGER NOT NULL REFERENCES empresa(id_empresa) ON DELETE RESTRICT,
    mes TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'abierto',
    UNIQUE(id_obra, id_empresa, mes));

CREATE TABLE mensual_persona(     -- snapshot congelado, 31 columnas fijas d1..d31
    id_mp INTEGER PRIMARY KEY AUTOINCREMENT,
    id_mensual INTEGER NOT NULL REFERENCES mensual(id_mensual) ON DELETE CASCADE,
    id_persona INTEGER NOT NULL REFERENCES persona(id_persona) ON DELETE RESTRICT,
    id_rango   INTEGER          REFERENCES rango(id_rango)     ON DELETE SET NULL,
    id_empresa INTEGER          REFERENCES empresa(id_empresa) ON DELETE SET NULL,
    nom_c TEXT NOT NULL, ap1_c TEXT NOT NULL, ap2_c TEXT NOT NULL DEFAULT '',
    dni_c TEXT NOT NULL, rango_cache TEXT NOT NULL DEFAULT '',
    empresa_cache TEXT NOT NULL DEFAULT '', es_subcontrata INTEGER NOT NULL DEFAULT 0,
    d1 REAL, d2 REAL, ..., d31 REAL,
    total_mes REAL NOT NULL DEFAULT 0);
```

**Diferencia clave respecto al análisis v1.0 anterior:** la empresa NO cuelga de `diario`
sino de `diario_linea`. Esto es justo lo que aquel documento recomendaba en su sección
"Cambio de Empresa a Mitad de Mes" — **ya está resuelto** en tu diseño real.

---

## 🏗️ ARQUITECTURA REAL

Un único archivo `app.py` (ahora ~1840 líneas), sin blueprints, con vistas que devuelven
`render_template_string(BASE + "...")`. 44 rutas agrupadas así:

| Módulo | Rutas | Función |
|---|---|---|
| Empresas | `/empresas/`, `/empresas/nueva`, `/editar`, `/eliminar` | CRUD + baja lógica |
| Subcontratas | `/subcontratas/*` | Relación empresa principal ↔ subcontrata |
| Rangos | `/rangos/*` | Categorías laborales (Peón…Encargado) |
| Personas | `/personas/*` | CRUD, histórico de rango vía `persona_rango` |
| Obras | `/obras/*`, `add-empresa`, `add-partida` | CRUD + empresas participantes + partidas |
| Diario | `/diario/*`, `/arrastrar`, `/meteo` | Parte diario, arrastre, líneas, clima |
| Mensual | `/mensual/*`, `/cerrar`, `/reabrir`, `/csv` | Snapshot mensual + export |
| Backup | `/backup/*` | Crear / restaurar `.db` |
| Config | `/config/` | Límite de horas/día |

Esto ya va más allá de lo que planteaba el documento anterior (que solo hablaba de
5 blueprints genéricos): tu app real ya cubre subcontratas, rangos históricos y partidas
de obra, que ni se mencionaban antes.

---

## ⚙️ LÓGICA DE NEGOCIO REAL

### Arrastre (`diario_arrastrar`)
Busca el diario anterior de la **misma obra** (no filtra por empresa, porque la empresa
ahora es por línea), copia cada línea que no exista ya en el diario destino, con
`horas=0` y resolviendo el rango vigente de la persona en la fecha (`get_rango_activo`).
**No implementado:** la alerta de "han pasado más de 3 días" que proponía el documento
anterior — es una mejora pendiente, no un bug.

### Validación de horas (`chk_horas`)
Suma las horas ya registradas de la persona ese día (a través de todos los diarios) y
rechaza con un `ValueError` legible si se supera `config.limite_horas_dia`. Correcto y
ya implementado.

### Bloqueo de mes cerrado (`chk_mes_cerrado`)
Se comprueba en cada inserción de línea. Si el `mensual` de esa obra+empresa+mes está en
estado `cerrado`, lanza excepción y no deja escribir. Ya implementado.

### Cierre de mes (`mensual_cerrar`)
Borra el snapshot previo, recalcula filas con `_calcular_filas_mensual` y hace un
`INSERT` por persona con las 31 columnas de días + `total_mes`. Todo ocurre entre
sentencias sin `db.commit()` intermedio → como el conector `sqlite3` de Python abre
una transacción implícita en el primer `INSERT/UPDATE/DELETE`, esto **ya es atómico**
de facto (un solo `commit()` al final). El "riesgo de snapshot parcial" que señalaba
el documento anterior no aplica tal cual está el código.

### Rango vigente (`get_rango_activo`) y subcontratas (`get_subcontratas`)
Resuelven histórico de categoría por fechas y cadena de subcontratación. Funcionalidad
que el documento anterior ni contemplaba.

---

## 🔥 PROBLEMAS REALES DETECTADOS (verificados, no teóricos)

| # | Problema | Evidencia | Gravedad |
|---|---|---|---|
| 1 | `.gitignore` es de un proyecto Java/IntelliJ | No ignora `.venv/`, `__pycache__/`, `app.db`, `build/` | 🔴 Alta |
| 2 | `app.db` con datos reales de obra subido al repo | `src/app.db`, 106 KB, trackeado | 🔴 Alta (privacidad) |
| 3 | Carpeta `build/` de PyInstaller subida entera | ~15 MB de binarios/artefactos regenerables | 🟡 Media (peso del repo) |
| 4 | Nombre de archivo real ≠ el que esperan `Launcher.py` / instalador | `"ObraPasaLista v1.1. -- app.py"` vs `app.py` esperado | 🔴 Alta (la app no arranca vía Launcher tal como está subida) |
| 5 | `secret_key` hardcodeada | `app.secret_key = 'opl-v1.1-local-2026'` | 🟢 Baja (app local, no expuesta) |
| 6 | Monolito de ~1840 líneas, un solo archivo | 44 rutas + `render_template_string` inline | 🟡 Media (mantenibilidad) |
| 7 | Sin alerta de ">3 días" en el arrastre | No existe ese check en `diario_arrastrar` | 🟢 Baja (mejora opcional) |
| 8 | Sin tabla `schema_version` para migraciones futuras | La migración v1.0→v1.1 está hardcodeada con `ALTER TABLE` idempotentes | 🟡 Media (a futuro, cuando haya v1.2) |

Los puntos 1–4 son los que de verdad importan ahora mismo y están resueltos en la
"Parte 1" que te acabo de dar (gitignore + comandos git + renombrado).

---

## ✅ LO QUE YA ESTÁ BIEN HECHO (no lo toques)

- `PRAGMA foreign_keys=ON` + `PRAGMA journal_mode=WAL` en cada conexión.
- `row_factory = sqlite3.Row` para acceso por nombre de columna.
- Consultas parametrizadas (`?`) en absolutamente todo lo revisado — sin inyección SQL.
- Comandos `flask --app app init-db` / `upgrade-db` con migración real v1.0→v1.1.
- Soft delete en empresa/persona (`estado`), histórico de rango por fechas.
- Página de backup/restauración de `.db` ya funcionando.
- Exportación CSV con cabeceras de obra/empresa/mes.
- `requirements.txt` presente (`flask>=2.3.0`).

---

## 📝 ROADMAP PRIORIZADO (v1.2)

### Fase 0 — Higiene de repo (ya cubierta arriba)
- [x] `.gitignore` Python correcto
- [x] Sacar `app.db` y `build/` del tracking
- [x] Renombrar a `src/app.py`
- [ ] `secret_key` desde variable de entorno

### Fase 1 — Robustez de negocio (esfuerzo bajo-medio)
- [ ] Alerta ">3 días" en `diario_arrastrar`
- [ ] Tabla `schema_version` para futuras migraciones
- [ ] Diferenciar horas normales/nocturnas/extra si vas a facturar distinto (`tipo_hora`)

### Fase 2 — Mantenibilidad (esfuerzo alto, opcional)
- [ ] Separar en blueprints (`empresas`, `personas`, `obras`, `diario`, `mensual`, `backup`)
- [ ] Mover los `render_template_string` a plantillas Jinja reales en `templates/`
- [ ] Tests básicos (arrastre, límite de horas, bloqueo de mes cerrado)

### Fase 3 — Distribución
- [ ] Verificar que `compilar_exe_obra_pasalista.bat` (PyInstaller) sigue apuntando a `app.py` tras el renombrado
- [ ] Actualizar `instalador_obra_pasalista_linux.sh` para que ya no busque el nombre viejo `"ObraPasaLista v1.0 - app.py"` (con el rename a `app.py` el `find` de fallback ya funciona, pero limpia la referencia)

---

## ✅ CONCLUSIÓN

Tu v1.1 ya está considerablemente más avanzada de lo que reflejaba el análisis anterior:
subcontratas, rangos históricos, partidas de obra y meteorología ya están implementados
y bien resueltos a nivel de esquema. Los problemas reales no eran de lógica de negocio,
sino de higiene de repositorio (gitignore, datos subidos, nombre de archivo) — ya
solucionados en la Parte 1. Lo que queda es opcional: pulir mantenibilidad y algunos
detalles menores de UX en el arrastre.

**Autor:** Revisión basada en lectura directa del código fuente real (`src/app.py`, `Launcher.py`, `.gitignore`, `instalador_obra_pasalista_linux.sh`) del repo `RecklessCat55/ObraPasaLista`, julio 2026.