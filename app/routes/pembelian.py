from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from flask import send_file
import psycopg2.extras
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from app.models.db import get_db
from datetime import datetime
from flask import flash
import io

bp = Blueprint('pembelian', __name__, url_prefix='/pembelian')

@bp.route('/list')
def index():
    start = request.args.get('start')
    end = request.args.get('end')

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT menu_id, nama FROM menu ORDER BY nama")
    menu_list = cur.fetchall()

    cur.execute("SELECT vendor_id, nama FROM vendor ORDER BY nama")
    vendor_list = cur.fetchall()

    query = """
        SELECT p.beli_id, p.tanggal, u.nama AS kasir, v.nama AS vendor, p.total, p.keterangan
        FROM pembelian p
        JOIN pengguna u ON p.user_id = u.user_id
        JOIN vendor v ON p.vendor_id = v.vendor_id
        WHERE 1=1
    """
    params = []

    if start:
        query += " AND p.tanggal >= %s"
        params.append(start)

    if end:
        query += " AND p.tanggal <= %s"
        params.append(end + " 23:59:59")

    query += " ORDER BY p.tanggal DESC"

    cur.execute(query, params)
    riwayat_pembelian = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('pembelian/pembelian.html',
        menu_list=menu_list,
        vendor_list=vendor_list,
        riwayat_pembelian=riwayat_pembelian,
        start=start,
        end=end
    )


@bp.route('/tambah', methods=['POST'])
def tambah_pembelian():
    conn = get_db()
    cur = conn.cursor()

    user_id = session.get('user', {}).get('user_id')
    vendor_id = request.form['vendor_id']
    keterangan = request.form.get('keterangan', '')

    menu_ids = request.form.getlist('menu_id[]')
    qtys = request.form.getlist('qty[]')
    harga_belis = request.form.getlist('harga_beli[]')

    total = 0
    details = []

    for i in range(len(menu_ids)):
        menu_id = menu_ids[i]
        qty = int(qtys[i])
        harga_beli = float(harga_belis[i])
        subtotal = qty * harga_beli
        total += subtotal
        details.append((menu_id, qty, harga_beli))

    # Insert pembelian
    cur.execute("SELECT beli_id FROM pembelian ORDER BY beli_id DESC LIMIT 1")
    last_beli = cur.fetchone()
    if last_beli:
        next_beli_num = int(last_beli[0][3:]) + 1
    else:
        next_beli_num = 1
    beli_id = f"INV{str(next_beli_num).zfill(4)}"

    cur.execute("""
        INSERT INTO pembelian (beli_id, user_id, vendor_id, total, keterangan, status)
        VALUES (%s, %s, %s, %s, %s, 'pending')
    """, (beli_id, user_id, vendor_id, total, keterangan))

    # Insert detail pembelian
    cur.execute("SELECT detail_beli_id FROM detail_pembelian ORDER BY detail_beli_id DESC LIMIT 1")
    last_detail = cur.fetchone()
    if last_detail:
        next_detail_num = int(last_detail[0][2:]) + 1
    else:
        next_detail_num = 1
    
    for menu_id, qty, harga_beli in details:
        detail_beli_id = f"DP{str(next_detail_num).zfill(5)}"
        next_detail_num += 1
        cur.execute("""
            INSERT INTO detail_pembelian (detail_beli_id, beli_id, menu_id, qty, harga_beli)
            VALUES (%s, %s, %s, %s, %s)
        """, (detail_beli_id, beli_id, menu_id, qty, harga_beli))


    conn.commit()
    cur.close()
    conn.close()

    flash(beli_id)
    return redirect(url_for('pembelian.index'))


