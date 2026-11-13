from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import io
import os
import uuid
from decimal import Decimal, InvalidOperation
import mysql.connector
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-this-secret")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "inventatech_db"),
    )


def parse_positive_int(value, field):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} debe ser un número entero.")
    if number <= 0:
        raise ValueError(f"{field} debe ser mayor que cero.")
    return number


def parse_nonnegative_decimal(value, field):
    try:
        number = Decimal(value)
    except (TypeError, InvalidOperation):
        raise ValueError(f"{field} debe ser un número válido.")
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field} no puede ser negativo.")
    return number

# ---------- INDEX ----------
@app.route('/')
def index():
    if 'usuario' not in session:
        return render_template(
            'index.html', productos=[], categorias=[], ventas=[], clientes=[], total_ingresos=0
        )

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT p.id, p.nombre, p.sku, p.costo, p.precio, p.stock,
               c.nombre AS categoria, p.categoria_id
        FROM productos p
        LEFT JOIN categorias c ON p.categoria_id = c.id
        ORDER BY p.id DESC
    """)
    productos = cursor.fetchall()

    cursor.execute("SELECT * FROM categorias")
    categorias = cursor.fetchall()

    cursor.execute("""
        SELECT v.id, p.nombre AS producto, p.sku, v.cantidad,
               v.precio_unitario, v.total, v.fecha, c.nombre AS cliente
        FROM ventas v
        JOIN productos p ON v.producto_id = p.id
        JOIN clientes c ON v.cliente_id = c.id_cliente
        ORDER BY v.fecha DESC
    """)
    ventas = cursor.fetchall()

    cursor.execute("SELECT id_cliente, nombre FROM clientes ORDER BY nombre")
    clientes = cursor.fetchall()

    total_ingresos = sum(v['total'] for v in ventas)

    cursor.close()
    conn.close()

    return render_template('index.html',
                           productos=productos, categorias=categorias,
                           ventas=ventas, clientes=clientes,
                           total_ingresos=total_ingresos)

# ---------- REPORTE PDF (sin cambios) ----------
@app.route('/descargar-reporte-pdf')
def descargar_reporte_pdf():
    if 'usuario' not in session:
        return redirect(url_for('index'))
    conexion = get_db_connection()
    cursor = conexion.cursor(dictionary=True)
    
    # 1. Consultar ventas y calcular totales y ganancias
    cursor.execute("""
        SELECT v.*, p.nombre as producto_nombre, p.costo
        FROM ventas v
        JOIN productos p ON v.producto_id = p.id
    """)
    ventas = cursor.fetchall()
    
    total_ventas = sum(v['total'] for v in ventas)
    total_costos = sum(v['cantidad'] * v['costo_unitario'] for v in ventas)
    ganancia_neta = total_ventas - total_costos
    
    margen = (ganancia_neta / total_ventas * 100) if total_ventas > 0 else 0
    
    # 2. Encontrar el producto más vendido
    cursor.execute("""
        SELECT p.nombre, SUM(v.cantidad) as total_vendidos 
        FROM ventas v 
        JOIN productos p ON v.producto_id = p.id 
        GROUP BY p.id 
        ORDER BY total_vendidos DESC LIMIT 1
    """)
    top_producto = cursor.fetchone()
    nombre_top = top_producto['nombre'] if top_producto else "Sin ventas registradas"

    cursor.close()
    conexion.close()

    # 3. Generar el PDF en una sola página con ReportLab
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elementos = []
    
    estilos = getSampleStyleSheet()
    
    estilo_titulo = ParagraphStyle('Titulo', parent=estilos['Heading1'], fontSize=20, textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    estilo_sub = ParagraphStyle('Sub', parent=estilos['Normal'], fontSize=10, textColor=colors.HexColor('#64748b'), spaceAfter=20)
    estilo_seccion = ParagraphStyle('Seccion', parent=estilos['Heading2'], fontSize=13, textColor=colors.HexColor('#1e293b'), spaceBefore=15, spaceAfter=8)
    estilo_cuerpo = ParagraphStyle('Cuerpo', parent=estilos['Normal'], fontSize=10, textColor=colors.HexColor('#334155'), leading=14, spaceAfter=10)
    
    estilo_th = ParagraphStyle('TH', parent=estilos['Normal'], fontSize=9, textColor=colors.whitesmoke, fontName='Helvetica-Bold')
    estilo_td = ParagraphStyle('TD', parent=estilos['Normal'], fontSize=9, textColor=colors.HexColor('#334155'), fontName='Helvetica', leading=11)
    
    elementos.append(Paragraph("<b>InventaTech — Reporte Ejecutivo de Gestión</b>", estilo_titulo))
    elementos.append(Paragraph("Informe de rendimiento financiero, control de inventarios y análisis operativo.", estilo_sub))
    
    elementos.append(Paragraph("<b>1. Resumen de Desempeño Operativo</b>", estilo_seccion))
    texto_analisis = (
        f"Durante el periodo actual de operaciones, el sistema ha registrado un volumen de ventas consolidado en <b>${total_ventas:,.0f} COP</b>, "
        f"con una inversión acumulada en costos de inventario de <b>${total_costos:,.0f} COP</b>. Esto genera una utilidad neta estimada de "
        f"<b>${ganancia_neta:,.0f} COP</b>, representando un margen de rentabilidad global del <b>{margen:.1f}%</b> sobre las transacciones efectuadas. "
        f"El artículo con mayor dinamismo comercial y preferencia por parte de los clientes ha sido <b>{nombre_top}</b>."
    )
    elementos.append(Paragraph(texto_analisis, estilo_cuerpo))
    
    elementos.append(Paragraph("<b>2. Indicadores Financieros Clave</b>", estilo_seccion))
    
    datos_resumen = [
        [Paragraph('Indicador / Métrica', estilo_th), Paragraph('Valor Financiero (COP)', estilo_th), Paragraph('Estado / Evaluación', estilo_th)],
        [Paragraph('Total Recaudado en Ventas', estilo_td), Paragraph(f"${total_ventas:,.0f}", estilo_td), Paragraph('Flujo de Ingresos Activo', estilo_td)],
        [Paragraph('Costo Total de Inversión', estilo_td), Paragraph(f"${total_costos:,.0f}", estilo_td), Paragraph('Capital Operativo Invertido', estilo_td)],
        [Paragraph('Ganancia / Utilidad Neta', estilo_td), Paragraph(f"${ganancia_neta:,.0f}", estilo_td), Paragraph(f"Margen: {margen:.1f}% (Saludable)", estilo_td)],
        [Paragraph('Producto Estrella (Top Sales)', estilo_td), Paragraph(str(nombre_top), estilo_td), Paragraph('Líder en Rotación de Stock', estilo_td)]
    ]
    
    tabla_resumen = Table(datos_resumen, colWidths=[150, 180, 202])
    tabla_resumen.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('TOPPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f8fafc')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#ffffff'), colors.HexColor('#f1f5f9')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('BOTTOMPADDING', (0,1), (-1,-1), 6),
        ('TOPPADDING', (0,1), (-1,-1), 6)
    ]))
    
    elementos.append(tabla_resumen)
    elementos.append(Spacer(1, 10))
    
    elementos.append(Paragraph("<b>3. Sugerencias y Recomendaciones Estratégicas</b>", estilo_seccion))
    texto_recomendaciones = (
        "• <b>Optimización de Stock:</b> Se recomienda asegurar un reabastecimiento prioritario del producto líder (" + str(nombre_top) + ") "
        "para evitar quiebres de inventario ante la alta demanda sostenida.<br/>"
        "• <b>Control de Costos:</b> Monitorear de cerca los costos de adquisición de los componentes para proteger el margen de ganancia actual superior al 20%.<br/>"
        "• <b>Estrategia Comercial:</b> Impulsar campañas de rotación para aquellos artículos de menor salida registrados en el sistema de inventarios."
    )
    elementos.append(Paragraph(texto_recomendaciones, estilo_cuerpo))
    
    elementos.append(Spacer(1, 20))
    estilo_footer = ParagraphStyle('Footer', parent=estilos['Normal'], fontSize=8, textColor=colors.HexColor('#94a3b8'), alignment=1)
    elementos.append(Paragraph("InventaTech POS & Inventory Management — Reporte generado automáticamente.", estilo_footer))
    
    doc.build(elementos)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="Reporte_Gerencial_InventaTech.pdf", mimetype='application/pdf')

# ---------- LOGIN con hash ----------
@app.route('/login', methods=['POST'])
def login():
    usuario    = request.form.get('username')
    contrasena = request.form.get('password')

    if not usuario or not contrasena:
        return "Credenciales incorrectas. <a href='/'>Volver</a>", 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT * FROM usuarios WHERE nombre_usuario = %s AND estado = 'Activo'",
        (usuario,)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and check_password_hash(user['contrasena'], contrasena):
        session.clear()
        session['usuario'] = user['nombre_usuario']
        session['usuario_id'] = user['id_usuario']
        session['rol']     = user['rol']
        return redirect(url_for('index'))

    return "Credenciales incorrectas. <a href='/'>Volver</a>", 401

# ---------- AGREGAR PRODUCTO ----------
@app.route('/agregar_producto', methods=['POST'])
def agregar_producto():
    if 'usuario' not in session:
        return redirect(url_for('index'))

    nombre = request.form.get('nombre', '').strip()
    sku = request.form.get('sku', '').strip()
    categoria_id = request.form.get('categoria_id')
    try:
        costo = parse_nonnegative_decimal(request.form.get('costo'), 'Costo')
        precio = parse_nonnegative_decimal(request.form.get('precio'), 'Precio')
        stock_nuevo = parse_positive_int(request.form.get('stock'), 'Stock')
    except ValueError as error:
        flash(str(error), 'danger')
        return redirect(url_for('index'))
    if not nombre or not sku or not categoria_id:
        flash('Nombre, SKU y categoría son obligatorios.', 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute("SELECT * FROM productos WHERE sku = %s FOR UPDATE", (sku,))
        existente = cursor.fetchone()

        if existente:
            nuevo_stock = existente['stock'] + stock_nuevo
            cursor.execute(
                "UPDATE productos SET nombre=%s, stock=%s, costo=%s, precio=%s, categoria_id=%s WHERE id=%s",
                (nombre, nuevo_stock, costo, precio, categoria_id, existente['id'])
            )
            mensaje = f"Producto existente. Stock sumado (Total: {nuevo_stock})."
        else:
            cursor.execute(
                "INSERT INTO productos (nombre, sku, costo, precio, stock, categoria_id) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                (nombre, sku, costo, precio, stock_nuevo, categoria_id)
            )
            mensaje = "¡Producto registrado exitosamente!"
        conn.commit()
        flash(mensaje, "success")
    except mysql.connector.IntegrityError:
        conn.rollback()
        flash("No se pudo guardar el producto: revisa que el SKU y la categoría sean válidos.", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('index'))

# ---------- EDITAR PRODUCTO ----------
@app.route('/editar_producto', methods=['POST'])
def editar_producto():
    if 'usuario' not in session:
        return redirect(url_for('index'))

    try:
        precio = parse_nonnegative_decimal(request.form.get('precio'), 'Precio')
        costo = parse_nonnegative_decimal(request.form.get('costo'), 'Costo')
        stock = int(request.form.get('stock', ''))
        producto_id = parse_positive_int(request.form.get('producto_id'), 'Producto')
        if stock < 0:
            raise ValueError('Stock no puede ser negativo.')
    except ValueError as error:
        flash(str(error), 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE productos SET precio=%s, costo=%s, stock=%s WHERE id=%s",
        (precio, costo, stock, producto_id)
    )
    conn.commit()
    cursor.close()
    conn.close()
    flash("Producto actualizado correctamente.", "success")
    return redirect(url_for('index'))

# ---------- VENDER (ahora con cliente_id) ----------


@app.route('/vender_producto', methods=['POST'])
def vender_producto():
    if 'usuario' not in session:
        return redirect(url_for('index'))

    try:
        producto_id = parse_positive_int(request.form.get('producto_id'), 'Producto')
        cliente_id = parse_positive_int(request.form.get('cliente_id'), 'Cliente')
        cantidad = parse_positive_int(request.form.get('cantidad'), 'Cantidad')
    except ValueError as error:
        flash(str(error), 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute("SELECT * FROM productos WHERE id = %s FOR UPDATE", (producto_id,))
        prod = cursor.fetchone()
        cursor.execute("SELECT id_cliente FROM clientes WHERE id_cliente = %s", (cliente_id,))
        cliente = cursor.fetchone()

        if not prod or not cliente:
            conn.rollback()
            flash('Producto o cliente no encontrado.', 'danger')
            return redirect(url_for('index'))
        if prod['stock'] < cantidad:
            conn.rollback()
            flash(f"Stock insuficiente. Solo quedan {prod['stock']}.", 'danger')
            return redirect(url_for('index'))

        nuevo_stock = prod['stock'] - cantidad
        total_venta = Decimal(cantidad) * prod['precio']
        num_factura = f"FAC-{uuid.uuid4().hex[:8].upper()}"
        cursor.execute("UPDATE productos SET stock=%s WHERE id=%s", (nuevo_stock, producto_id))
        cursor.execute(
            "INSERT INTO ventas (cliente_id, producto_id, cantidad, precio_unitario, costo_unitario, total, usuario_id) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (cliente_id, producto_id, cantidad, prod['precio'], prod['costo'], total_venta, session['usuario_id'])
        )
        venta_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO historial_facturas (numero_factura, venta_id, cliente_id, subtotal, total) "
            "VALUES (%s, %s, %s, %s, %s)",
            (num_factura, venta_id, cliente_id, total_venta, total_venta)
        )
        conn.commit()
        flash(f"¡Venta exitosa! Factura {num_factura} generada.", "success")
        return redirect(url_for('ver_factura_pdf', venta_id=venta_id))
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


# --- NUEVA RUTA: GENERAR LA FACTURA EN PDF ---
@app.route('/factura/<int:venta_id>')
def ver_factura_pdf(venta_id):
    if 'usuario' not in session:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Buscar los datos de la venta, el cliente y el producto juntos
    cursor.execute("""
        SELECT v.id, v.cantidad, v.precio_unitario, v.total, v.fecha,
               c.nombre AS cliente_nombre, c.email AS cliente_email, c.direccion AS cliente_dir,
               p.nombre AS prod_nombre, p.sku,
               h.numero_factura
        FROM ventas v
        JOIN clientes c ON v.cliente_id = c.id_cliente
        JOIN productos p ON v.producto_id = p.id
        JOIN historial_facturas h ON h.venta_id = v.id
        WHERE v.id = %s
    """, (venta_id,))
    factura = cursor.fetchone()
    
    cursor.close()
    conn.close()

    if not factura:
        flash("Factura no encontrada.", "danger")
        return redirect(url_for('index'))

    # --- GENERAR PDF DE LA FACTURA ---
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elementos = []
    estilos = getSampleStyleSheet()

    # Encabezado
    elementos.append(Paragraph("<b>INVENTATECH</b>", ParagraphStyle('T', parent=estilos['Heading1'], fontSize=24, textColor=colors.HexColor('#4f7cff'))))
    elementos.append(Paragraph("Tienda Especializada en Repuestos y Hardware de Tecnología", estilos['Normal']))
    elementos.append(Spacer(1, 20))
    
    # Datos de la factura
    elementos.append(Paragraph(f"<b>Factura N°:</b> {factura['numero_factura']}", estilos['Normal']))
    elementos.append(Paragraph(f"<b>Fecha:</b> {factura['fecha'].strftime('%Y-%m-%d %H:%M')}", estilos['Normal']))
    elementos.append(Spacer(1, 15))
    
    elementos.append(Paragraph("<b>Datos del Cliente:</b>", estilos['Heading3']))
    elementos.append(Paragraph(f"Nombre: {factura['cliente_nombre']}", estilos['Normal']))
    elementos.append(Paragraph(f"Email: {factura['cliente_email'] or 'N/A'}", estilos['Normal']))
    elementos.append(Paragraph(f"Dirección: {factura['cliente_dir'] or 'N/A'}", estilos['Normal']))
    elementos.append(Spacer(1, 25))

    # Tabla de Productos
    data_tabla = [
        ['Producto', 'SKU', 'Cantidad', 'Precio Unit.', 'Total'],
        [factura['prod_nombre'], factura['sku'], str(factura['cantidad']), f"${factura['precio_unitario']:,.0f}", f"${factura['total']:,.0f}"]
    ]
    tabla = Table(data_tabla, colWidths=[200, 80, 70, 80, 90])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4f7cff')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('ALIGN', (0,1), (0,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1'))
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 20))

    # Total Final
    elementos.append(Paragraph(f"<b>Total a Pagar:</b> ${factura['total']:,.0f} COP", ParagraphStyle('Total', parent=estilos['Heading2'], alignment=2, textColor=colors.HexColor('#2ee6c5'))))

    doc.build(elementos)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{factura['numero_factura']}.pdf", mimetype='application/pdf')

# ---------- ELIMINAR PRODUCTO ----------
@app.route('/eliminar/<int:id>')
def eliminar_producto(id):
    if 'usuario' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM productos WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index'))

# ============================================================
# MÓDULO 1: GESTIÓN DE CLIENTES
# ============================================================
@app.route('/clientes')
def clientes():
    if 'usuario' not in session:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM clientes ORDER BY id_cliente DESC")
    lista_clientes = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('clientes.html', clientes=lista_clientes)


@app.route('/clientes/agregar', methods=['POST'])
def agregar_cliente():
    if 'usuario' not in session:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO clientes (nombre, email, telefono, direccion, ciudad, pais)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (
        request.form['nombre'],
        request.form['email'],
        request.form['telefono'],
        request.form['direccion'],
        request.form['ciudad'],
        request.form['pais']
    ))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Cliente registrado exitosamente.", "success")
    return redirect(url_for('clientes'))


@app.route('/clientes/editar/<int:id>', methods=['POST'])
def editar_cliente(id):
    if 'usuario' not in session:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE clientes 
        SET nombre=%s, email=%s, telefono=%s, direccion=%s, ciudad=%s, pais=%s
        WHERE id_cliente=%s
    """, (
        request.form['nombre'],
        request.form['email'],
        request.form['telefono'],
        request.form['direccion'],
        request.form['ciudad'],
        request.form['pais'],
        id
    ))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Cliente actualizado.", "success")
    return redirect(url_for('clientes'))


