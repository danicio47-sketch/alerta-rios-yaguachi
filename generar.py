# -*- coding: utf-8 -*-
"""Genera la página pública "Alerta ríos de Yaguachi".

Baja el caudal GloFAS (Open-Meteo Flood API) de los ríos del cantón y la lluvia
(Open-Meteo Forecast API), calcula el semáforo y escribe:
  _site/index.html   la página, con los datos dentro
  _site/datos.json   los mismos datos, para descargar
  historial/AAAA-MM-DD.json   resumen del día (se guarda en el repositorio)

Solo usa la biblioteca estándar de Python. Uso: python generar.py
"""
import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.abspath(__file__))
SITIO = os.path.join(RAIZ, "_site")
HISTORIAL = os.path.join(RAIZ, "historial")
UA = {"User-Agent": "GAD-Yaguachi-COE-alerta-rios/1.0"}
ECUADOR = dt.timezone(dt.timedelta(hours=-5))

# Umbrales de lluvia (mm). De prueba: salen de ERA5 1991-2020 en Yaguachi (P99 24 h = 55,9;
# P95 72 h = 78,5; P99 72 h = 131,8). Validar con el gestor de riesgos.
R24_AMARILLO = 50.0
R72_AMARILLO = 100.0
R72_NARANJA = 150.0

# Puntos de lluvia usados en los cortes del COE de octubre de 2026.
PUNTOS_LLUVIA = [
    ("cabecera", "Yaguachi (cabecera)", -2.094, -79.699),
    ("milagro", "Milagro", -2.134, -79.594),
    ("bucay", "Bucay", -2.198, -79.130),
    ("la_troncal", "La Troncal", -2.423, -79.340),
]
NIVELES = ["verde", "amarillo", "naranja", "rojo"]


def leer(nombre):
    with open(os.path.join(RAIZ, nombre), encoding="utf-8") as f:
        return json.load(f)


def bajar(url, params):
    full = url + "?" + urllib.parse.urlencode(params, safe=",")
    for intento in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(full, headers=UA), timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # Open-Meteo responde 429 si se le pide mucho seguido
            print("reintento", intento + 1, e)
            time.sleep(30 * (intento + 1))
    raise SystemExit("No se pudo descargar " + full)


def r1(v):
    return None if v is None else round(float(v), 1)


def caudales(rios, hoy):
    datos = bajar("https://flood-api.open-meteo.com/v1/flood", {
        "latitude": ",".join(f"{r['lat']:.3f}" for r in rios),
        "longitude": ",".join(f"{r['lon']:.3f}" for r in rios),
        "daily": "river_discharge,river_discharge_median,river_discharge_p25,river_discharge_p75",
        "past_days": 31, "forecast_days": 16,
    })
    if isinstance(datos, dict):
        datos = [datos]
    filas = []
    for rio, d in zip(rios, datos):
        dd = d["daily"]
        for i, fecha in enumerate(dd["time"]):
            if fecha < hoy:
                filas.append({"rio_id": rio["rio_id"], "fecha": fecha, "tipo": "simulado",
                              "q": r1(dd["river_discharge"][i]), "q_p25": None, "q_p75": None})
            elif fecha == hoy:
                filas.append({"rio_id": rio["rio_id"], "fecha": fecha, "tipo": "simulado",
                              "q": r1(dd["river_discharge"][i]),
                              "q_p25": r1(dd["river_discharge_p25"][i]), "q_p75": r1(dd["river_discharge_p75"][i])})
            else:
                filas.append({"rio_id": rio["rio_id"], "fecha": fecha, "tipo": "pronostico",
                              "q": r1(dd["river_discharge_median"][i]),
                              "q_p25": r1(dd["river_discharge_p25"][i]), "q_p75": r1(dd["river_discharge_p75"][i])})
    # Los últimos 30 días simulados, hoy y el pronóstico
    desde = (dt.date.fromisoformat(hoy) - dt.timedelta(days=30)).isoformat()
    return [f for f in filas if f["fecha"] >= desde and f["q"] is not None]


