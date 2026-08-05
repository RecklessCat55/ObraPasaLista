#!/usr/bin/env node
'use strict';
/**
 * cli.js — equivalente a los comandos `flask --app app init-db` y
 * `flask --app app upgrade-db` de la version Python.
 *
 * Uso:
 *   node src/cli.js init-db
 *   node src/cli.js upgrade-db
 *   npm run init-db
 *   npm run upgrade-db
 */
const config = require('./config');
config.migrarUbicacionBdLegacy();

const db = require('./db');
const conn = db.getDb();

const cmd = process.argv[2];
if (cmd === 'init-db') {
  db.cliInitDb(conn);
} else if (cmd === 'upgrade-db') {
  db.cliUpgradeDb(conn);
} else {
  console.log('Uso: node src/cli.js <init-db|upgrade-db>');
  process.exit(1);
}
conn.close();