@app.route('/clientes/eliminar/<int:id>')
def eliminar_cliente(id):
    if 'usuario' not in session:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM clientes WHERE id_cliente = %s", (id,))
        conn.commit()
        flash("Cliente eliminado.", "success")
    except mysql.connector.IntegrityError:
        flash("No se puede eliminar: el cliente tiene ventas registradas.", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('clientes'))


# --- Reporte PDF: clasificación por nacionalidad ---
@app.route('/clientes/reporte-pdf')
def clientes_reporte_pdf():
    if 'usuario' not in session:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Agrupación por país
    cursor.execute("""
        SELECT pais, COUNT(*) AS total
        FROM clientes
        GROUP BY pais
        ORDER BY total DESC
    """)
    por_pais = cursor.fetchall()

    # Detalle por país
    cursor.execute("SELECT nombre, email, telefono, ciudad, pais FROM clientes ORDER BY pais, nombre")
    detalle = cursor.fetchall()

    cursor.close()
    conn.close()

    # --- Generar PDF ---
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=40, leftMargin=40,
                            topMargin=40, bottomMargin=40)
    elementos = []
    estilos = getSampleStyleSheet()

    titulo = ParagraphStyle('T', parent=estilos['Heading1'], fontSize=18,
                            textColor=colors.HexColor('#0f172a'), spaceAfter=4)
    sub = ParagraphStyle('S', parent=estilos['Normal'], fontSize=10,
                         textColor=colors.HexColor('#64748b'), spaceAfter=15)
    seccion = ParagraphStyle('Sec', parent=estilos['Heading2'], fontSize=13,
                             textColor=colors.HexColor('#1e293b'),
                             spaceBefore=12, spaceAfter=8)
    th = ParagraphStyle('TH', parent=estilos['Normal'], fontSize=9,
                        textColor=colors.whitesmoke, fontName='Helvetica-Bold')
    td = ParagraphStyle('TD', parent=estilos['Normal'], fontSize=9,
                        textColor=colors.HexColor('#334155'),
                        fontName='Helvetica', leading=11)

    elementos.append(Paragraph("<b>InventaTech — Reporte de Clientes por Nacionalidad</b>", titulo))
    elementos.append(Paragraph("Clasificación de la base de clientes según su país de origen.", sub))

    # Tabla resumen
    elementos.append(Paragraph("<b>1. Resumen por País</b>", seccion))
    total_clientes = sum(r['total'] for r in por_pais)
    filas = [[Paragraph('País', th),
              Paragraph('Cantidad de Clientes', th),
              Paragraph('% del Total', th)]]
    for r in por_pais:
        pct = (r['total'] / total_clientes * 100) if total_clientes else 0
        filas.append([
            Paragraph(str(r['pais']), td),
            Paragraph(str(r['total']), td),
            Paragraph(f"{pct:.1f}%", td)
        ])
    filas.append([Paragraph('<b>TOTAL</b>', td),
                  Paragraph(f'<b>{total_clientes}</b>', td),
                  Paragraph('<b>100%</b>', td)])

    tabla = Table(filas, colWidths=[220, 180, 130])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1),
         [colors.HexColor('#ffffff'), colors.HexColor('#f1f5f9')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 12))

    # Tabla detalle
    elementos.append(Paragraph("<b>2. Detalle de Clientes</b>", seccion))
    filas2 = [[Paragraph('Nombre', th), Paragraph('Email', th),
               Paragraph('Teléfono', th), Paragraph('Ciudad', th),
               Paragraph('País', th)]]
    for d in detalle:
        filas2.append([
            Paragraph(d['nombre'] or '', td),
            Paragraph(d['email'] or '', td),
            Paragraph(d['telefono'] or '', td),
            Paragraph(d['ciudad'] or '', td),
            Paragraph(d['pais'] or '', td),
        ])
    tabla2 = Table(filas2, colWidths=[110, 130, 80, 90, 90])
    tabla2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1),
         [colors.HexColor('#ffffff'), colors.HexColor('#f1f5f9')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    elementos.append(tabla2)

    doc.build(elementos)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True,
                     download_name="Reporte_Clientes_Por_Pais.pdf",
                     mimetype='application/pdf')

