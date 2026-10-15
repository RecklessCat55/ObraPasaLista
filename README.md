# 📋 ObraPasaLista

**Control de presencia, CAE/PRL y gestión de personal en obra civil**, aplicación web local y offline diseñada específicamente para jefes de obra, encargados y administrativos que necesitan registrar asistencia, controlar documentación preventiva y generar informes de costes sin depender de conexión a internet.

> Versión actual: **v1.4.0** · Arquitectura Node.js/Express sobre SQLite (puerto robusto del legacy Python/Flask)

---

## ✨ Funcionalidades principales

- **📅 Parte diario y asignación masiva** — Fichaje por jornada con soporte para vista de escritorio y vista optimizada para dispositivos móviles en pie de obra. Asignación masiva en un solo clic.
- **⚡ Arrastre temporal inteligente** — Duplicación rápida de cuadrillas desde el último día laborable real, saltando automáticamente fines de semana y festivos autonómicos o locales configurables.
- **🛡️ Coordinación de Actividades Empresariales (CAE / PRL)** — Control de documentación preventiva obligatoria (TC2, seguros de RC, reconocimientos médicos, formación PRL) con semáforo de estados (válido, por caducar, caducado).
- **🔒 Protección de meses cerrados** — Guardas de seguridad a nivel de servicio y base de datos que impiden crear, modificar o eliminar imputaciones en meses ya cerrados contablemente.
- **🗑️ Borrado suave (Soft Deletes)** — Protección total de integridad histórica en `persona`, `empresa` y `obra` mediante la columna `deleted_at`. Los registros eliminados no rompen diarios ni partes pasados y pueden auditarse opcionalmente en los informes.
- **🎯 Metas de horas y tarifas** — Jerarquía de metas de jornada (`persona` > `empresa` > `obra` > 8h defecto), detección de desajustes y cálculo dinámico de costes por hora según rango laboral.
- **💾 Copias de seguridad automáticas** — Generación de snapshots SQLite con verificación estricta de integridad (`PRAGMA integrity_check`) y política de rotación histórica configurable.
- **📁 Documentación de obra** — Estructura jerárquica de carpetas y archivos asociada a partidas y fases de obra.
- **📶 100% Offline** — Bootstrap 5.3.2 y Bootstrap Icons 1.11.3 servidos en local desde el propio servidor.

---

## 🛠️ Stack tecnológico

| Capa | Tecnología | Características |
|------|-----------|-----------------|
| **Backend** | Node.js ≥ 18 + Express 5 | Síncrono, robusto y mono-proceso para fiabilidad en disco local |
| **Base de datos** | SQLite 3 (`better-sqlite3`) | WAL mode, foreign keys activadas, migraciones idempotentes |
| **Plantillas** | EJS | Renderizado SSR en servidor con protección contra fugas de `null` |
| **Frontend** | Bootstrap 5.3.2 + Icons 1.11.3 | Vendorizado en local (sin CDNs externas) |
| **Archivos** | Multer | Subida y custodia segura de documentación técnica y PRL |
| **Sesiones** | express-session + flash | Mensajería contextual para el usuario |
| **Legacy** | Python / Flask | Preservado en `legacy-python/` para referencia histórica |

---

## 🚀 Instalación y arranque rápido

### Requisitos previos

