from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import os, httpx, psycopg2, psycopg2.extras, logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ordenes")

# ─────────────────── CONFIGURACIÓN ───────────────────
PG_HOST      = os.getenv("POSTGRES_HOST",     "localhost")
PG_PORT      = int(os.getenv("POSTGRES_PORT", 5432))
PG_DB        = os.getenv("POSTGRES_DB",       "tienda_ordenes")
PG_USER      = os.getenv("POSTGRES_USER",     "admin")
PG_PASS      = os.getenv("POSTGRES_PASSWORD", "PostgresSeguro123")
CARRITO_URL  = os.getenv("CARRITO_URL",       "http://localhost:8002")
CATALOGO_URL = os.getenv("CATALOGO_URL",      "http://localhost:8001")

#conexion inicial
def get_conn():
    """
    Abre una conexión nueva a PostgreSQL.
    Se cierra al terminar cada request (no pool por simplicidad).
    """
    try:
        return psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASS,
            connect_timeout=5
        )
    except psycopg2.OperationalError as e:
        raise HTTPException(503, f"PostgreSQL no disponible: {e}")

class ConfirmarCompra(BaseModel):
    cliente_id: str

class AgregarInventario(BaseModel):
    sku: str
    stock_disponible: int

app = FastAPI(
    title="Servicio de Órdenes e Inventario",
    description="Gestiona órdenes y stock con PostgreSQL. Las compras son transaccionales.",
    version="1.0.0"
)

"""
@app.get("/health", tags=["Estado"])
def health():
    """Verifica que PostgreSQL esté accesible."""
    try:
        conn = get_conn()
        conn.close()
        return {"servicio": "ordenes", "postgresql": "ok", "estado": "ok"}
    except HTTPException as e:
        return {"servicio": "ordenes", "postgresql": "error", "estado": "degradado", "detalle": e.detail}
"""

#  CONFIRMA COMPRA (endpoint principal)

@app.post("/ordenes", status_code=201, tags=["Órdenes"])
async def confirmar_compra(body: ConfirmarCompra):
    cliente_id = body.cliente_id

    # 1. Obtener carrito desde el servicio de carrito
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{CARRITO_URL}/carrito/{cliente_id}")
        resp.raise_for_status()
        carrito = resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(503, f"Carrito no disponible: {e}")
    except Exception as e:
        raise HTTPException(503, f"No se pudo consultar el carrito: {e}")

    items = carrito.get("items", [])
    if not items:
        raise HTTPException(400, "El carrito está vacío")

    total = carrito.get("total", 0)

    # 2. TRANSACCIÓN en PostgreSQL
    conn = get_conn()
    conn.autocommit = False   # ← modo manual: nosotros hacemos commit/rollback
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # 2a. Para cada item: bloquear fila de inventario y verificar stock
        for item in items:
            producto_id = item["producto_id"]
            cantidad    = item["cantidad"]

            # SELECT ... FOR UPDATE → bloquea la fila hasta que hagamos commit
            # Esto evita que dos transacciones simultáneas lean el mismo stock
            cur.execute(
                """
                SELECT stock_disponible FROM inventario
                WHERE producto_id = %s
                FOR UPDATE
                """,
                (producto_id,)
            )
            fila = cur.fetchone()

            if not fila:
                raise HTTPException(404, f"Producto {producto_id} no tiene registro de inventario")

            if fila["stock_disponible"] < cantidad:
                raise HTTPException(
                    409,
                    f"Stock insuficiente para {producto_id}: "
                    f"disponible={fila['stock_disponible']}, solicitado={cantidad}"
                )

        # 2b. Insertar la orden
        cur.execute(
            """
            INSERT INTO ordenes (cliente_id, total, estado)
            VALUES (%s, %s, 'COMPLETADA')
            RETURNING orden_id, fecha_creacion
            """,
            (cliente_id, total)
        )
        orden = cur.fetchone()
        orden_id = orden["orden_id"]

        # 2c. Insertar detalles y descontar inventario
        for item in items:
            producto_id    = item["producto_id"]
            cantidad       = item["cantidad"]
            precio_unit    = item["precio"]

            cur.execute(
                """
                INSERT INTO orden_detalles (orden_id, producto_id, cantidad, precio_unitario)
                VALUES (%s, %s, %s, %s)
                """,
                (orden_id, producto_id, cantidad, precio_unit)
            )
            cur.execute(
                """
                UPDATE inventario
                SET stock_disponible = stock_disponible - %s,
                    ultima_actualizacion = NOW()
                WHERE producto_id = %s
                """,
                (cantidad, producto_id)
            )

        conn.commit()   # ← TODO bien → confirmar
        logger.info(f"Orden {orden_id} creada para cliente {cliente_id}")

    except HTTPException:
        conn.rollback()   # ← algo falló → deshace
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error en transacción: {e}")
        raise HTTPException(500, f"Error interno al procesar la orden: {e}")
    finally:
        cur.close()
        conn.close()

    # Vaciar el carrito (llamada al servicio de carrito)
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.delete(f"{CARRITO_URL}/carrito/{cliente_id}")
    except Exception as e:
        # El carrito fallará en expirar solo, pero la orden ya fue confirmada
        logger.warning(f"No se pudo vaciar el carrito de {cliente_id}: {e}")

    return {
        "mensaje": "Compra confirmada",
        "orden_id": orden_id,
        "cliente_id": cliente_id,
        "total": total,
        "items": len(items),
        "estado": "COMPLETADA"
    }