@bp.route('/detail-json/<beli_id>')
def detail_json(beli_id):
    conn = get_db()
    cur = conn.cursor()

    # Ambil status pembelian
    cur.execute("SELECT status FROM pembelian WHERE beli_id = %s", (beli_id,))
    status_result = cur.fetchone()
    status = status_result[0] if status_result else 'unknown'

    # Ambil detail item
    cur.execute("""
        SELECT m.nama, dp.qty, dp.harga_beli, (dp.qty * dp.harga_beli) AS subtotal
        FROM detail_pembelian dp
        JOIN menu m ON dp.menu_id = m.menu_id
        WHERE dp.beli_id = %s
    """, (beli_id,))
    items = [
        {
            'nama': row[0],
            'qty': row[1],
            'harga_beli': float(row[2]),
            'subtotal': float(row[3])
        }
        for row in cur.fetchall()
    ]

    cur.close()
    conn.close()

    return jsonify({
        'status': status,
        'items': items
    })

@bp.route('/hapus/<beli_id>', methods=['POST'])
def hapus(beli_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM detail_pembelian WHERE beli_id = %s", (beli_id,))
    cur.execute("DELETE FROM pembelian WHERE beli_id = %s", (beli_id,))

    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('pembelian.index'))

@bp.route('/nota/<beli_id>')
def cetak_invoice(beli_id):
    conn = get_db()
    cur = conn.cursor()

    # Ambil data utama pembelian
    cur.execute("""
        SELECT p.tanggal, p.total, u.nama AS kasir, v.nama AS vendor, p.keterangan
        FROM pembelian p
        JOIN pengguna u ON p.user_id = u.user_id
        JOIN vendor v ON p.vendor_id = v.vendor_id
        WHERE p.beli_id = %s
    """, (beli_id,))
    result = cur.fetchone()
    if not result:
        return "Pembelian tidak ditemukan", 404

    tanggal, total, kasir, vendor, keterangan = result
    keterangan = "-" if not keterangan else keterangan

    # Ambil detail item pembelian
    cur.execute("""
        SELECT m.nama, dp.qty, dp.harga_beli
        FROM detail_pembelian dp
        JOIN menu m ON dp.menu_id = m.menu_id
        WHERE dp.beli_id = %s
    """, (beli_id,))
    items = cur.fetchall()

    cur.close()
    conn.close()

    # Siapkan PDF
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(width / 2, y, "Invoice Pembelian - Relax Cafe")
    y -= 30

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, f"{beli_id}")
    y -= 18
    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, y, f"Tanggal")
    pdf.drawString(120, y, f": {tanggal.strftime('%Y-%m-%d %H:%M')}")
    y -= 18
    pdf.drawString(50, y, f"Vendor")
    pdf.drawString(120, y, f": {vendor}")
    y -= 18
    pdf.drawString(50, y, f"Kasir")
    pdf.drawString(120, y, f": {kasir}")
    y -= 18
    pdf.drawString(50, y, f"Keterangan")
    pdf.drawString(120, y, f": {keterangan}")
    y -= 40

    # Header tabel
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Menu")
    pdf.drawString(250, y, "Qty")
    pdf.drawString(300, y, "Harga")
    pdf.drawString(400, y, "Subtotal")
    y -= 15
    pdf.line(50, y, 500, y)
    y -= 15

    # Tabel item
    pdf.setFont("Helvetica", 10)
    for nama, qty, harga in items:
        subtotal = qty * harga
        if y < 100:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = height - 50
        pdf.drawString(50, y, nama)
        pdf.drawString(250, y, str(qty))
        pdf.drawString(300, y, f"Rp{int(harga):,}".replace(",", "."))
        pdf.drawString(400, y, f"Rp{int(subtotal):,}".replace(",", "."))
        y -= 18

    pdf.setFont("Helvetica-Bold", 11)
    pdf.line(50, y, 500, y)
    y -= 20
    pdf.drawString(300, y, "Total:")
    pdf.drawString(400, y, f"Rp{int(total):,}".replace(",", "."))

    # Footer
    y -= 50
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(width / 2, y, "Relax Cafe")

    pdf.setTitle(f"Invoice Pembelian {beli_id}")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=False,
        download_name=f'invoice_{beli_id}.pdf',
        mimetype='application/pdf'
    )

