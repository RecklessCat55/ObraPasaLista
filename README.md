# Control de Personal en Obra — Flask + SQLite (On-Premise)

Aplicación web local (on-premise) para jefes de obra que necesitan controlar el personal de subcontratas e industriales, replicando y mejorando las hojas mensuales de control que se manejan en papel.

La app corre en **local**, sin servidor externo ni multiusuario: un portátil en obra con Python 3, Flask y SQLite como motor transaccional embebido. [web:16][web:152]

---

## Objetivos funcionales

- **RF1 – Diario por fecha**  
  - Registro diario por obra y fecha (parte de actividades), con fecha dinámica (`DD-MM-AAAA`).  

- **RF2 – Archivo diario vinculado a mensual**  
  - Cada día se crea un “archivo diario” vinculado a un mensual por obra+empresa.  
  - Las horas del diario alimentan el mensual de forma automática.

- **RF3 – Obras y empresas**  
  - Base de datos de obras (`obra`) relacionando empresas participantes (`obra_empresa`).  
  - Consulta de empresas participantes en cada obra.

- **RF4 – Empresas y personal**  
  - Empresas (`empresa`) con estado (`activa`, `finalizada`, `baja`).  
  - Personas (`persona`) asociadas a empresa, con estado (`activa`, `inactiva`) para preservar histórico aunque se desvinculen.

- **RF5 – Personas**  
  - Persona definida por: nombre, apellidos, DNI, empresa actual y oficio (opcional).  
  - Selección de empresa vía `select` para evitar duplicados/errores de entrada.

- **RF2.x – Lógica diaria y mensual**  
  - RF2.1: En el diario se registran líneas con empresa + persona + asunto + horas, con opción de copiar el último diario anterior (arrastre inteligente) para tareas repetitivas.  
  - RF2.2: Registro de horas trabajadas por persona, con límite diario configurable.  
  - RF2.3: Mensual por obra+empresa y mes.  
  - RF2.4: Un único mensual por empresa y obra en cada mes.  
  - RF2.4.1: Campos: Nombre y apellidos, DNI, días del mes con horas trabajadas; todo derivado de diarios.

---

## Arquitectura técnica

### Stack

- **Backend**: Python 3 + Flask. [web:152][web:168]
- **BD**: SQLite (fichero `app.db` en local).  
  - Foreign keys activados vía `PRAGMA foreign_keys = ON` en cada conexión. [web:24][web:20][web:160]  
  - Constraints (`CHECK`, `UNIQUE`, FKs) para garantizar integridad referencial.

### Diseño de datos (resumen)

- `empresa`  
  - Maestro de empresas, con `estado` y soft delete (`deleted_at`).

- `persona`  
  - Maestro de personas: nombre, apellidos, DNI (único), empresa actual (`id_empresa`), oficio opcional, estado (`activa/inactiva`).  

- `obra`  
  - Maestro de obras con código único (ej. 2516) y nombre.

- `obra_empresa`  
  - Relación de participación de empresas en obras (principal, subcontrata, etc.).

- `config`  
  - Configuración global: `limite_horas_dia` (REAL, por defecto 24.0, ajustable vía UI).

- `diario`  
  - Parte diario por obra y fecha, estado (`abierto/cerrado`).

- `diario_linea`  
  - Líneas del diario: empresa, persona, asunto, horas.  
  - Horas almacenadas como `REAL` y sujetas a `CHECK(horas >= 0 AND horas <= 24)`.

- `mensual`  
  - Parte mensual por obra, empresa y mes (`YYYY-MM`), con estado (`abierto/cerrado`).

- `mensual_persona`  
  - Snapshot congelado de personas en el mensual: caché de nombre y DNI, horas por día (`dia_1..dia_31`) y `total_mes`.

---

## Lógica de negocio clave

### Límites de horas diarias

- Límite diario configurable en `config.limite_horas_dia` (por defecto 24.0 h).  
- Antes de guardar una línea de diario (`diario_linea`), la app suma todas las horas del día para esa persona (across obras y empresas) y bloquea si `total_existente + horas_nueva > limite_horas_dia`. [web:77][web:80]

### Arrastre temporal inteligente (copiar último diario)

- Al crear el diario de hoy para una obra:  
  - Se busca el último diario anterior con líneas para esa obra.  
  - Se ofrece copiar personas y asuntos del día anterior, con horas iniciales a 0 y texto editable.  
- Se evita copiar más allá del último día trabajado sin confirmación, para no arrastrar errores en lunes/festivos.

### Cierre de mes y snapshot