- [Node.js](https://nodejs.org/) **v18 o superior** (v20+ recomendado)
- `npm` (incluido con Node.js)

### Pasos de instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/RecklessCat55/ObraPasaLista.git
cd ObraPasaLista

# 2. Instalar dependencias de producción y desarrollo
npm install

# 3. Inicializar la base de datos (v1.4)
npm run init-db

# 4. Iniciar la aplicación
npm start
```

La app se abrirá en **http://localhost:5000** (puerto configurable mediante la variable de entorno `PORT`).

---

## 💻 Modos de ejecución y scripts auxiliares

### En desarrollo (recarga automática)

```bash
npm run dev
```

### Windows — Scripts de un solo clic

- **Arrancar app**: Doble clic en `src/Start.bat`.
- **Actualizar repositorio**: Ejecutar `src/actualizador_obrapasalista.bat` para descargar cambios y migrar esquemas automáticamente.

### Linux — Scripts de arranque

```bash
chmod +x src/instalador_obra_pasalista_linux.sh src/start.sh
./src/start.sh
```

---

## ⚙️ Comandos npm disponibles

| Comando | Acción |
|---------|--------|
| `npm start` | Inicia el servidor HTTP en producción |
| `npm run dev` | Inicia con monitorización y recarga automática (`node --watch`) |
| `npm run init-db` | Inicializa el esquema completo (v1.4) y siembra rangos por defecto |
| `npm run upgrade-db` | Ejecuta las migraciones acumulativas idempotentes (`v1.1` → `v1.4`) |
| `npm run backup` | Ejecuta un backup íntegro de la base de datos con rotación y verificación |
| `npm test` | Ejecuta la suite de smoke tests funcionales en memoria |

---

## 🗂️ Estructura del proyecto

```
ObraPasaLista/
├── src/
│   ├── app.js                   # Configuración y servidor Express
│   ├── config.js                # Variables de entorno y rutas del sistema
│   ├── db.js                    # Esquema SQLite, migraciones v1.1-v1.4 y conexión
│   ├── cli.js                   # CLI interactivo (init-db, upgrade-db, backup)
│   ├── utils.js                 # Manejo seguro de ficheros, serialización y errores
│   ├── routes/                  # Controladores y rutas HTTP modulares
│   │   ├── index.js             # Dashboard de inicio y métricas rápidas
│   │   ├── diario.js            # Fichaje diario, vista móvil y arrastre inteligente
│   │   ├── mensual.js           # Matriz mensual de horas y cierre de periodos
│   │   ├── obras.js             # CRUD de obras, asignación de empresas y partidas
│   │   ├── empresas.js          # CRUD de empresas y control de bajas/soft delete
│   │   ├── personas.js          # Ficha de personal, historial de rangos y RGPD
│   │   ├── cae.js               # Alertas documentales y gestión CAE/PRL
│   │   ├── config.js            # Ajuste de metas, festivos y parámetros globales
│   │   ├── documentacion.js     # Explorador de archivos de obra
│   │   ├── informes.js          # Cálculo y exportación de informes de costes
│   │   ├── backup.js            # Panel web de gestión de copias de seguridad
│   │   └── rangos.js            # Catálogo de rangos profesionales y tarifas
│   ├── services/                # Lógica pura de negocio y cálculos
│   │   ├── carryover.js         # Algoritmo de retroceso y cálculo de laborables
│   │   ├── backup.js            # Pipeline de backup, retención e integridad
│   │   ├── cae.js               # Evaluación y semáforo de vigencia documental
│   │   ├── negocio.js           # Agregaciones, metas efectivas y desajustes
│   │   ├── horas.js             # Validaciones de jornada y control de meses cerrados
│   │   ├── fechas.js            # Utilidades y formateo de fechas
│   │   ├── docs.js              # Gestión en disco de documentos
│   │   ├── logs.js              # Auditoría administrativa
│   │   └── excel.js             # Generación de reportes tabulares
│   ├── middleware/              # Renderizado compartido y manejo de sesión
│   ├── views/                   # Vistas EJS (diario, obras, personas, cae, config...)
│   └── static/                  # Bootstrap 5, iconos y hojas de estilo locales
├── tests/
│   └── smoke_test.js            # Smoke test exhaustivo en memoria SQLite
├── data/                        # Almacenamiento local de SQLite y copias
├── legacy-python/               # Código original Flask para auditoría y contraste
├── package.json
└── README.md
```

---

## 🧪 Pruebas y verificación de calidad

La suite de pruebas automatizadas ejecuta un test de humo end-to-end sobre una base de datos SQLite en memoria sin requerir dependencias externas:

```bash
npm test
```

### Qué cubre la suite de pruebas:
1. **Esquema completo y migraciones**: Valida la creación e idempotencia de `MIGRATION_V11`, `MIGRATION_V12`, `MIGRATION_V13` y `MIGRATION_V14`.
2. **Servicios de horas**: Verificación de límites de 24h, coherencia de cómputo y bloqueo de meses cerrados.
3. **Arrastre inteligente**: Comprobación de que salta sábados, domingos y festivos configurados en `config_festivo`.
4. **Lógica de negocio**: Resolución de metas efectivas (`persona` > `empresa` > `obra`), detección de desajustes y costes.
5. **Auditoría e integridad**: Registro de eventos administrativos y verificación de integridad SQLite.
6. **Soft Deletes**: Comprueba que la eliminación lógica conserva registros históricos en diarios y mensuales sin violar claves foráneas.

---

## 💾 Copias de seguridad y restauración

### Generar un backup desde terminal

```bash
npm run backup
```

Genera un archivo con marca de tiempo en:
```
~/.obrapasalista/data/backups/backup_YYYYMMDD_HHMMSS_AUTO.db
```

### Política de retención e integridad
- **Rotación**: Conserva hasta **30 copias** y purga aquellas con más de **90 días**.
- **Comprobación de integridad**: Cada copia se verifica con `PRAGMA integrity_check` antes de ser archivada.

### Proceso de restauración manual

> ⚠️ **Advertencia**: La restauración sustituye la base de datos activa por la copia elegida. Se recomienda hacer un backup de seguridad antes de proceder.

1. **Detener el servidor**: Presiona `Ctrl + C` en la consola donde corre la aplicación.
2. **Reemplazar el archivo de base de datos**:
   ```powershell
   # En Windows PowerShell
   Copy-Item "$env:USERPROFILE\.obrapasalista\data\backups\backup_YYYYMMDD_HHMMSS_AUTO.db" `
             "$env:USERPROFILE\.obrapasalista\data\app.db"
   ```
   ```bash
   # En Linux / macOS
   cp ~/.obrapasalista/data/backups/backup_YYYYMMDD_HHMMSS_AUTO.db ~/.obrapasalista/data/app.db
   ```
3. **Asegurar migraciones**:
   ```bash
   npm run upgrade-db
   ```
4. **Reiniciar el servicio**:
   ```bash
   npm start
   ```

---

## ♿ Accesibilidad y ergonomía en obra

Diseñado para uso en tablets rugerizadas y smartphones con luz solar directa o uso con guantes:
- **Zonas táctiles ampliadas**: Botones y filas de tabla con altura mínima de **44px** (estándar Apple HIG / Android Material).
- **Tipografía legible**: Tamaños de 15px a 18px en celdas numéricas de fichaje.
- **Alto contraste**: Tema oscuro optimizado para visibilidad en exteriores y bajo consumo de batería en pantallas OLED.

---

## 📄 Licencia

Proyecto privado — Todos los derechos reservados.  
*Desarrollado para uso en gestión técnica de obra civil y edificación.*
