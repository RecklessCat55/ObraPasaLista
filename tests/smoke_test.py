# -*- coding: utf-8 -*-
"""
Smoke test manual de ObraPasaLista v1.2.

No es una suite formal (pytest, fixtures, etc.) — es un script sencillo,
pensado para lanzarlo a mano contra una BD de pruebas cuando se toca algo
del backend, y comprobar de un vistazo que el flujo completo sigue vivo:
diario -> asignación masiva -> documentación -> cierre de mes -> cierre de
obra -> informe de costes -> reactivar obra.

CÓMO USARLO
-----------
1) Terminal 1, desde src/, con una BD de pruebas limpia:

     rm -rf data docs
     OBRAPL_MODE=test SECRET_KEY=test python -m flask --app app init-db
     OBRAPL_MODE=test SECRET_KEY=test python -m flask --app app run --port 5099

2) Terminal 2: sembrar algo de datos de ejemplo (empresa, obra, personas...)
   usando la shell de Flask o la propia web en http://127.0.0.1:5099

3) Terminal 2, desde la raíz del repo:

     python tests/smoke_test.py

Si algo falla, el script para en seco (assert) e imprime el motivo.
"""
import re
import sys

import requests

BASE = "http://127.0.0.1:5099"
s = requests.Session()


def check(label, resp, expect=(200, 302)):
    ok = resp.status_code in expect
    print(f"[{'OK' if ok else 'FAIL'}] {label} -> {resp.status_code} {resp.url}")
    if not ok:
        print(resp.text[-1500:])
        sys.exit(1)
    return resp


def main():
    # 0) abrir el parte de hoy de la obra 1 para obtener su id_diario real
    d0 = check("abrir parte diario (obra 1, hoy)", s.get(f"{BASE}/diario/1/2026-07-11"))
    m_diario = re.search(r"/diario/(\d+)/asignacion-masiva", d0.text)
    assert m_diario, "No se encontró el id_diario en la página del parte"
    id_diario = m_diario.group(1)

    # 1) asignación masiva a la primera empresa de la obra
    check("asignación masiva POST", s.post(f"{BASE}/diario/{id_diario}/asignacion-masiva", data={
        "id_empresa": "1", "horas": "5", "id_partida": "", "asunto": "Smoke test",
        "personas": ["1", "2"],
    }))
    r2 = s.get(f"{BASE}/diario/1/2026-07-11")
    assert "Smoke test" in r2.text, "Las líneas de asignación masiva no se crearon"
    print("  -> asignación masiva OK")

    # 2) documentación: crear carpeta y subir archivo
    check("crear carpeta documentación", s.post(f"{BASE}/obra/1/documentacion/carpeta/nueva", data={
        "nombre": "Carpeta smoke test", "id_partida": "", "id_padre": "",
    }))
    doc = check("ver documentación", s.get(f"{BASE}/obra/1/documentacion"))
    m = re.search(r"documentacion/carpeta/(\d+)/subir", doc.text)
    assert m, "No se encontró el formulario de subida de archivos"
    check("subir archivo", s.post(f"{BASE}/obra/1/documentacion/carpeta/{m.group(1)}/subir",
          files={"archivo": ("nota.txt", b"contenido de prueba", "text/plain")}))
    print("  -> documentación OK")

    # 3) estado de obra: debería listar el evento de auditoría más reciente
    estado = check("ver estado de obra", s.get(f"{BASE}/obras/1/estado"))
    assert "Actividad administrativa" in estado.text
    print("  -> estado de obra + auditoría OK")

    # 4) informe de costes no debe romper aunque no haya tarifas configuradas
    check("informe de costes", s.get(f"{BASE}/informes/costes?id_obra=1&mes=2026-07"))
    print("  -> informe de costes OK")

    print("\nSMOKE TEST COMPLETO SIN ERRORES")


if __name__ == "__main__":
    main()
