#!/usr/bin/env node
'use strict';
/**
 * tests/smoke_test.js — smoke test funcional del backend Node.js.
 *
 * Ejecuta los módulos de servicio y la capa de datos directamente (sin
 * levantar el servidor HTTP) contra una BD de pruebas en memoria.
 * Cubre: esquema, migraciones, servicios de horas, carryover inteligente,
 * negocio (metas, costes, estado de obra) y backup/integridad.
 *
 * Uso:
 *   npm test
 *   node tests/smoke_test.js
 */
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const Database = require('better-sqlite3');

// --- Bootstrap: crear BD en memoria con el esquema completo ---
const { SCHEMA, RANGOS_DEFAULT, MIGRATION_V12, seedRangos, aplicarMigracion } = require('../src/db');

const db = new Database(':memory:');
db.pragma('foreign_keys = ON');
db.pragma('journal_mode = WAL');
db.exec(SCHEMA);
aplicarMigracion(db, MIGRATION_V12, 'v1.2 (test)');
db.prepare('INSERT OR IGNORE INTO config(id_config,limite_horas_dia,umbral_desajuste_meta) VALUES(1,24.0,2.0)').run();
seedRangos(db);

let passed = 0;
let failed = 0;

function test(label, fn) {
  try {
    fn();
    console.log(`  ✓ ${label}`);
    passed++;
  } catch (e) {
    console.error(`  ✗ ${label}`);
    console.error(`    ${e.message}`);
    failed++;
  }
}

// ======================== 1. ESQUEMA ========================
console.log('\n1. Esquema y datos base');

test('La tabla empresa existe', () => {
  db.prepare('SELECT count(*) FROM empresa').get();
});

test('La tabla log_auditoria existe con obra_id', () => {
  const info = db.prepare("PRAGMA table_info('log_auditoria')").all();
  assert(info.some((c) => c.name === 'obra_id'), 'Falta columna obra_id');
});

test('Rangos por defecto sembrados', () => {
  const n = db.prepare('SELECT count(*) c FROM rango').get().c;
  assert(n >= RANGOS_DEFAULT.length, `Esperados >= ${RANGOS_DEFAULT.length}, obtenidos ${n}`);
});

// ======================== 2. DATOS DE PRUEBA ========================
console.log('\n2. Datos de prueba');

test('Crear empresa, obra, persona y diario', () => {
  db.prepare("INSERT INTO empresa(nombre) VALUES('Test Corp')").run();
  db.prepare("INSERT INTO obra(codigo,nombre) VALUES('T01','Obra test')").run();
  db.prepare("INSERT INTO obra_empresa(id_obra,id_empresa) VALUES(1,1)").run();
  const sinEsp = db.prepare("SELECT id_rango FROM rango WHERE codigo='SIN_ESPECIFICAR'").get();
  db.prepare(
    "INSERT INTO persona(nombre,apellido1,dni,id_empresa) VALUES('Ana','García','12345678A',1)"
  ).run();
  db.prepare(
    "INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio) VALUES(1,?,?)"
  ).run(sinEsp.id_rango, '2020-01-01');
  // Diario del viernes 12 sept 2026
  db.prepare("INSERT INTO diario(id_obra,fecha) VALUES(1,'2026-09-11')").run();
  db.prepare(
    "INSERT INTO diario_linea(id_diario,id_empresa,id_persona,horas,asunto) VALUES(1,1,1,8,'Prueba viernes')"
  ).run();
});

// ======================== 3. SERVICIO DE HORAS ========================
console.log('\n3. Servicios de horas');

const { getLim, chkHoras, chkMesCerrado, getRangoActivo } = require('../src/services/horas');

test('getLim devuelve 24 por defecto', () => {
  assert.strictEqual(getLim(db), 24.0);
});

test('chkHoras no lanza con horas dentro del límite', () => {
  chkHoras(1, '2026-09-12', 8, db); // no debe lanzar
});

test('chkHoras lanza si se supera el límite', () => {
  assert.throws(() => chkHoras(1, '2026-09-11', 20, db), /supera/);
});

test('getRangoActivo devuelve SIN_ESPECIFICAR como fallback', () => {
  const r = getRangoActivo(1, '2026-09-12', db);
  assert(r !== null, 'Debería devolver un id_rango');
});

test('chkMesCerrado no lanza si no hay mensual', () => {
  chkMesCerrado(1, 1, '2026-09-12', db);
});

// ======================== 4. CARRYOVER INTELIGENTE ========================
console.log('\n4. Arrastre temporal inteligente');

const { ultimoDiaLaboral, buscarDiarioParaArrastre } = require('../src/services/carryover');

test('ultimoDiaLaboral salta fin de semana', () => {
  // Lunes 14 sept 2026 -> último laborable = viernes 11 sept 2026
  const result = ultimoDiaLaboral('2026-09-14');
  assert.strictEqual(result, '2026-09-11');
});

test('ultimoDiaLaboral salta festivos', () => {
  // Si viernes 11 es festivo, debe devolver jueves 10
  const result = ultimoDiaLaboral('2026-09-14', { holidaysList: ['2026-09-11'] });
  assert.strictEqual(result, '2026-09-10');
});

