'use strict';
/**
 * routes/index.js — página de inicio ('/'), equivalente a la ruta index()
 * de app.py.
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { hhmm } = require('../services/fechas');
const { getLim } = require('../services/horas');
const { renderPage } = require('../middleware/render');

router.get('/', (req, res) => {
  const conn = db.getDb();
  const obras = conn.prepare("SELECT * FROM obra WHERE estado='activa' ORDER BY nombre").all();
  const stats = [
    ['buildings', 'warning', conn.prepare("SELECT count(*) c FROM obra WHERE estado='activa'").get().c, 'Obras activas'],
    ['briefcase', 'info', conn.prepare("SELECT count(*) c FROM empresa WHERE estado='activa'").get().c, 'Empresas'],
    ['people', 'success', conn.prepare("SELECT count(*) c FROM persona WHERE estado='activa'").get().c, 'Personas activas'],
    ['clock', '', hhmm(getLim(conn)), 'Límite h/día'],
  ];
  renderPage(req, res, 'index', { title: 'Inicio', active: 'home', obras, stats });
});

module.exports = router;
