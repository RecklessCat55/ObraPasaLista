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

app.disable('x-powered-by');

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

app.use(express.urlencoded({ extended: true, limit: '1mb' }));
app.use(express.json({ limit: '1mb' }));
app.use(
  session({
    name: 'opl.sid',
    secret: config.SECRET_KEY,
    resave: false,
    saveUninitialized: false,
    cookie: {
      httpOnly: true,
      sameSite: 'lax',
      maxAge: 12 * 3600 * 1000,
    },
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
app.use((err, req, res, next) => {
  console.error('[Error]', req.method, req.originalUrl, err);
  const msg = err && err.name === 'ValidationError'
    ? err.message
    : 'Se ha producido un error. Revisa el registro local.';
  req.flash(msg, 'error');
  const ref = req.get('referer');
  const back = ref && ref.startsWith('/') && !ref.startsWith('//') ? ref : '/';
  res.redirect(back);
});

app.use((req, res) => {
  res.status(404).send('Página no encontrada.');
});

function gracefulShutdown() {
  try {
    conn.close();
  } catch (_) {}
  process.exit(0);
}

process.on('SIGINT', gracefulShutdown);
process.on('SIGTERM', gracefulShutdown);

if (require.main === module) {
  app.listen(config.PORT, '127.0.0.1', () => {
    console.log(`ObraPasaLista escuchando en http://127.0.0.1:${config.PORT}`);
  });
}

module.exports = app;
