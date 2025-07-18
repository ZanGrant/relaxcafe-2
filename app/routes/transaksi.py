from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from flask import make_response, send_file
import psycopg2.extras
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from app.models.db import get_db
from datetime import datetime
import random, string
import io
import os

bp = Blueprint('transaksi', __name__, url_prefix='/transaksi')

@bp.route('/kasir')
def index():
    if 'user' not in session:
        return redirect(url_for('dashboard.login'))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT kategori FROM menu GROUP BY kategori ORDER BY kategori")
    kategori_list = [row['kategori'] for row in cur.fetchall()]

    menu_kategori = {}
    for kategori in kategori_list:
        cur.execute("SELECT menu_id, nama, harga, stok, image_path FROM menu WHERE kategori = %s ORDER BY nama", (kategori,))
        items = [
            {
                'menu_id': row['menu_id'],
                'nama': row['nama'],
                'harga': row['harga'],
                'stok': row['stok'],
                'image_path': row['image_path'] if row['image_path'] else ''       
            }
            for row in cur.fetchall()
        ]
        menu_kategori[kategori] = items

    cur.close()
    conn.close()
    return render_template('transaksi/transaksi.html', menu_kategori=menu_kategori)

@bp.route('/arsip')
def arsip():
    if 'user' not in session:
        return redirect(url_for('dashboard.login'))

    user = session['user']
    role = user.get('role')
    user_id = user.get('user_id')

    cur = get_db().cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Filter logic (start, end, kasir)
    start = request.args.get("start")
    end = request.args.get("end")
    kasir = request.args.get("kasir") if role in ['manajemen', 'admin'] else user_id

    query = """
        SELECT t.transaksi_id, t.tanggal, k.nama, t.nama_pelanggan, t.total
        FROM transaksi t
        JOIN pengguna k ON t.user_id = k.user_id
        WHERE 1=1
    """
    params = []
    if start:
        query += " AND t.tanggal >= %s"
        params.append(start)
    if end:
        query += " AND t.tanggal <= %s"
        params.append(end + " 23:59:59")
    if kasir:
        query += " AND k.user_id = %s"
        params.append(kasir)
    query += " ORDER BY t.tanggal DESC"
    cur.execute(query, params)
    
    transaksi_list = cur.fetchall()
    kasir_list = []
    cur.execute("""
        SELECT DISTINCT p.user_id, p.nama
        FROM transaksi t
        JOIN pengguna p ON t.user_id = p.user_id
        ORDER BY p.nama
    """)
    kasir_list = cur.fetchall()

    asal = request.args.get('from')
    if asal == 'dashboard':
        back_url = url_for('dashboard.main')

    return render_template('transaksi/transaksi_arsip.html', transaksi=transaksi_list, kasir_list=kasir_list)

@bp.route('/detail-json/<transaksi_id>')
def detail_transaksi_json(transaksi_id):
    cur = get_db().cursor()
    cur.execute("""
        SELECT m.nama, d.qty, d.harga_satuan, d.subtotal
        FROM detail_transaksi d
        JOIN menu m ON d.menu_id = m.menu_id
        WHERE d.transaksi_id = %s
    """, (transaksi_id,))
    data = [
        {'nama': r[0], 'qty': r[1], 'harga': float(r[2]), 'subtotal': float(r[3])}
        for r in cur.fetchall()
    ]
    return jsonify(data)

@bp.route('/hapus/<transaksi_id>', methods=['POST'])
def hapus_transaksi(transaksi_id):
    conn = get_db()
    cur = conn.cursor()
    # Hapus detail dulu karena masalah constraint
    cur.execute("DELETE FROM detail_transaksi WHERE transaksi_id = %s", (transaksi_id,))
    cur.execute("DELETE FROM transaksi WHERE transaksi_id = %s", (transaksi_id,))
    conn.commit()
    return redirect(url_for('transaksi.arsip'))


@bp.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    menu_id = request.form.get('menu_id')
    qty = int(request.form.get('qty', 1))

    if not menu_id or qty <= 0:
        return jsonify({'success': False, 'message': 'Permintaan tidak valid'})

    menu = get_menu_by_id(menu_id)
    if not menu:
        return jsonify({'success': False, 'message': 'Menu tidak ditemukan'})

    cart = session.get('cart', {})
    existing_qty = cart.get(menu_id, 0)

    if existing_qty + qty > menu['stok']:
        sisa = menu["stok"] - existing_qty
        return jsonify({'success': False, 'message': f'Stok tidak cukup. Tersisa {sisa} lagi'})

    cart[menu_id] = existing_qty + qty
    session['cart'] = cart
    return jsonify({'success': True})

