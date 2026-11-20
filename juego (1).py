import json
import os
import secrets
import sqlite3
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

GRUPOS = [
    [
        ["Javi", "Edu", "Brenda"],
        ["Ana", "Toni", "Silvia"],
        ["Eric", "Martí", "Jona"],
        ["Alex", "Dani", "Cristian"],
    ],
    [
        ["Dani", "Ana", "Edu"],
        ["Eric", "Brenda", "Silvia"],
        ["Javi", "Alex", "Jona"],
        ["Martí", "Toni", "Cristian"],
    ],
]
NOMBRES = sorted(nombre for grupo in GRUPOS[0] for nombre in grupo)
BD = os.environ.get("GAME_DB", "cumple-cristian.sqlite3")


def partida_nueva():
    return {
        "sesiones": {},
        "planes": {},
        "historias": {},
        "orden": [],
        "votos": {},
        "consejos": {},
    }


def equipo(persona, ronda):
    return next(
        str(i) for i, grupo in enumerate(GRUPOS[ronda])
        if persona in grupo
    )


def turno(juego):
    for nombre in juego["orden"]:
        if len(juego["votos"].get(nombre, {})) < len(NOMBRES) - 1:
            return nombre
    return None


def texto(datos, campo):
    valor = datos.get(campo)
    if not isinstance(valor, str) or not 1 <= len(valor.strip()) <= 500:
        raise ValueError("Completa todos los campos con un máximo de 500 caracteres.")
    return valor.strip()


def entero(datos, campo, maximo):
    valor = datos.get(campo)
    if type(valor) is not int or not 0 <= valor <= maximo:
        raise ValueError("Introduce un número válido.")
    return valor


def aplicar(juego, persona, datos):
    accion = datos.get("accion")
    if accion == "entrar":
        nombre = datos.get("nombre")
        if persona == nombre and persona:
            return persona, None
        if persona:
            raise ValueError("Este navegador ya tiene un nombre asignado.")
        if nombre not in NOMBRES or nombre in juego["sesiones"]:
            raise ValueError("Ese nombre ya está ocupado. Elige el tuyo.")
        clave = secrets.token_urlsafe(32)
        juego["sesiones"][nombre] = clave
        return nombre, clave

    if not persona:
        raise ValueError("Elige tu nombre para participar.")

    if accion == "plan":
        grupo = equipo(persona, 0)
        if grupo in juego["planes"]:
            raise ValueError("Tu trío ya ha enviado su plan.")
        juego["planes"][grupo] = {
            campo: texto(datos, campo)
            for campo in ("lugar", "comida", "actividad")
        }
        juego["planes"][grupo]["centimos"] = entero(datos, "centimos", 3000)

    elif accion == "historia":
        if len(juego["planes"]) != 4:
            raise ValueError("Falta algún plan de cumpleaños.")
        if persona in juego["historias"]:
            raise ValueError("Tu historia ya está guardada.")
        juego["historias"][persona] = {
            "frase": texto(datos, "frase"),
            "edad": entero(datos, "edad", 120),
        }
        if len(juego["historias"]) == len(NOMBRES):
            orden = NOMBRES.copy()
            secrets.SystemRandom().shuffle(orden)
            juego["orden"] = orden

    elif accion == "votar":
        quien = turno(juego)
        if not quien or quien != datos.get("quien") or quien == persona:
            raise ValueError("Esta apuesta no corresponde al turno actual.")
        votos = juego["votos"].setdefault(quien, {})
        if persona in votos:
            raise ValueError("Tu apuesta ya está guardada.")
        votos[persona] = entero(datos, "edad", 120)

    elif accion == "consejo":
        if not juego["orden"] or turno(juego):
            raise ValueError("Todavía estáis jugando a las edades.")
        grupo = equipo(persona, 1)
        if grupo in juego["consejos"]:
            raise ValueError("Tu grupo ya ha publicado su frase.")
        juego["consejos"][grupo] = {
            "autor": persona,
            "frase": texto(datos, "frase"),
        }
    else:
        raise ValueError("Acción desconocida.")

    return persona, None


