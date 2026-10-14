# 📋 ObraPasaLista

**Control de presencia y gestión de personal en obra**, aplicación web local diseñada para jefes de obra que necesitan registrar asistencia, asignar trabajadores y generar informes de costes sin depender de internet.

> Versión actual: **v1.2.0** · Puerto Node.js/Express de la versión original Python/Flask

---

## ✨ Funcionalidades principales

- **Parte diario** — Registro de asistencia y asignación masiva de trabajadores por obra
- **Gestión de obras** — Alta, edición y seguimiento de obras activas
- **Gestión de empresas y personas** — Directorio de subcontratas y trabajadores con rangos
- **Documentación de obra** — Registro de incidencias, partes y estado
- **Auditoría** — Historial de cambios y estado de la obra
- **Informe de costes** — Cálculo de costes por obra y empresa
- **FAQ integrada** — Ayuda contextual para el usuario de obra
- **Bootstrap 5 vendorizado** — Sin dependencia de CDN externo; funciona sin internet en la obra

---

## 🛠️ Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Node.js ≥ 18 + Express 5 |
| Base de datos | SQLite (vía `better-sqlite3`) |
| Plantillas | EJS |
| Frontend | Bootstrap 5.3.2 + Bootstrap Icons 1.11.3 (local) |
| Subida de archivos | Multer |
| Sesiones | express-session |
| Legacy | Python/Flask (`legacy-python/`) |

---

## 🚀 Instalación y arranque

### Requisitos previos

- [Node.js](https://nodejs.org/) **v18 o superior**
- `npm` (incluido con Node.js)

### Pasos

```bash
# 1. Clona el repositorio
git clone https://github.com/RecklessCat55/ObraPasaLista.git
cd ObraPasaLista

# 2. Instala las dependencias
npm install

# 3. Inicializa la base de datos
npm run init-db

# 4. Arranca la aplicación
npm start
```

La app estará disponible en **http://localhost:5000** (o el puerto configurado con `PORT=xxxx`).

### Modo desarrollo (recarga automática)

```bash
npm run dev
```

### Windows — script rápido

Doble clic en `src/Start.bat` o ejecuta:

```bat
src\Start.bat
```

### Linux — instalador automático

```bash
chmod +x src/instalador_obra_pasalista_linux.sh
./src/instalador_obra_pasalista_linux.sh
```

---

## ⚙️ Scripts disponibles

| Comando | Descripción |
|---------|-------------|
| `npm start` | Arranca el servidor en producción |
| `npm run dev` | Arranca con `--watch` (recarga en caliente) |
| `npm run init-db` | Crea e inicializa la base de datos SQLite |
| `npm run upgrade-db` | Aplica migraciones pendientes de esquema |
| `npm run backup` | Genera copia de seguridad de la base de datos |
| `npm test` | Ejecuta el smoke test completo |

---

## 🗂️ Estructura del proyecto

```
ObraPasaLista/
├── src/
│   ├── app.js              # Punto de entrada Express
│   ├── config.js           # Configuración general
│   ├── db.js               # Capa de acceso a datos (SQLite)
│   ├── cli.js              # CLI para init-db / upgrade-db / backup
│   ├── utils.js            # Utilidades compartidas
│   ├── routes/             # Rutas Express (diario, obras, personas…)
│   ├── services/           # Lógica de negocio
│   ├── middleware/         # Middlewares (auth, etc.)
│   ├── views/              # Plantillas EJS
│   ├── static/             # Bootstrap, iconos y assets (offline)
│   ├── data/               # Base de datos SQLite y backups
│   ├── docs/               # Documentación interna
│   ├── Start.bat           # Lanzador Windows
│   ├── start.sh            # Lanzador Linux
│   ├── Launcher.py         # Lanzador Python (legacy helper)
│   └── app.py              # Versión Flask completa (referencia)
├── legacy-python/          # Código Python/Flask original
├── tests/
│   └── smoke_test.js       # Tests de humo end-to-end
├── docs/                   # Documentación del proyecto
├── data/                   # Datos y backups (raíz)
├── package.json
└── .gitignore
```

---

## 🧪 Tests

El smoke test cubre el flujo completo principal:

```bash
npm test
```

Rutas verificadas: `/`, `/diario/`, `/empresas/`, `/personas/`, `/obras/`, `/rangos/`, `/faq/`

---

## 🔄 Actualización (Windows)

El repositorio incluye un actualizador automático para Windows:

```bat
src\actualizador_obrapasalista.bat
```

Este script descarga la última versión y migra la base de datos sin perder datos.

---

## 💾 Copias de seguridad y restauración

### Generar un backup

```bash
npm run backup
```

Crea una copia de la base de datos en:

```
~/.obrapasalista/data/backups/backup_YYYYMMDD_HHMMSS_AUTO.db
```

El fichero lleva una marca de tiempo en el nombre para facilitar la identificación.  
La política de retención por defecto conserva los últimos **30 ficheros** y descarta los de más de **90 días**.

### Backups automáticos

La aplicación llama internamente a `backupCompleto()` en cada arranque. Se puede programar también con el programador de tareas de Windows o un cron en Linux:

```
# Linux: backup diario a las 02:00
0 2 * * * /usr/bin/node /ruta/a/ObraPasaLista/src/cli.js backup >> /var/log/obra_backup.log 2>&1
```

### Verificación de integridad

Cada backup generado se verifica automáticamente con `PRAGMA integrity_check`.  
Si la verificación falla, se muestra un aviso en consola pero el proceso no se interrumpe.

### Restaurar desde un backup

> ⚠️ **La restauración reemplaza todos los datos actuales.** Haz siempre un backup previo antes de restaurar.

1. **Para la aplicación**:
   ```bash
   # Ctrl+C en el terminal donde corre la app
   ```

2. **Localiza el backup** a restaurar en `~/.obrapasalista/data/backups/`

3. **Reemplaza la base de datos activa**:
   ```bash
   # Windows PowerShell
   Copy-Item "$env:USERPROFILE\.obrapasalista\data\backups\backup_YYYYMMDD_HHMMSS_AUTO.db" `
             "$env:USERPROFILE\.obrapasalista\data\app.db"

   # Linux / macOS
   cp ~/.obrapasalista/data/backups/backup_YYYYMMDD_HHMMSS_AUTO.db \
      ~/.obrapasalista/data/app.db
   ```

4. **Aplica migraciones** (por si el backup es de una versión anterior):
   ```bash
   npm run upgrade-db
   ```

5. **Reinicia la aplicación**:
   ```bash
   npm start
   ```

---

## 📦 Versión legacy (Python/Flask)

La versión original en Python con Flask se conserva en `legacy-python/` y en `src/app.py` como referencia. El port a Node.js/Express mantiene paridad funcional completa.

Para migrar desde la versión Python, consulta [`cambios-obra-pasalista.md`](cambios-obra-pasalista.md).

---

## ♿ Accesibilidad (v1.2)

La v1.2 incluye un parche UX orientado a uso en obra (pantallas pequeñas, condiciones de luz difícil):

- Tipografía aumentada en tablas de horas (11px → 15-16px)
- Zonas de toque mínimas de **44px** en botones y celdas (estándar Material/HIG)
- Badges con tamaño mínimo homogéneo de 13px
- Bootstrap y Bootstrap Icons servidos **en local** (sin CDN)

---

## 📄 Licencia

Proyecto privado — todos los derechos reservados.

---

*Desarrollado para uso interno en gestión de obra civil.*
