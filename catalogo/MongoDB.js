use Catalogos;

// COLECCIÓN 1: categorias 
db.createCollection("categorias", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["conector", "nombre", "activa"],
      additionalProperties: false,
      properties: {
        _id: { bsonType: "objectId" },
        conector: {
          bsonType: "string",
          pattern: "^[a-z0-9-]+$",
          description: "Identificador URL en minúsculas sin espacios"
        },
        nombre: {
          bsonType: "string",
          minLength: 3,
          description: "Nombre visible de la categoría"
        },
        descripcion: {
          bsonType: "string"
        },
        activa: {
          bsonType: "bool"
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

db.categorias.createIndex({ slug: 1 }, { unique: true });

// Colección de productos, utiliza las categorias
db.createCollection("productos", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "nombre", "categoria", "precio", "atributos", "activo"],
      properties: {
        _id: { bsonType: "objectId" },
        sku: {
          bsonType: "string",
          minLength: 4,
          description: "Código único de producto"
        },
        nombre: {
          bsonType: "string",
          minLength: 2,
          description: "Nombre comercial del producto"
        },
        descripcion: {
          bsonType: "string"
        },
        categoria: {
          bsonType: "string",
          description: "Conector de la categoría para filtrado"
        },
        precio: {
          bsonType: ["double", "int", "decimal"],
          minimum: 0,
          description: "Precio unitario mayor o igual a 0"
        },
        atributos: {
          bsonType: "object",
          minProperties: 1,
          description: "Objeto flexible con especificaciones propias de cada tipo de producto"
        },
        activo: {
          bsonType: "bool"
        },
        fecha_actualizacion: {
          bsonType: "date"
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

db.productos.createIndex({ sku: 1 }, { unique: true });
db.productos.createIndex({ categoria: 1, precio: 1 });
db.productos.createIndex({ nombre: "text" });

db.categorias.insertMany([
  { slug: "linea-blanca", nombre: "Línea Blanca", descripcion: "Electrodomésticos mayores", activa: true },
  { slug: "ropa", nombre: "Ropa y Calzado", descripcion: "Prendas de vestir", activa: true },
  { slug: "electronica", nombre: "Electrónica", descripcion: "Cómputo y dispositivos", activa: true }
]);

db.productos.insertMany([
  {
    _id: ObjectId("673b1a000000000000000001"),
    sku: "REF-SAM-001",
    nombre: "Refrigerador Samsung French Door",
    descripcion: "Refrigerador de acero inoxidable con dispensador",
    categoria: "linea-blanca",
    precio: 18500.00,
    atributos: {
      capacidad_pies_cubicos: 22,
      voltaje: "110V",
      eficiencia_energetica: "A++",
      color: "Plata"
    },
    activo: true,
    fecha_actualizacion: new Date()
  },
  {
    _id: ObjectId("673b1a000000000000000002"),
    sku: "CAM-LEV-002",
    nombre: "Camisa Casual Manga Larga",
    descripcion: "Camisa corte regular 100% algodón",
    categoria: "ropa",
    precio: 599.00,
    atributos: {
      talla: "M",
      material: "Algodón",
      corte: "Regular Fit",
      color: "Azul Marino"
    },
    activo: true,
    fecha_actualizacion: new Date()
  },
  {
    _id: ObjectId("673b1a000000000000000003"),
    sku: "LAP-ASU-003",
    nombre: "Laptop ASUS Vivobook 15",
    descripcion: "Equipo portátil para desarrollo y oficina",
    categoria: "electronica",
    precio: 14200.00,
    atributos: {
      procesador: "AMD Ryzen 7",
      ram_gb: 16,
      almacenamiento_ssd_gb: 512,
      pantalla_pulgadas: 15.6
    },
    activo: true,
    fecha_actualizacion: new Date()
  }
]);