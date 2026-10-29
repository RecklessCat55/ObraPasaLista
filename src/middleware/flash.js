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
  if (req.session && req.session.flashMessages && req.session.flashMessages.length > 0) {
    const msgs = req.session.flashMessages;
    delete req.session.flashMessages;
    return msgs;
  }
  return [];
}

module.exports = { flashMiddleware, popFlashed };
