#!/usr/bin/env node
'use strict';
/**
 * cli.js — equivalente a los comandos `flask --app app init-db` y
 * `flask --app app upgrade-db` de la version Python.
 *
 * Uso:
 *   node src/cli.js init-db
 *   node src/cli.js upgrade-db
 *   node src/cli.js backup [contexto]
 *   npm run init-db
 *   npm run upgrade-db
 *   npm run backup
 */
const config = require('./config');
config.migrarUbicacionBdLegacy();

const db = require('./db');
const conn = db.getDb();

const cmd = process.argv[2];
if (cmd === 'init-db') {
  db.cliInitDb(conn);
  conn.close();
} else if (cmd === 'upgrade-db') {
  db.cliUpgradeDb(conn);
  conn.close();
} else if (cmd === 'backup') {
  const { backupCompleto } = require('./services/backup');
  const contexto = process.argv[3] || 'CLI';
  backupCompleto(conn, contexto)
    .then(({ ruta, integridadOk, eliminados }) => {
      const path = require('path');
      console.log(`OK Backup creado: ${path.basename(ruta)}`);
      console.log(`   Integridad: ${integridadOk ? 'OK' : 'FALLO — revisar manualmente'}`);
      if (eliminados.length) {
        console.log(`   Retención: ${eliminados.length} backup(s) antiguos eliminados.`);
      }
      conn.close();
    })
    .catch((e) => {
      console.error(`ERROR: ${e.message}`);
      conn.close();
      process.exit(1);
    });
} else {
  console.log('Uso: node src/cli.js <init-db|upgrade-db|backup [contexto]>');
  process.exit(1);
}