def lluvias(ahora):
    datos = bajar("https://api.open-meteo.com/v1/forecast", {
        "latitude": ",".join(f"{p[2]:.3f}" for p in PUNTOS_LLUVIA),
        "longitude": ",".join(f"{p[3]:.3f}" for p in PUNTOS_LLUVIA),
        "hourly": "precipitation", "daily": "precipitation_sum",
        "past_days": 14, "forecast_days": 8, "timezone": "America/Guayaquil",
    })
    if isinstance(datos, dict):
        datos = [datos]
    corte = ahora.strftime("%Y-%m-%dT%H:00")
    acum = {}
    diarias = {}
    for (pid, _, _, _), d in zip(PUNTOS_LLUVIA, datos):
        th = d["hourly"]["time"]
        ph = [0.0 if v is None else float(v) for v in d["hourly"]["precipitation"]]
        i = th.index(corte)  # horas hasta i: ya transcurridas
        acum[pid] = {
            ("24h", "ultimas"): sum(ph[i - 23:i + 1]), ("72h", "ultimas"): sum(ph[i - 71:i + 1]),
            ("24h", "proximas"): sum(ph[i + 1:i + 25]), ("72h", "proximas"): sum(ph[i + 1:i + 73]),
        }
        diarias[pid] = dict(zip(d["daily"]["time"], d["daily"]["precipitation_sum"]))
    filas = []
    for clave in acum["cabecera"]:
        filas.append({"lugar": "cabecera", "ventana": clave[0], "periodo": clave[1], "mm": r1(acum["cabecera"][clave])})
        filas.append({"lugar": "cuenca", "ventana": clave[0], "periodo": clave[1],
                      "mm": r1(sum(acum[p[0]][clave] for p in PUNTOS_LLUVIA) / len(PUNTOS_LLUVIA))})
    hoy = ahora.date()
    serie = []
    for fecha, mm in sorted(diarias["cabecera"].items()):
        f = dt.date.fromisoformat(fecha)
        if (hoy - f).days > 14 or (f - hoy).days > 7:
            continue
        tipo = "observado" if f < hoy else "hoy" if f == hoy else "pronostico"
        cuenca = [diarias[p[0]].get(fecha) for p in PUNTOS_LLUVIA]
        cuenca = [c for c in cuenca if c is not None]
        serie.append({"fecha": fecha, "tipo": tipo, "mm": r1(mm or 0),
                      "mm_cuenca": r1(sum(cuenca) / len(cuenca)) if cuenca else None})
    return filas, serie, corte


def estado_rios(rios, caudal, umbrales, hoy):
    salida = []
    for rio in rios:
        filas = sorted((f for f in caudal if f["rio_id"] == rio["rio_id"]), key=lambda f: f["fecha"])
        sim = [f for f in filas if f["tipo"] == "simulado"]
        h = sim[-1] if sim else None
        prox = [f for f in filas if f["tipo"] == "pronostico" and h and f["fecha"] > h["fecha"]][:7]
        m7 = max(prox, key=lambda f: f["q"]) if prox else None
        u = {int(x["periodo_anios"]): float(x["q_m3s"]) for x in umbrales if x["rio_id"] == rio["rio_id"]}
        q = max(h["q"] if h else 0, m7["q"] if m7 else 0)
        fiable = bool(rio.get("fiable", True)) and h is not None and 2 in u
        n = -1 if not fiable else 3 if q >= u[25] else 2 if q >= u[10] else 1 if q >= u[2] else 0
        salida.append({
            "rio_id": rio["rio_id"], "nombre": rio["nombre"], "fiable": fiable,
            "q_hoy": h["q"] if h else None, "q_max7": m7["q"] if m7 else None, "fecha_max7": m7["fecha"] if m7 else None,
            "q2": u.get(2), "q10": u.get(10), "q25": u.get(25),
            "pct_q2": round(q / u[2], 3) if 2 in u else None,
            "nivel": "sin dato fiable" if n < 0 else NIVELES[n],
            "nota": rio.get("nota"),
        })
    return salida


