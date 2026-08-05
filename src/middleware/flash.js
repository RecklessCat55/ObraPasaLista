'use strict';
/**
 * middleware/flash.js — mensajes flash basados en sesión, equivalente a
 * `flash()` / `get_flashed_messages(with_categories=True)` de Flask.
 *
 * Categorías usadas en toda la app: 'error', 'success', 'warning', 'info'
 * (mapeadas a clases de alerta de Bootstrap en views/layout.ejs).
 */

function flashMiddleware(req, res, next) {
  req.flash = (message, category = 'message') => {
    if (!req.session.flashMessages) req.session.flashMessages = [];
    req.session.flashMessages.push([category, message]);
  };
  next();
}

/** Devuelve los mensajes acumulados y vacía la cola (se muestran una sola vez). */
function popFlashed(req) {
  const msgs = (req.session && req.session.flashMessages) || [];
  if (req.session) req.session.flashMessages = [];
  return msgs;
}

module.exports = { flashMiddleware, popFlashed };