# ============================================================
# MÓDULO 3: GESTIÓN DE USUARIOS (Solo Administrador)
# ============================================================
@app.route('/usuarios')
def usuarios():
    # Control de acceso
    if 'usuario' not in session or session.get('rol') != 'administrador':
        flash("Acceso denegado. Solo administradores.", "danger")
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id_usuario, nombre_usuario, email, rol, estado FROM usuarios ORDER BY id_usuario DESC")
    lista_usuarios = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('usuarios.html', usuarios=lista_usuarios)

@app.route('/usuarios/agregar', methods=['POST'])
def agregar_usuario():
    if 'usuario' not in session or session.get('rol') != 'administrador':
        return redirect(url_for('index'))

    nombre = request.form['nombre_usuario']
    email = request.form['email']
    contrasena = request.form['contrasena']
    rol = request.form['rol']
    estado = request.form['estado']

    # Ciframos la contraseña (Requisito del PDF)
    hash_pass = generate_password_hash(contrasena)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO usuarios (nombre_usuario, email, contrasena, rol, estado)
            VALUES (%s, %s, %s, %s, %s)
        """, (nombre, email, hash_pass, rol, estado))
        conn.commit()
        flash("Usuario registrado exitosamente.", "success")
    except mysql.connector.IntegrityError:
        flash("Error: El nombre de usuario o el email ya están en uso.", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('usuarios'))

@app.route('/usuarios/editar/<int:id>', methods=['POST'])
def editar_usuario(id):
    if 'usuario' not in session or session.get('rol') != 'administrador':
        return redirect(url_for('index'))

    nombre = request.form['nombre_usuario']
    email = request.form['email']
    rol = request.form['rol']
    estado = request.form['estado']
    contrasena = request.form.get('contrasena') # Puede venir vacía

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if contrasena: # Si el admin escribió una nueva contraseña, la actualizamos
            hash_pass = generate_password_hash(contrasena)
            cursor.execute("""
                UPDATE usuarios SET nombre_usuario=%s, email=%s, contrasena=%s, rol=%s, estado=%s WHERE id_usuario=%s
            """, (nombre, email, hash_pass, rol, estado, id))
        else: # Si la dejó en blanco, mantenemos la anterior
            cursor.execute("""
                UPDATE usuarios SET nombre_usuario=%s, email=%s, rol=%s, estado=%s WHERE id_usuario=%s
            """, (nombre, email, rol, estado, id))
        conn.commit()
        flash("Usuario actualizado correctamente.", "success")
    except mysql.connector.IntegrityError:
        flash("Error: El nombre de usuario o el email ya están en uso.", "danger")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('usuarios'))

@app.route('/usuarios/eliminar/<int:id>')
def eliminar_usuario(id):
    if 'usuario' not in session or session.get('rol') != 'administrador':
        return redirect(url_for('index'))

    # Evitar que el admin se elimine a sí mismo
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT nombre_usuario FROM usuarios WHERE id_usuario = %s", (id,))
    user = cursor.fetchone()
    
    if user and user['nombre_usuario'] == session['usuario']:
        flash("No puedes eliminar tu propio usuario mientras estás en sesión.", "danger")
    else:
        cursor.execute("DELETE FROM usuarios WHERE id_usuario = %s", (id,))
        conn.commit()
        flash("Usuario eliminado.", "success")
        
    cursor.close()
    conn.close()
    return redirect(url_for('usuarios'))

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(
        host=os.getenv('FLASK_HOST', '0.0.0.0'),
        port=int(os.getenv('FLASK_PORT', '5000')),
        debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
    )