def vista(juego, persona):
    # Solo se envían al móvil los datos que ya se pueden mostrar.
    if not persona:
        return {
            "yo": None,
            "disponibles": [n for n in NOMBRES if n not in juego["sesiones"]],
        }

    quien = turno(juego)
    terminados = [
        n for n in juego["orden"]
        if len(juego["votos"].get(n, {})) == len(NOMBRES) - 1
    ]
    puntos = {
        n: sum(
            juego["votos"][autor].get(n) == juego["historias"][autor]["edad"]
            for autor in terminados
        )
        for n in NOMBRES
    }
    ronda = 1 if len(juego["planes"]) < 4 else 2
    if len(terminados) == len(NOMBRES):
        ronda = 3

    votos = juego["votos"].get(quien, {})
    return {
        "yo": persona,
        "ronda": ronda,
        "grupos": GRUPOS,
        "misGrupos": [equipo(persona, 0), equipo(persona, 1)],
        "planes": juego["planes"],
        "historiasRecibidas": len(juego["historias"]),
        "yaEscribi": persona in juego["historias"],
        "quien": quien,
        "pregunta": juego["historias"][quien]["frase"] if quien else "",
        "yaVote": persona in votos,
        "numVotos": len(votos),
        "reveladas": [
            {"nombre": n, **juego["historias"][n]} for n in terminados
        ],
        "puntos": puntos if ronda == 3 else {},
        "consejos": juego["consejos"],
    }


