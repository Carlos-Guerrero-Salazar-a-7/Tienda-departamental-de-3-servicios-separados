from fastapi import FastAPI, Request, HTTPException, Response
import httpx, os, logging, asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")

# urls de servicios (usar ip privada en aws)
CATALOGO_URL = os.getenv("CATALOGO_URL", "http://localhost:4001")
CARRITO_URL  = os.getenv("CARRITO_URL",  "http://localhost:4002")
ORDENES_URL  = os.getenv("ORDENES_URL",  "http://localhost:4003")

TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT", 10))

# mapeo de prefijos a servicios
RUTAS = {
    "/catalogo":   CATALOGO_URL,
    "/carrito":    CARRITO_URL,
    "/ordenes":    ORDENES_URL,
    "/inventario": ORDENES_URL,
}

# cliente http reutilizable
_http_client: httpx.AsyncClient | None = None

async def get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=TIMEOUT)
    return _http_client

app = FastAPI(
    title="api gateway - tienda departamental",
    description="""
punto de entrada a los microservicios.
| `/catalogo` | catalogo (mongodb + redis) | 4001 |
| `/carrito` | carrito (redis) | 4002 |
| `/ordenes` | ordenes e inventario (postgresql) | 4003 |
| `/inventario` | ordenes e inventario (postgresql) | 4003 |
    """,
    version="1.0.0"
)

@app.on_event("shutdown")
async def shutdown():
    if _http_client:
        await _http_client.aclose()

@app.get("/health", tags=["gateway"])
async def health():
    # revisa el estado de los servicios en paralelo
    async def ping(nombre: str, url: str) -> dict:
        try:
            client = await get_client()
            resp = await client.get(f"{url}/health", timeout=3)
            return {"servicio": nombre, "estado": "ok", "codigo": resp.status_code}
        except httpx.ConnectError:
            return {"servicio": nombre, "estado": "sin conexion"}
        except httpx.TimeoutException:
            return {"servicio": nombre, "estado": "timeout"}
        except Exception as e:
            return {"servicio": nombre, "estado": f"error: {e}"}

    resultados = await asyncio.gather(
        ping("catalogo", CATALOGO_URL),
        ping("carrito",  CARRITO_URL),
        ping("ordenes",  ORDENES_URL),
    )

    todo_ok = all(r["estado"] == "ok" for r in resultados)
    return {
        "gateway": "ok",
        "estado_global": "ok" if todo_ok else "degradado",
        "servicios": resultados
    }

# proxy generico para reenviar peticiones
@app.api_route(
    "/{prefijo}/{ruta:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    tags=["proxy"],
    summary="reenvia la peticion al microservicio",
    include_in_schema=False
)
async def proxy(prefijo: str, ruta: str, request: Request):
    clave = f"/{prefijo}"
    if clave not in RUTAS:
        raise HTTPException(
            404,
            detail=f"ruta '/{prefijo}/...' no existe. validos: {list(RUTAS.keys())}"
        )

    destino_base = RUTAS[clave]
    ruta_interna = f"/{ruta}" if ruta else "/"
    url_destino  = f"{destino_base}{ruta_interna}"

    if request.url.query:
        url_destino += f"?{request.url.query}"

    body = await request.body()

    # elimina headers conflictivos
    headers = dict(request.headers)
    for h in ("host", "content-length"):
        headers.pop(h, None)

    logger.info(f"proxy {request.method} {request.url.path} -> {url_destino}")

    try:
        client = await get_client()
        resp = await client.request(
            method=request.method,
            url=url_destino,
            headers=headers,
            content=body,
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )

    except httpx.ConnectError:
        logger.error(f"sin conexion a '{prefijo}' en {destino_base}")
        raise HTTPException(
            503,
            detail={
                "error": "servicio_no_disponible",
                "servicio": prefijo,
                "mensaje": f"el servicio '{prefijo}' no esta disponible."
            }
        )
    except httpx.TimeoutException:
        logger.error(f"timeout en '{prefijo}'")
        raise HTTPException(
            504,
            detail={
                "error": "timeout",
                "servicio": prefijo,
                "mensaje": f"el servicio '{prefijo}' tardo demasiado en responder."
            }
        )
    except Exception as e:
        logger.exception(f"error en proxy hacia '{prefijo}'")
        raise HTTPException(500, detail=f"error interno del gateway: {e}")

