-- 1. Tabla de inventario (esta es la que tiene que avisar de disponibilidad al redis)
CREATE TABLE IF NOT EXISTS inventario (
    producto_id VARCHAR(50) PRIMARY KEY,
    sku VARCHAR(30) UNIQUE NOT NULL,
    stock_disponible INT NOT NULL CHECK (stock_disponible >= 0),
    ultima_actualizacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabla de ordenes (con partición, separando datos de compra con el producto, el 3 tiene la orden en elementos)
CREATE TABLE IF NOT EXISTS ordenes (
    orden_id SERIAL PRIMARY KEY,
    cliente_id VARCHAR(50) NOT NULL,
    total NUMERIC(10, 2) NOT NULL CHECK (total >= 0),
    estado VARCHAR(20) NOT NULL DEFAULT 'COMPLETADA'
        CHECK (estado IN ('PENDIENTE', 'COMPLETADA', 'CANCELADA')),
    fecha_creacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabla de Detalles de Orden (es una lista incremental 1:N de elementos)
CREATE TABLE IF NOT EXISTS orden_detalles (
    detalle_id SERIAL PRIMARY KEY,
    orden_id INT NOT NULL,
    producto_id VARCHAR(50) NOT NULL,
    cantidad INT NOT NULL CHECK (cantidad > 0),
    precio_unitario NUMERIC(10, 2) NOT NULL CHECK (precio_unitario >= 0),
    subtotal NUMERIC(10, 2) GENERATED ALWAYS AS (cantidad * precio_unitario) STORED,

    CONSTRAINT fk_orden
        FOREIGN KEY (orden_id) REFERENCES ordenes (orden_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_inventario_producto
        FOREIGN KEY (producto_id) REFERENCES inventario (producto_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_ordenes_cliente_fecha ON ordenes (cliente_id, fecha_creacion DESC);

CREATE INDEX idx_detalles_orden_id ON orden_detalles (orden_id);
CREATE INDEX idx_detalles_producto_id ON orden_detalles (producto_id);

-- datos de prueba
INSERT INTO inventario (producto_id, sku, stock_disponible) VALUES
    ('673b1a000000000000000001', 'REF-SAM-001', 5),
    ('673b1a000000000000000002', 'CAM-LEV-002', 1),
    ('673b1a000000000000000003', 'LAP-ASU-003', 10)
ON CONFLICT (producto_id) DO NOTHING;