#HISTORIAL DE COMPRAS
@app.get("/ordenes/{cliente_id}", tags=["Órdenes"])
def historial_compras(cliente_id: str):
    """Regresa el historial de órdenes de un cliente, con sus detalles."""
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            """
            SELECT o.orden_id, o.total, o.estado, o.fecha_creacion,
                   json_agg(json_build_object(
                       'producto_id',   od.producto_id,
                       'cantidad',      od.cantidad,
                       'precio_unitario', od.precio_unitario,
                       'subtotal',      od.subtotal
                   )) AS items
            FROM ordenes o
            JOIN orden_detalles od ON o.orden_id = od.orden_id
            WHERE o.cliente_id = %s
            GROUP BY o.orden_id
            ORDER BY o.fecha_creacion DESC
            """,
            (cliente_id,)
        )
        ordenes = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return {
        "cliente_id": cliente_id,
        "total_ordenes": len(ordenes),
        "ordenes": [dict(o) for o in ordenes]
    }

"""
#  INVENTARIO
@app.get("/inventario", tags=["Inventario"])
def ver_inventario():
    """Lista el stock de todos los productos."""
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM inventario ORDER BY sku")
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return {"inventario": [dict(r) for r in rows]}


@app.get("/inventario/{producto_id}", tags=["Inventario"])
def stock_producto(producto_id: str):
    """Consulta el stock de un producto específico."""
    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM inventario WHERE producto_id = %s",
            (producto_id,)
        )
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()

    if not row:
        raise HTTPException(404, "Producto no encontrado en inventario")
    return dict(row)


@app.post("/inventario", status_code=201, tags=["Inventario"])
def agregar_inventario(body: AgregarInventario):
    """Agrega un producto al inventario (usado para pruebas o administración)."""
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO inventario (producto_id, sku, stock_disponible)
            VALUES (%s, %s, %s)
            ON CONFLICT (sku) DO UPDATE
            SET stock_disponible = EXCLUDED.stock_disponible,
                ultima_actualizacion = NOW()
            RETURNING producto_id
            """,
            (body.sku, body.sku, body.stock_disponible)
        )
        pid = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(400, f"Error: {e}")
    finally:
        cur.close()
        conn.close()
    return {"mensaje": "Inventario actualizado", "producto_id": pid}
"""