def resumen(estado, lluvia_acum):
    ok = [r for r in estado if r["fiable"]]
    n_rio = max([NIVELES.index(r["nivel"]) for r in ok] or [0])
    critico = max(ok, key=lambda r: r["pct_q2"] or 0) if ok else None
    ll24 = max(f["mm"] for f in lluvia_acum if f["ventana"] == "24h")
    ll72 = max(f["mm"] for f in lluvia_acum if f["ventana"] == "72h")
    n_ll = 2 if (n_rio >= 1 and ll72 >= R72_NARANJA) else 1 if (ll72 >= R72_AMARILLO or ll24 >= R24_AMARILLO) else 0
    n = max(n_rio, n_ll)
    if n == 0:
        motivo = "que todos los ríos siguen bajo su caudal de 2 años y la lluvia bajo sus umbrales"
    elif n_rio >= n_ll:
        motivo = "el caudal del " + critico["nombre"] + " frente a sus periodos de retorno"
    else:
        motivo = "la lluvia acumulada; ningún río pasa todavía su caudal de 2 años"
    return {
        "nivel": NIVELES[n], "motivo": motivo,
        "rios_alerta": sum(1 for r in ok if NIVELES.index(r["nivel"]) >= 1), "n_rios": len(ok),
        "rio_critico": critico["nombre"] if critico else None, "pct_q2_max": critico["pct_q2"] if critico else None,
        "lluvia_24h_max": ll24, "lluvia_72h_max": ll72,
    }


def expuestos(recintos):
    salida = []
    for e in ("alta", "media", "baja"):
        rs = [r for r in recintos if r["exposicion"] == e]
        salida.append({"exposicion": e, "recintos": len(rs),
                       "poblacion": sum(r["poblacion"] or 0 for r in rs),
                       "poblacion_influencia": sum(r["poblacion_influencia"] or 0 for r in rs)})
    return salida


def main():
    ahora = dt.datetime.now(ECUADOR).replace(minute=0, second=0, microsecond=0)
    hoy = ahora.date().isoformat()
    rios, umbrales, recintos = leer("rios.json"), leer("umbrales.json"), leer("recintos.json")

    caudal = caudales(rios, hoy)
    time.sleep(5)
    lluvia_acum, lluvia_diaria, corte = lluvias(ahora)
    estado = estado_rios(rios, caudal, umbrales, hoy)
    res = resumen(estado, lluvia_acum)

    datos = {
        "generado": dt.datetime.now(ECUADOR).isoformat(timespec="minutes"),
        "fecha_hoy": hoy, "corte_lluvia": corte,
        "umbrales_lluvia": {"r24_amarillo": R24_AMARILLO, "r72_amarillo": R72_AMARILLO, "r72_naranja": R72_NARANJA},
        "resumen": res, "rios": estado, "caudal_diario": caudal, "umbrales": umbrales,
        "lluvia_acumulada": lluvia_acum, "lluvia_diaria": lluvia_diaria,
        "expuestos": expuestos(recintos), "recintos": recintos,
    }

    os.makedirs(SITIO, exist_ok=True)
    with open(os.path.join(RAIZ, "plantilla.html"), encoding="utf-8") as f:
        plantilla = f.read()
    incrustado = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    with open(os.path.join(SITIO, "index.html"), "w", encoding="utf-8") as f:
        f.write(plantilla.replace("/*__DATOS__*/null", incrustado))
    with open(os.path.join(SITIO, "datos.json"), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)

    os.makedirs(HISTORIAL, exist_ok=True)
    with open(os.path.join(HISTORIAL, hoy + ".json"), "w", encoding="utf-8") as f:
        json.dump({"generado": datos["generado"], "resumen": res, "rios": estado, "lluvia_acumulada": lluvia_acum},
                  f, ensure_ascii=False, indent=1)

    print(f"{hoy} · nivel {res['nivel']} · {res['rios_alerta']} de {res['n_rios']} ríos sobre Q2 · "
          f"lluvia 72 h máx {res['lluvia_72h_max']} mm")


if __name__ == "__main__":
    main()
