CREATE DATABASE IF NOT EXISTS inventatech_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE inventatech_db;

CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    nombre_usuario VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    contrasena VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL DEFAULT 'vendedor',
    estado ENUM('Activo', 'Inactivo') NOT NULL DEFAULT 'Activo',
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS categorias (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS productos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    sku VARCHAR(50) NOT NULL UNIQUE,
    costo DECIMAL(12,2) NOT NULL DEFAULT 0.00 CHECK (costo >= 0),
    precio DECIMAL(12,2) NOT NULL CHECK (precio >= 0),
    stock INT NOT NULL DEFAULT 0 CHECK (stock >= 0),
    categoria_id INT NULL,
    CONSTRAINT fk_productos_categoria FOREIGN KEY (categoria_id)
        REFERENCES categorias(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS clientes (
    id_cliente INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    email VARCHAR(255) NULL,
    telefono VARCHAR(40) NULL,
    direccion VARCHAR(255) NULL,
    ciudad VARCHAR(100) NULL,
    pais VARCHAR(100) NOT NULL DEFAULT 'Colombia',
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ventas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT NOT NULL,
    producto_id INT NOT NULL,
    cantidad INT NOT NULL CHECK (cantidad > 0),
    precio_unitario DECIMAL(12,2) NOT NULL,
    costo_unitario DECIMAL(12,2) NOT NULL,
    total DECIMAL(12,2) NOT NULL,
    usuario_id INT NOT NULL,
    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ventas_cliente FOREIGN KEY (cliente_id) REFERENCES clientes(id_cliente),
    CONSTRAINT fk_ventas_producto FOREIGN KEY (producto_id) REFERENCES productos(id),
    CONSTRAINT fk_ventas_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id_usuario)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS historial_facturas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    numero_factura VARCHAR(32) NOT NULL UNIQUE,
    venta_id INT NOT NULL UNIQUE,
    cliente_id INT NOT NULL,
    subtotal DECIMAL(12,2) NOT NULL,
    total DECIMAL(12,2) NOT NULL,
    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_facturas_venta FOREIGN KEY (venta_id) REFERENCES ventas(id),
    CONSTRAINT fk_facturas_cliente FOREIGN KEY (cliente_id) REFERENCES clientes(id_cliente)
) ENGINE=InnoDB;

INSERT IGNORE INTO categorias (nombre) VALUES
    ('Periféricos'), ('Mantenimiento'), ('Almacenamiento'), ('Memorias');

-- Credencial inicial para acceder por primera vez: admin / admin123.
-- La contraseña está almacenada como hash Werkzeug.
INSERT INTO usuarios (nombre_usuario, email, contrasena, rol, estado)
VALUES ('admin', 'admin@inventatech.local', 'scrypt:32768:8:1$Rfamoa2UlX3XF8mN$786aba8adecb2e9e9ab3547430169029dfc870e274cb7d542ef29afd32cc4622a9382a60b826d60ca4a3c9fc805540b6000b35af488857acbe8213b26f19e2a1', 'administrador', 'Activo')
ON DUPLICATE KEY UPDATE nombre_usuario = VALUES(nombre_usuario);