@bp.route('/laporan')
def laporan_pembelian_pdf():
    start = request.args.get('start')
    end = request.args.get('end')

    if not start or not end:
        return "Tanggal harus diisi", 400

    conn = get_db()
    cur = conn.cursor()

    # Ambil data pembelian yang accepted saja
    query = """
        SELECT p.beli_id, p.tanggal, v.nama AS vendor, p.total
        FROM pembelian p
        JOIN vendor v ON p.vendor_id = v.vendor_id
        WHERE DATE(p.tanggal) BETWEEN %s AND %s
        AND p.status = 'accepted'
        ORDER BY p.tanggal DESC
    """
    cur.execute(query, [start, end])
    pembelian_data = cur.fetchall()

    # Ambil semua detail pembelian
    detail_query = """
        SELECT d.beli_id, m.nama, d.qty, d.harga_beli, d.subtotal
        FROM detail_pembelian d
        JOIN menu m ON d.menu_id = m.menu_id
        WHERE d.beli_id IN (
            SELECT beli_id FROM pembelian
            WHERE DATE(tanggal) BETWEEN %s AND %s
            AND status = 'accepted'
        )
        ORDER BY d.beli_id
    """
    cur.execute(detail_query, [start, end])
    detail_data = cur.fetchall()

    cur.close()
    conn.close()

    # Gabungkan detail berdasarkan beli_id
    from collections import defaultdict
    grouped_detail = defaultdict(list)
    for d in detail_data:
        beli_id, nama_menu, qty, harga_beli, subtotal = d
        grouped_detail[beli_id].append({
            'menu': nama_menu,
            'qty': qty,
            'harga': harga_beli,
            'subtotal': subtotal
        })

    # PDF
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    pdf.setFont("Helvetica-Bold", 14)
    y = height - 40

    pdf.drawCentredString(width / 2, y, "Laporan Pembelian")
    y -= 25
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, y, "Periode:")
    y -= 20
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, f"{start}  s.d.  {end}")
    y -= 30

    total_semua = 0
    pdf.setFont("Helvetica", 10)

    for p in pembelian_data:
        beli_id, tanggal, vendor, total = p
        if y < 120:
            pdf.showPage()
            y = height - 50
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawCentredString(width / 2, y, "Laporan Pembelian")
            y -= 30
            pdf.setFont("Helvetica", 10)

        pdf.setFont("Helvetica-Bold", 10)
        y -= 10
        pdf.drawString(50, y, f"Tanggal: {tanggal.strftime('%Y-%m-%d')}")
        y -= 15
        pdf.drawString(50, y, f"Vendor: {vendor}")
        y -= 15
        pdf.drawString(50, y, f"ID: {beli_id}")
        y -= 25

        pdf.setFont("Helvetica", 10)
        pdf.drawString(60, y, "Menu")
        pdf.drawString(220, y, "Qty")
        pdf.drawString(280, y, "Harga Beli")
        pdf.drawString(380, y, "Subtotal")
        y -= 10
        pdf.line(50, y, 550, y)
        y -= 15

        for item in grouped_detail.get(beli_id, []):
            pdf.drawString(60, y, item['menu'][:30])
            pdf.drawString(220, y, str(item['qty']))
            pdf.drawString(280, y, f"{int(item['harga']):,}".replace(",", "."))
            pdf.drawString(380, y, f"{int(item['subtotal']):,}".replace(",", "."))
            y -= 15
            if y < 80:
                pdf.showPage()
                y = height - 50
                pdf.setFont("Helvetica", 10)

        pdf.setFont("Helvetica-Bold", 10)
        y-= 10
        pdf.drawString(390, y, f"Total:")
        pdf.drawRightString(500, y, f"Rp. {int(total):,}".replace(",", "."))
        total_semua += float(total)
        y -= 25

    # Footer Total
    pdf.setFont("Helvetica-Bold", 11)
    y -= 40
    pdf.drawRightString(380, y, "Total Semua:")
    pdf.drawRightString(500, y, f"Rp. {int(total_semua):,}".replace(",", "."))

    pdf.setTitle("Laporan Pembelian")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=False,
        download_name=f'laporan_pembelian_{start}_sd_{end}.pdf',
        mimetype='application/pdf'
    )