HTML = r"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Los 30 de Cristian</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#183334;color:#fff6e3;font:17px/1.5 system-ui}
main{max-width:720px;margin:auto;padding:24px 16px 64px}
h1,h2,h3{font-family:Georgia,serif;line-height:1.15}
h1{font-size:clamp(38px,8vw,66px);margin:15px 0 25px}
section,article,details{background:#fff8eb;color:#213c39;border-radius:12px;padding:18px;margin:14px 0}
article{background:#efe9da}h2{margin-top:0}
label{display:block;margin:14px 0;font-weight:600}
input,textarea,select,button{display:block;width:100%;margin-top:6px;padding:12px;border:1px solid #87978e;border-radius:7px;font:inherit}
textarea{min-height:75px}button{background:#20584b;color:white;cursor:pointer}
button:disabled{opacity:.55}.mio{font-weight:bold;color:#15644f}
#aviso{color:#ffda91}summary{cursor:pointer;font-weight:650}
</style>
<main>
<h1>Los 30 de Cristian</h1>
<p id="aviso" role="status"></p>
<div id="juego">Conectando con la mesa…</div>
</main>
<script>
const panel = document.querySelector("#juego");
const aviso = document.querySelector("#aviso");
let enviando = false, leyendo = false, version = 0, ultimoHTML = "";

function esc(s) {
  const e = document.createElement("span");
  e.textContent = String(s);
  return e.innerHTML;
}
function campo(titulo, nombre, tipo="text", max=120) {
  const input = tipo === "text"
    ? `<textarea name="${nombre}" maxlength="500" required></textarea>`
    : `<input type="number" name="${nombre}" min="0" max="${max}"
        step="${nombre === "euros" ? "0.01" : "1"}" required>`;
  return `<label>${titulo}${input}</label>`;
}
function form(accion, contenido, boton, quien="") {
  return `<form data-accion="${accion}" data-quien="${quien}">
    ${contenido}<button>${boton}</button></form>`;
}
function grupos(s, r) {
  return s.grupos[r].map((g,i) => {
    const mio = String(i) === s.misGrupos[r];
    return `<p class="${mio ? "mio" : ""}">${mio ? "Tu trío" : "Trío "+(i+1)}
      · ${g.map(esc).join(", ")}</p>`;
  }).join("");
}
function dibujar(s) {
  let html = "";
  if (!s.yo) {
    const opciones = s.disponibles.map(n => `<option>${esc(n)}</option>`).join("");
    html = `<section><h2>¿Quién eres?</h2><p>Usa el mismo navegador durante la cena.</p>${
      opciones ? form("entrar",
        `<select required name="nombre"><option value="">Elige tu nombre</option>${opciones}</select>`,
        "Ver mi trío") : "<p>Todos los nombres están asignados.</p>"
    }</section>`;
  } else {
    html = `<p>${esc(s.yo)} · Ronda ${s.ronda} de 3</p>`;
    if (s.ronda === 1) {
      html += `<section><h2>El cumple ideal con 30 €</h2>
        <p>Tenéis 30 € en total. Acordad un plan para Cristian y que una persona lo envíe.</p>
        ${grupos(s,0)}`;
      html += s.planes[s.misGrupos[0]]
        ? `<p>Plan guardado. Han respondido ${Object.keys(s.planes).length} de 4 tríos.</p>`
        : form("plan", campo("¿Adónde iría Cristian?","lugar")
            + campo("¿Qué comería?","comida")
            + campo("¿Qué haría allí?","actividad")
            + campo("Coste total en euros","euros","number",30), "Enviar el plan");
      html += "</section>";
    }
    if (s.ronda === 2) {
      html += "<section><h2>¿A qué edad me pasó?</h2>";
      if (!s.yaEscribi) {
        html += `<p>Escribe una anécdota sin desvelar la edad. Solo se revelará
          cuando los otros once hayan apostado.</p>`;
        html += form("historia", campo("Mi anécdota, por ejemplo «Se me cayó el primer diente»","frase")
          + campo("Mi edad en años cumplidos (privada)","edad","number"), "Guardar en secreto");
      } else if (!s.quien) {
        html += `<p>Tu anécdota está guardada. Llevamos ${s.historiasRecibidas} de 12.</p>`;
      } else {
        html += `<p>Turno ${s.reveladas.length+1} de 12 · ${s.numVotos}/11 apuestas</p>
          <h3>${esc(s.quien)}</h3><blockquote>«${esc(s.pregunta)}»</blockquote>`;
        if (s.quien === s.yo) html += "<p>¡Es tu historia! Deja que los demás adivinen.</p>";
        else if (s.yaVote) html += "<p>Tu apuesta está guardada.</p>";
        else html += form("votar",campo("¿Cuántos años tenía?","edad","number"),"Apostar",s.quien);
      }
      html += "</section>";
    }
    if (s.ronda === 3) {
      const lista = Object.entries(s.puntos).sort((a,b)=>b[1]-a[1]);
      const ganadores = lista.filter(a=>a[1]===lista[0][1]).map(a=>a[0]);
      html += `<section><h2>🏆 ${ganadores.length>1 ? "Primer puesto compartido" : "Primer puesto"}</h2>
        <p>${ganadores.map(esc).join(", ")} · ${lista[0][1]} aciertos</p>
        <details><summary>Clasificación completa</summary>
        ${lista.map(([n,p])=>`<p>${esc(n)} · ${p}</p>`).join("")}</details></section>
        <section><h2>Antes de los 40</h2>${grupos(s,1)}
        <p>¿Qué le recomendáis a Cristian antes de cumplir los 40? Una persona del trío publica la frase.</p>`;
      html += s.consejos[s.misGrupos[1]] ? "<p>Vuestro consejo ya está publicado.</p>"
        : form("consejo",campo("Cristian, antes de los 40 te recomendamos…","frase"),"Publicar en el chat");
      html += "<h3>Chat de la mesa</h3>" + Object.entries(s.consejos).map(([i,c])=>
        `<article><b>${esc(c.autor)} · Trío ${Number(i)+1}</b><p>${esc(c.frase)}</p></article>`
      ).join("") + "</section>";
    }
    if (s.reveladas.length) {
      html += `<details><summary>Edades reveladas</summary>${[...s.reveladas].reverse().map(h=>
        `<p><b>${esc(h.nombre)} · ${h.edad} años</b><br>${esc(h.frase)}</p>`
      ).join("")}</details>`;
    }
    if (Object.keys(s.planes).length) {
      html += `<details><summary>Planes de los tríos</summary>${Object.entries(s.planes).map(([i,p])=>
        `<article><b>${s.grupos[0][i].map(esc).join(", ")}</b>
        <p>${esc(p.lugar)} · ${esc(p.comida)} · ${esc(p.actividad)}
        · ${(p.centimos/100).toLocaleString("es-ES")} €</p></article>`
      ).join("")}</details>`;
    }
  }

  // Al recibir novedades, conserva el formulario activo y lo que se está escribiendo.
  if (html === ultimoHTML) return;
  const anterior = panel.querySelector("form");
  const abiertos = new Set([...panel.querySelectorAll("details[open]")].map(d=>d.querySelector("summary").textContent));
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  const nuevo = tmp.querySelector("form");
  if (anterior && nuevo && anterior.dataset.accion === nuevo.dataset.accion
      && anterior.dataset.quien === nuevo.dataset.quien && nuevo.dataset.accion !== "entrar") {
    const marcador = document.createComment("formulario");
    nuevo.replaceWith(marcador);
    const foco = anterior.contains(document.activeElement) ? document.activeElement : null;
    panel.replaceChildren(...tmp.childNodes);
    marcador.replaceWith(anterior);
    if (foco) foco.focus({preventScroll:true});
  } else {
    const elegido = anterior?.elements.namedItem("nombre")?.value;
    panel.replaceChildren(...tmp.childNodes);
    const selector = panel.querySelector("select");
    if (selector && elegido && [...selector.options].some(o=>o.value===elegido)) selector.value=elegido;
  }
  panel.querySelectorAll("details").forEach(d=>{
    d.open=abiertos.has(d.querySelector("summary").textContent);
  });
  ultimoHTML = html;
}

async function leer() {
  if (leyendo || enviando) return;
  leyendo = true;
  const v = version;
  try {
    const r = await fetch("/estado",{cache:"no-store"});
    if (!r.ok) throw Error();
    const s = await r.json();
    if (version === v) {
      dibujar(s);
      if (aviso.dataset.red === "1") {aviso.textContent=""; aviso.dataset.red="";}
    }
  } catch {
    if (version === v) {
      aviso.textContent="Reconectando con la mesa…";
      aviso.dataset.red="1";
    }
  } finally { leyendo=false; }
}

panel.addEventListener("submit", async e=>{
  e.preventDefault();
  if (enviando) return;
  const f=e.target, datos=Object.fromEntries(new FormData(f));
  datos.accion=f.dataset.accion;
  if (f.dataset.quien) datos.quien=f.dataset.quien;
  if ("edad" in datos) datos.edad=Number(datos.edad);
  if ("euros" in datos) datos.centimos=Math.round(Number(datos.euros)*100);
  enviando=true; version++;
  const boton=f.querySelector("button");
  boton.disabled=true; aviso.textContent=""; aviso.dataset.red="";
  try {
    const r=await fetch("/accion",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(datos)});
    const s=await r.json();
    if (!r.ok) throw Error(s.error || "No se ha podido enviar.");
    dibujar(s);
  } catch(err) {aviso.textContent=err.message;}
  finally {enviando=false; boton.disabled=false; leer();}
});
leer();
setInterval(leer,2500);
document.addEventListener("visibilitychange",()=>{if (!document.hidden) leer();});
</script></html>"""


class Servidor(BaseHTTPRequestHandler):
    def responder(self, estado, contenido, tipo="application/json", clave=None):
        if tipo == "application/json":
            contenido = json.dumps(contenido, ensure_ascii=False)
        cuerpo = contenido.encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        if clave:
            segura = "; Secure" if os.environ.get("COOKIE_SECURE") == "1" else ""
            self.send_header(
                "Set-Cookie",
                f"jugador={clave}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000{segura}",
            )
        self.end_headers()
        self.wfile.write(cuerpo)

    def procesar(self, datos=None):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        guardada = cookie.get("jugador")
        token = guardada.value if guardada else ""
        conexion = sqlite3.connect(BD, timeout=15)
        try:
            # Cada envío se aplica por completo, incluso con varios móviles a la vez.
            conexion.execute("BEGIN IMMEDIATE" if datos is not None else "BEGIN")
            fila = conexion.execute("SELECT datos FROM fiesta WHERE id=1").fetchone()
            juego = json.loads(fila[0])
            persona = next(
                (n for n, k in juego["sesiones"].items() if secrets.compare_digest(k, token)),
                None,
            )
            nueva_clave = None
            if datos is not None:
                persona, nueva_clave = aplicar(juego, persona, datos)
                conexion.execute(
                    "UPDATE fiesta SET datos=? WHERE id=1",
                    (json.dumps(juego, ensure_ascii=False),),
                )
            resultado = vista(juego, persona)
            conexion.commit()
        except ValueError as exc:
            conexion.rollback()
            self.responder(HTTPStatus.CONFLICT, {"error": str(exc)})
            return
        except sqlite3.Error:
            conexion.rollback()
            self.responder(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "Vuelve a intentarlo."})
            return
        finally:
            conexion.close()
        self.responder(HTTPStatus.OK, resultado, clave=nueva_clave)

    def do_GET(self):
        ruta = urlsplit(self.path).path
        if ruta == "/":
            self.responder(HTTPStatus.OK, HTML, "text/html")
        elif ruta == "/estado":
            self.procesar()
        else:
            self.responder(HTTPStatus.NOT_FOUND, {"error": "Página desconocida."})

    def do_POST(self):
        if urlsplit(self.path).path != "/accion":
            self.responder(404, {"error": "Ruta desconocida."})
            return
        try:
            if self.headers.get_content_type() != "application/json":
                raise ValueError
            longitud = int(self.headers.get("Content-Length", "0"))
            if not 0 < longitud <= 10000:
                raise ValueError
            datos = json.loads(self.rfile.read(longitud))
            if not isinstance(datos, dict):
                raise ValueError
        except (ValueError, UnicodeError):
            self.responder(400, {"error": "Petición inválida."})
            return
        self.procesar(datos)


if __name__ == "__main__":
    with sqlite3.connect(BD) as conexion:
        conexion.execute("PRAGMA journal_mode=WAL")
        conexion.execute(
            "CREATE TABLE IF NOT EXISTS fiesta "
            "(id INTEGER PRIMARY KEY, datos TEXT NOT NULL)"
        )
        conexion.execute(
            "INSERT OR IGNORE INTO fiesta VALUES(1,?)",
            (json.dumps(partida_nueva()),),
        )
    puerto = int(os.environ.get("PORT", "8000"))
    print(f"Juego disponible en http://localhost:{puerto}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", puerto), Servidor).serve_forever()