# rutas documentadas: catalogo
@app.get("/catalogo/productos", tags=["catalogo"])
async def listar_productos(request: Request):
    # filtra por categoria y rango de precio
    return await proxy("catalogo", "productos", request)

@app.get("/catalogo/productos/{producto_id}", tags=["catalogo"])
async def detalle_producto(producto_id: str, request: Request):
    # obtiene detalle con cache redis
    return await proxy("catalogo", f"productos/{producto_id}", request)

@app.post("/catalogo/productos", tags=["catalogo"])
async def crear_producto(request: Request):
    # crea producto en mongodb
    return await proxy("catalogo", "productos", request)

@app.put("/catalogo/productos/{producto_id}", tags=["catalogo"])
async def actualizar_producto(producto_id: str, request: Request):
    # actualiza producto e invalida cache
    return await proxy("catalogo", f"productos/{producto_id}", request)

@app.get("/catalogo/productos/{producto_id}/reseñas", tags=["catalogo"])
async def ver_reseñas(producto_id: str, request: Request):
    return await proxy("catalogo", f"productos/{producto_id}/reseñas", request)

@app.post("/catalogo/productos/{producto_id}/reseñas", tags=["catalogo"])
async def agregar_reseña(producto_id: str, request: Request):
    return await proxy("catalogo", f"productos/{producto_id}/reseñas", request)

@app.get("/catalogo/categorias", tags=["catalogo"])
async def listar_categorias(request: Request):
    return await proxy("catalogo", "categorias", request)

# rutas documentadas: carrito
@app.get("/carrito/{cliente_id}", tags=["carrito"])
async def ver_carrito(cliente_id: str, request: Request):
    # consulta items, total y ttl
    return await proxy("carrito", f"carrito/{cliente_id}", request)

@app.post("/carrito/{cliente_id}/items", tags=["carrito"])
async def agregar_item(cliente_id: str, request: Request):
    return await proxy("carrito", f"carrito/{cliente_id}/items", request)

@app.put("/carrito/{cliente_id}/items/{producto_id}", tags=["carrito"])
async def actualizar_item(cliente_id: str, producto_id: str, request: Request):
    return await proxy("carrito", f"carrito/{cliente_id}/items/{producto_id}", request)

@app.delete("/carrito/{cliente_id}/items/{producto_id}", tags=["carrito"])
async def eliminar_item(cliente_id: str, producto_id: str, request: Request):
    return await proxy("carrito", f"carrito/{cliente_id}/items/{producto_id}", request)

@app.delete("/carrito/{cliente_id}", tags=["carrito"])
async def vaciar_carrito(cliente_id: str, request: Request):
    return await proxy("carrito", f"carrito/{cliente_id}", request)

# rutas documentadas: ordenes e inventario
@app.post("/ordenes", tags=["ordenes"])
async def confirmar_compra(request: Request):
    # crea orden, descuenta stock y vacia carrito
    return await proxy("ordenes", "ordenes", request)

@app.get("/ordenes/{cliente_id}", tags=["ordenes"])
async def historial_compras(cliente_id: str, request: Request):
    return await proxy("ordenes", f"ordenes/{cliente_id}", request)

@app.get("/inventario", tags=["inventario"])
async def ver_inventario(request: Request):
    return await proxy("inventario", "inventario", request)

@app.get("/inventario/{producto_id}", tags=["inventario"])
async def stock_producto(producto_id: str, request: Request):
    return await proxy("inventario", f"inventario/{producto_id}", request)

@app.post("/inventario", tags=["inventario"])
async def agregar_inventario(request: Request):
    return await proxy("inventario", "inventario", request)
```[cite: 1]