- El mensual comienza en estado `abierto`.  
- Botón “Cerrar mes”:
  - Calcula horas por persona y día desde los diarios.  
  - Inserta snapshot en `mensual_persona` (caché de nombres/DNI y horas en REAL).  
  - Calcula `total_mes`.  
  - Marca `mensual.estado = 'cerrado'`.  
- Tras cierre:
  - No se permite modificar diarios de ese mes para esa obra+empresa.  
  - El snapshot congela todo, incluso nombres y DNIs (histórico legal).

### Formato de horas

- Internamente: horas en decimal (`REAL`). [web:104][web:108]  
- En UI y CSV:
  - Conversión a `HH:MM` con redondeo de minutos (`round`).  
  - Totales mensuales también en `HH:MM` (hurra para Excel).

---

## Backup y restauración (borrón y cuenta nueva)

La app incluye un módulo de backup con la Online Backup API de SQLite. [web:3][web:30][web:28][web:179]

### Backup

- Carpeta `backups/` junto a `app.db`.  
- Botón “Crear backup”:
  - Usa `sqlite3.Connection.backup()` para crear un snapshot consistente en caliente. [web:3][web:28][web:179]  
  - Nombre de fichero tipo:  
    - `backup_YYYYMMDD_HHMM_{CODIGO_OBRA}_{NOMBRE_OBRA_NORMALIZADO}.db`  
    - Normalización: mayúsculas + `_`, sin espacios ni acentos.

### Restore

- Pantalla que lista backups disponibles.  
- Botón “Restaurar backup”:
  - Muestra **warning** claro:  
    - “Restaurar este backup reemplazará todos los datos actuales. Es un borrón y cuenta nueva. Los cambios posteriores se perderán.”  
  - Copia el backup seleccionado sobre `app.db` (con la app parada o tras cerrar conexión). [web:22][web:30][web:156]  

---

## Estructura del proyecto

```text
app/
  app.py          # Arranque Flask, registro de blueprints
  db.py           # get_db, close_db, init_db, PRAGMA foreign_keys=ON
  schema.sql      # Modelo de datos completo (DDL)
  blueprints/
    config_bp.py  # Límite diario y configuración global
    maestros_bp.py# Empresas, personas, obras, obra_empresa
    diario_bp.py  # Partes diarios, validación de límite, arrastre
    mensual_bp.py # Cierre de mes, snapshot, export CSV
    backup_bp.py  # Backup y restauración
  templates/
    base.html
    config.html
    empresas.html
    personas.html
    obras.html
    diario.html
    mensual.html
    backup.html
    faq.html
  static/
    css/
    js/
backups/
  backup_YYYYMMDD_HHMM_XXXX_YYYY.db
```

---

## Cómo arrancar la app

1. Clonar el repo:

   ```bash
   git clone https://github.com/tuusuario/control-personal-obra.git
   cd control-personal-obra/app
   ```

2. Crear y activar entorno virtual:

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/macOS
   # o .\venv\Scripts\activate en Windows
   ```

3. Instalar dependencias:

   ```bash
   pip install flask
   ```

4. Inicializar la base de datos:

   ```bash
   flask --app app init-db
   ```

   (Siguiendo el patrón del tutorial de Flask para bases de datos.) [web:152][web:166][web:176]

5. Arrancar la app en local:

   ```bash
   flask --app app run
   ```

6. Abrir en el navegador:

   - `http://127.0.0.1:5000/`

---

## Preguntas frecuentes (FAQ)

La UI incluye una página de FAQ que responde:

- ¿Qué es el límite diario y cómo se configura?  
- ¿Qué significa “cerrar mes” y por qué no se puede modificar después?  
- ¿Cómo funciona el backup y qué implica restaurar un backup (borrón y cuenta nueva)?  
- ¿Por qué las horas se ven como `HH:MM` en lugar de decimales?  
- ¿Qué pasa si una persona cambia de empresa a mitad de mes?  
- ¿Por qué no puedo borrar una empresa/persona con partes históricos asociados?

---

## Puntos críticos por resolver (para futuras versiones)

Esta V1 está diseñada para ser **coherente y usable**, pero no perfecta. Áreas claras para V1.x / V2.0:

- Correcciones de errores en meses ya cerrados (snapshot inmutable).  
- Registro de cambios en `limite_horas_dia` (hoy no se audita).  
- Mejora del modelo de horas (tipos: normales, nocturnas, extras).  
- Soporte multiusuario y roles (jefe de obra vs administración).  
- Migraciones de esquema controladas si se añade funcionalidad extra. [web:83][web:22]

---

## Licencia

Pon la licencia que quieras (MIT, GPL, etc.). Si es para uso interno, puedes dejarlo cerrado o MIT para compartir la idea.