def get_menu_by_id(menu_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT menu_id, nama, harga, stok FROM menu WHERE menu_id = %s", (menu_id,))
    row = cur.fetchone()
    if row:
        return {'menu_id': row[0], 'nama': row[1], 'harga': row[2], 'stok': row[3]}
    return None

@bp.route('/get-cart')
def get_cart():
    cart = session.get('cart', {})
    result = []
    for menu_id, qty in cart.items():
        menu = get_menu_by_id(menu_id)
        if menu:
            result.append({
                'id': menu_id,
                'name': menu['nama'],
                'price': menu['harga'],
                'qty': qty
            })
    return jsonify(result)

@bp.route('/clear-cart')
def clear_cart():
    session.pop('cart', None)
    return jsonify({'success': True})


@bp.route('/checkout', methods=['POST'])
def checkout():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Belum login'})

    cart = session.get('cart', {})
    if not cart:
        return jsonify({'success': False})

    conn = get_db()
    cur = conn.cursor()

    try:
        # Hitung total dan cek stok lagi
        total = 0
        for menu_id, qty in cart.items():
            cur.execute("SELECT harga, stok FROM menu WHERE menu_id = %s", (menu_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({'success': False, 'message': 'Menu tidak ditemukan'})
            harga, stok = row
            if qty > stok:
                return jsonify({'success': False, 'message': f'Stok tidak cukup untuk menu {menu_id}'})
            total += harga * qty

        transaksi_id = generate_sequence_id('T', 'transaksi', 'transaksi_id')
        user_id = session['user']['user_id']
        nama_pelanggan = request.form.get("nama_pelanggan", "")
        bayar = float(request.form.get("bayar", 0))

        cur.execute("""
            INSERT INTO transaksi (transaksi_id, user_id, total, nama_pelanggan, bayar)
            VALUES (%s, %s, %s, %s, %s)
        """, (transaksi_id, user_id, total, nama_pelanggan, bayar))

        for menu_id, qty in cart.items():
            cur.execute("SELECT harga FROM menu WHERE menu_id = %s", (menu_id,))
            harga = cur.fetchone()[0]
            detail_transaksi_id = generate_sequence_id('D', 'detail_transaksi', 'detail_transaksi_id')
            cur.execute("""
                INSERT INTO detail_transaksi (detail_transaksi_id, transaksi_id, menu_id, qty, harga_satuan)
                VALUES (%s, %s, %s, %s, %s)
            """, (detail_transaksi_id, transaksi_id, menu_id, qty, harga))

            # Update stok
            cur.execute("UPDATE menu SET stok = stok - %s WHERE menu_id = %s", (qty, menu_id))

        conn.commit()
        session.pop('cart', None)
        return jsonify({'success': True, 'nota_url': url_for('transaksi.cetak_nota', transaksi_id=transaksi_id)})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': 'Terjadi kesalahan: ' + str(e)})

    finally:
        cur.close()
        conn.close()

def generate_sequence_id(prefix, table, column):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT MAX(RIGHT({column}, 4)) FROM {table}
        WHERE {column} LIKE %s
    """, (f"{prefix}%",))
    last_number = cur.fetchone()[0]
    if last_number and last_number.isdigit():
        next_number = int(last_number) + 1
    else:
        next_number = 1
    return f"{prefix}{next_number:04d}"


@bp.route('/nota/<transaksi_id>')
def cetak_nota(transaksi_id):
    conn = get_db()
    cur = conn.cursor()

    # Ambil data transaksi
    cur.execute("""
        SELECT t.tanggal, t.total, t.nama_pelanggan, t.bayar, t.kembalian, k.nama 
        FROM transaksi t
        JOIN pengguna k ON t.user_id = k.user_id
        WHERE t.transaksi_id = %s
    """, (transaksi_id,))
    trx = cur.fetchone()
    if not trx:
        return "Transaksi tidak ditemukan", 404

    tanggal, total, nama_pelanggan, bayar, kembalian, kasir = trx
    nama_pelanggan = "-" if not nama_pelanggan else nama_pelanggan

    # Ambil detail transaksi
    cur.execute("""
        SELECT m.nama, d.qty, d.harga_satuan
        FROM detail_transaksi d
        JOIN menu m ON d.menu_id = m.menu_id
        WHERE d.transaksi_id = %s
    """, (transaksi_id,))
    items = cur.fetchall()

    # Generate PDF
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    pdf.setFont("Helvetica", 12)

    y = height - 50

    # Header
    pdf.drawCentredString(width / 2, y, "Struk Pembayaran")
    y -= 30
    # Info Transaksi
    pdf.drawString(50, y, f"ID Transaksi: {transaksi_id}")
    y -= 20
    pdf.drawString(50, y, f"Tanggal: {tanggal.strftime('%Y-%m-%d %H:%M')}")
    y -= 20
    pdf.drawString(50, y, f"Kasir: {kasir}")
    y -= 20
    pdf.drawString(50, y, f"Pelanggan: {nama_pelanggan}")
    y -= 30
    # Table Header
    pdf.drawString(50, y, "Menu")
    pdf.drawString(250, y, "Qty")
    pdf.drawString(300, y, "Harga")
    pdf.drawString(400, y, "Subtotal")
    y -= 15
    pdf.line(50, y, 500, y)
    y -= 15
    # Isi item
    for nama, qty, harga in items:
        subtotal = qty * harga
        pdf.drawString(50, y, str(nama))
        pdf.drawString(250, y, str(qty))
        pdf.drawString(300, y, f"Rp{int(harga):,}".replace(",", "."))
        pdf.drawString(400, y, f"Rp{int(subtotal):,}".replace(",", "."))
        y -= 20

    pdf.line(50, y, 500, y)
    y -= 20
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(300, y, "Total:")
    pdf.drawString(400, y, f"Rp{int(total):,}".replace(",", "."))
    y -= 20
    pdf.setFont("Helvetica", 12)
    pdf.drawString(300, y, "Bayar:")
    pdf.drawString(400, y, f"Rp{int(bayar):,}".replace(",", "."))
    y -= 20
    pdf.drawString(300, y, "Kembalian:")
    pdf.drawString(400, y, f"Rp{int(kembalian):,}".replace(",", "."))
    # Footer ucapan
    y -= 50
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(width / 2, y, "Terima kasih sudah berbelanja di")
    y -= 20
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(width / 2, y, "Relax Cafe")


    pdf.setTitle("Struk Relax Cafe")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=False,
        download_name=f'nota_{transaksi_id}.pdf',
        mimetype='application/pdf'
    )


@bp.route('/laporan')
def laporan_transaksi_pdf():
    start = request.args.get('start')
    end = request.args.get('end')
    kasir_filter = request.args.get('kasir')

    if not start or not end:
        return "Tanggal harus diisi", 400

    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT t.tanggal, t.transaksi_id, t.nama_pelanggan, t.total, u.nama
        FROM transaksi t
        JOIN pengguna u ON t.user_id = u.user_id
        WHERE DATE(t.tanggal) BETWEEN %s AND %s
    """
    params = [start, end]

    if kasir_filter:
        query += " AND u.user_id = %s"
        params.append(kasir_filter)

    query += " ORDER BY t.tanggal DESC"
    cur.execute(query, params)
    transaksi = cur.fetchall()

    # Start generate PDF
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    pdf.setFont("Helvetica-Bold", 14)
    y = height - 40

    pdf.drawCentredString(width / 2, y, "Laporan Transaksi")
    y -= 25
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, y, "Periode:")
    y -= 20
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, f"{start}  s.d.  {end}")
    y -= 30
    pdf.setFont("Helvetica", 12)


    # Table Header
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(50, y, "Tanggal")
    pdf.drawString(120, y, "Kasir")
    pdf.drawString(250, y, "Pelanggan")
    pdf.drawRightString(500, y, "Total (Rp)")
    y -= 15
    pdf.line(50, y, 550, y)
    y -= 15

    # Isi tabel
    pdf.setFont("Helvetica", 10)
    total_semua = 0
    for trx in transaksi:
        tanggal, trx_id, nama_pelanggan, total, kasir = trx
        nama_pelanggan = nama_pelanggan or "-"
        
        if y < 80:  # break page
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(50, y, "Tanggal")
            pdf.drawString(120, y, "Kasir")
            pdf.drawString(250, y, "Pelanggan")
            pdf.drawString(400, y, "Total")
            y -= 15
            pdf.line(50, y, 550, y)
            y -= 15
            pdf.setFont("Helvetica", 10)

        pdf.drawString(50, y, tanggal.strftime('%Y-%m-%d'))
        pdf.drawString(120, y, kasir[:20])
        pdf.drawString(250, y, nama_pelanggan[:25])
        pdf.drawRightString(500, y, f"{int(total):,}".replace(",", "."))
        total_semua += total
        y -= 18


    # Footer Total
    pdf.setFont("Helvetica-Bold", 11)
    pdf.line(50, y, 550, y)
    y -= 20
    pdf.drawRightString(400, y, "Total Semua:")
    pdf.drawRightString(500, y, f"Rp. {int(total_semua):,}".replace(",", "."))


    pdf.setTitle("Laporan Transaksi")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=False,
        download_name=f'laporan_transaksi_{start}_sd_{end}.pdf',
        mimetype='application/pdf'
    )