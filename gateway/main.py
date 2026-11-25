from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse
import httpx, os, logging, asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")

CATALOGO_URL  = os.getenv("CATALOGO_URL",  "http://localhost:4001")
CARRITO_URL   = os.getenv("CARRITO_URL",   "http://localhost:4002")
ORDENES_URL   = os.getenv("ORDENES_URL",   "http://localhost:4003")

TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT", 10))  # segundos

RUTAS = {
    "/catalogo":   CATALOGO_URL,
    "/carrito":    CARRITO_URL,
    "/ordenes":    ORDENES_URL,
    "/inventario": ORDENES_URL,   # inventario vive en el servicio de órdenes
}

_http_client: httpx.AsyncClient | None = None

async def get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=TIMEOUT)
    return _http_client

# ─────────────────── APP ───────────────────
app = FastAPI(
    title="API Gateway — Tienda Departamental",
    description="""
Punto de entrada único a los tres microservicios.
| `/catalogo` | Catálogo (MongoDB + Redis) | 4001 |
| `/carrito` | Carrito (Redis) | 4002 |
| `/ordenes` | Órdenes e Inventario (PostgreSQL) | 4003 |
| `/inventario` | (mismo servicio de órdenes) | 4003 |
    """,
    version="1.0.0"
)

@app.on_event("shutdown")
async def shutdown():
    if _http_client:
        await _http_client.aclose()

@app.get("/health", tags=["Gateway"])
async def health():

    async def ping(nombre: str, url: str) -> dict:
        try:
            client = await get_client()
            resp = await client.get(f"{url}/health", timeout=3)
            return {"servicio": nombre, "estado": "ok", "codigo": resp.status_code}
        except httpx.ConnectError:
            return {"servicio": nombre, "estado": "sin conexión"}
        except httpx.TimeoutException:
            return {"servicio": nombre, "estado": "timeout"}
        except Exception as e:
            return {"servicio": nombre, "estado": f"error: {e}"}

    resultados = await asyncio.gather(
        ping("catalogo",  CATALOGO_URL),
        ping("carrito",   CARRITO_URL),
        ping("ordenes",   ORDENES_URL),
    )

    todo_ok = all(r["estado"] == "ok" for r in resultados)
    return {
        "gateway": "ok",
        "estado_global": "ok" if todo_ok else "degradado",
        "servicios": resultados
    }


@app.api_route(
    "/{prefijo}/{ruta:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    tags=["Proxy"],
    summary="Reenvía la petición al microservicio correspondiente",
    include_in_schema=False
)
async def proxy(prefijo: str, ruta: str, request: Request):

    clave = f"/{prefijo}"
    if clave not in RUTAS:
        raise HTTPException(
            404,
            detail=f"Ruta '/{prefijo}/...' no existe. "
                   f"Prefijos válidos: {list(RUTAS.keys())}"
        )

    destino_base = RUTAS[clave]
    # La ruta interna del servicio NO lleva el prefijo del gateway
    # /catalogo/productos/123  →  http://EC2-catálogo:4001/productos/123
    ruta_interna = f"/{ruta}" if ruta else "/"
    url_destino  = f"{destino_base}{ruta_interna}"

    # Preservar query string (?categoria=ropa&precio_min=100)
    if request.url.query:
        url_destino += f"?{request.url.query}"

    # Leer body (para POST/PUT)
    body = await request.body()
