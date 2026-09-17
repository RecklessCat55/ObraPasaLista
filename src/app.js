'use strict';
/**
 * app.js — punto de entrada de la aplicación (equivalente al `app = Flask(__name__)`
 * y registro de rutas de app.py).
 *
 * node src/app.js  ->  http://127.0.0.1:5000
 * npm run init-db     (instalación limpia)
 * npm run upgrade-db  (migración desde v1.0/v1.1)
 *
 * Variables de entorno soportadas: ver config.js
 */
const path = require('path');
const express = require('express');
const session = require('express-session');

const config = require('./config');
config.migrarUbicacionBdLegacy();

const db = require('./db');
const { flashMiddleware } = require('./middleware/flash');

const app = express();
const conn = db.getDb();

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

app.use(express.urlencoded({ extended: true }));
app.use(express.json());
app.use(
  session({
    secret: config.SECRET_KEY,
    resave: false,
    saveUninitialized: true,
  })
);
app.use(flashMiddleware);

// Estáticos: equivalente a static/vendor/... servido por Flask en /static/vendor/...
app.use('/vendor', express.static(path.join(config.BASE_DIR, 'public', 'vendor')));

// Se crean las tablas si hace falta en cada arranque (equivalente a _init_if_needed(),
// que en Flask se llamaba perezosamente en el primer request a '/').
db.initIfNeeded(conn);

// -- RUTAS --
app.use('/', require('./routes/index'));
app.use('/empresas', require('./routes/empresas'));
app.use('/subcontratas', require('./routes/subcontratas'));
app.use('/rangos', require('./routes/rangos'));
app.use('/personas', require('./routes/personas'));
app.use('/obras', require('./routes/obras'));
app.use('/obra', require('./routes/documentacion')); // ojo: singular, como en la app original
app.use('/documentacion', require('./routes/documentacionArchivo'));
app.use('/diario', require('./routes/diario'));
app.use('/mensual', require('./routes/mensual'));
app.use('/backup', require('./routes/backup'));
app.use('/config', require('./routes/config'));
app.use('/cae', require('./routes/cae'));
app.use('/informes', require('./routes/informes'));
app.use('/faq', require('./routes/faq'));

// -- MANEJO DE ERRORES --
// Equivalente al patrón `try/except ValueError as e: flash(str(e),'error')` que
// se repite en (casi) cada ruta POST de la version Python. Aquí cada ruta que
// puede lanzar una validación de negocio usa `next(e)` y este middleware final
// hace el flash + redirect genérico si la propia ruta no lo gestionó ya.
app.use((err, req, res, next) => {
  console.error(err);
  req.flash(err.message || 'Error inesperado.', 'error');
  const back = req.get('referer') || '/';
  res.redirect(back);
});

app.use((req, res) => {
  res.status(404).send('Página no encontrada.');
});

app.listen(config.PORT, '127.0.0.1', () => {
  console.log(`ObraPasaLista escuchando en http://127.0.0.1:${config.PORT}`);
});

process.on('SIGINT', () => {
  conn.close();
  process.exit(0);
});
