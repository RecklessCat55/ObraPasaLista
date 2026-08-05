'use strict';
/**
 * middleware/render.js — helper de render en dos pasos: primero la vista de
 * la página (views/<template>.ejs), luego layout.ejs con ese HTML embebido.
 *
 * Es el equivalente práctico a `render_template_string(BASE + "...")` con
 * `{% extends %}` / `{% block %}` de Jinja2: en vez de bloques con nombre,
 * cada página EJS simplemente exporta un `body` de HTML y unos metadatos
 * (title, active) que el layout usa para la cabecera/nav.
 *
 * Uso desde una ruta:
 *   renderPage(req, res, 'empresas/index', { title: 'Empresas', active: 'mas', empresas });
 */
const path = require('path');
const ejs = require('ejs');
const { popFlashed } = require('./flash');
const { fs: fsDate } = require('../services/fechas');

const VIEWS_DIR = path.join(__dirname, '..', 'views');

function renderPage(req, res, template, locals = {}) {
  // 'hoy' se inyecta en TODAS las vistas, igual que el context_processor
  // `inject_globals()` de la version Flask.
  const fullLocals = { hoy: fsDate(new Date()), ...locals };
  const pageFile = path.join(VIEWS_DIR, `${template}.ejs`);
  ejs.renderFile(pageFile, fullLocals, {}, (err, bodyHtml) => {
    if (err) {
      console.error(`Error renderizando vista '${template}':`, err);
      return res.status(500).send(`Error de plantilla en ${template}: ${err.message}`);
    }
    const layoutLocals = {
      title: locals.title || 'OPL',
      active: locals.active || null,
      hoy: fsDate(new Date()),
      messages: popFlashed(req),
      scripts: locals.scripts || '',
      body: bodyHtml,
    };
    res.render('layout', layoutLocals, (err2, html) => {
      if (err2) {
        console.error('Error renderizando layout:', err2);
        return res.status(500).send(`Error de layout: ${err2.message}`);
      }
      res.send(html);
    });
  });
}

module.exports = { renderPage };