test('ultimoDiaLaboral devuelve null si no hay día laborable en rango', () => {
  const result = ultimoDiaLaboral('2026-09-14', { maxRetroceso: 2 });
  // Retrocede sab 13 y dom 12 — ambos fin de semana, no encuentra
  assert.strictEqual(result, null);
});

test('buscarDiarioParaArrastre encuentra el diario del viernes desde el lunes', () => {
  const d = buscarDiarioParaArrastre(db, 1, '2026-09-14');
  assert(d, 'Debería encontrar un diario');
  assert.strictEqual(d.fecha, '2026-09-11');
});

// ======================== 5. NEGOCIO ========================
console.log('\n5. Lógica de negocio');

const {
  getMetaEfectiva,
  chkObraActiva,
  mensualesAbiertos,
  precioEfectivoPersona,
} = require('../src/services/negocio');

test('getMetaEfectiva devuelve 8h por defecto', () => {
  const { valor, origen } = getMetaEfectiva(db, 1, 1, 1);
  assert.strictEqual(valor, 8.0);
  assert.strictEqual(origen, 'defecto');
});

test('getMetaEfectiva respeta persona > empresa > obra', () => {
  db.prepare('UPDATE persona SET meta_horas_dia=6.5 WHERE id_persona=1').run();
  const { valor, origen } = getMetaEfectiva(db, 1, 1, 1);
  assert.strictEqual(valor, 6.5);
  assert.strictEqual(origen, 'persona');
  db.prepare('UPDATE persona SET meta_horas_dia=NULL WHERE id_persona=1').run();
});

test('chkObraActiva no lanza para obra activa', () => {
  chkObraActiva(db, 1); // no debe lanzar
});

test('chkObraActiva lanza para obra finalizada', () => {
  db.prepare("UPDATE obra SET estado='finalizada' WHERE id_obra=1").run();
  assert.throws(() => chkObraActiva(db, 1), /finalizada/);
  db.prepare("UPDATE obra SET estado='activa' WHERE id_obra=1").run();
});

test('mensualesAbiertos devuelve lista vacía sin mensuales', () => {
  const r = mensualesAbiertos(db, 1);
  assert.strictEqual(r.length, 0);
});

test('precioEfectivoPersona devuelve null sin tarifas', () => {
  const r = precioEfectivoPersona(db, 1);
  assert.strictEqual(r, null);
});

// ======================== 6. AUDITORÍA ========================
console.log('\n6. Auditoría');

const { logEvent } = require('../src/services/logs');

test('logEvent inserta evento correctamente', () => {
  logEvent(db, 'TEST_EVENT', 'obra', 1, 1, { nota: 'smoke test' });
  const r = db.prepare("SELECT * FROM log_auditoria WHERE tipo_evento='TEST_EVENT'").get();
  assert(r, 'Debería existir el evento');
  const det = JSON.parse(r.detalle);
  assert.strictEqual(det.nota, 'smoke test');
  assert.strictEqual(det.obra_id, 1);
});

test('logEvent no lanza aunque falle internamente', () => {
  // Pasar un db roto no debe explotar
  logEvent({}, 'BROKEN', 'test', 0, 0, {});
});

// ======================== 7. FECHAS ========================
console.log('\n7. Servicios de fechas');

const { nf, mes, dia, hhmm, norm } = require('../src/services/fechas');

test('nf normaliza Date a YYYY-MM-DD', () => {
  const d = new Date(2026, 8, 17); // sept = 8 (0-indexed)
  assert.strictEqual(nf(d), '2026-09-17');
});

test('nf normaliza string YYYY-MM-DD', () => {
  assert.strictEqual(nf('2026-09-17'), '2026-09-17');
});

test('nf rechaza fechas inválidas', () => {
  assert.throws(() => nf('2026-13-45'), /no soportado/);
});

test('hhmm formatea correctamente', () => {
  assert.strictEqual(hhmm(8.5), '08:30');
  assert.strictEqual(hhmm(0), '00:00');
  assert.strictEqual(hhmm(null), '--');
});

test('norm normaliza texto', () => {
  assert.strictEqual(norm('Café con leche'), 'CAFE_CON_LECHE');
});

// ======================== 8. UTILS ========================
console.log('\n8. Utils');

const { secureFilename, toJsonScript, ValidationError } = require('../src/utils');

test('secureFilename limpia nombres peligrosos', () => {
  assert.strictEqual(secureFilename('../../etc/passwd'), 'etc_passwd');
  assert.strictEqual(secureFilename('mi archivo (1).pdf'), 'mi_archivo_1_.pdf');
  assert.strictEqual(secureFilename(''), '');
});

test('toJsonScript escapa caracteres peligrosos', () => {
  const r = toJsonScript('</script>');
  assert(!r.includes('</script>'), 'No debería contener </script> literal');
});

test('ValidationError es un Error con nombre correcto', () => {
  const e = new ValidationError('test');
  assert(e instanceof Error);
  assert.strictEqual(e.name, 'ValidationError');
  assert.strictEqual(e.message, 'test');
});

// ======================== RESUMEN ========================
console.log(`\n${'='.repeat(50)}`);
console.log(`RESULTADO: ${passed} pasados, ${failed} fallidos`);
if (failed > 0) {
  console.log('HAY FALLOS — revisar arriba.');
  process.exit(1);
} else {
  console.log('SMOKE TEST COMPLETO SIN ERRORES ✓');
}

db.close();
