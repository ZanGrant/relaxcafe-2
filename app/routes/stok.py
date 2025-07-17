from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from flask import make_response, send_file
import psycopg2.extras
from datetime import datetime
from app.models.db import get_db
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

bp = Blueprint('stok', __name__, url_prefix='/stok')

@bp.route('/list')
def index():
    start = request.args.get('start')
    end = request.args.get('end')
    selected_menu_id = request.args.get('selected_menu_id', None)

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = """
        SELECT sm.tanggal, m.nama, sm.jumlah, sm.keterangan, sm.beli_id
        FROM stok_masuk sm
        JOIN menu m ON sm.menu_id = m.menu_id
        WHERE 1=1
    """
    params = []
    if start:
        query += " AND sm.tanggal >= %s"
        params.append(start)
    if end:
        query += " AND sm.tanggal <= %s"
        params.append(end + " 23:59:59")
    query += " ORDER BY sm.tanggal DESC"

    cur.execute(query, params)
    riwayat_stok = cur.fetchall()

    cur.execute("SELECT menu_id, nama, stok FROM menu ORDER BY nama")
    menu_list = cur.fetchall()

    cur.execute("""
        SELECT DISTINCT p.beli_id, p.tanggal, v.nama AS vendor_nama, dp.menu_id
        FROM pembelian p
        JOIN vendor v ON p.vendor_id = v.vendor_id
        JOIN detail_pembelian dp ON dp.beli_id = p.beli_id
        WHERE p.status = 'accepted'::status_enum
        ORDER BY p.tanggal DESC
    """)
    all_pembelian = cur.fetchall()

    from collections import defaultdict
    pembelian_by_menu = defaultdict(list)
    for beli in all_pembelian:
        pembelian_by_menu[beli['menu_id']].append({
            'beli_id': beli['beli_id'],
            'tanggal': beli['tanggal'],
            'vendor_nama': beli['vendor_nama']
        })


    cur.close()
    conn.close()

    return render_template('menu/stok.html',
        menu_list=menu_list,
        riwayat_stok=riwayat_stok,
        start=start,
        end=end,
        pembelian_by_menu=pembelian_by_menu,
        selected_menu_id=selected_menu_id # Dari halaman menu
    )

@bp.route('/tambah', methods=['POST'])
def tambah_stok():
    menu_id = request.form['menu_id']
    jumlah = int(request.form['jumlah'])
    keterangan = request.form.get('keterangan', '')
    timestamp_str = request.form.get('timestamp')
    user_id = session.get('user', {}).get('user_id')
    beli_id = request.form.get('beli_id') or None
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
    except Exception:
        timestamp = datetime.now()

    conn = get_db()
    cur = conn.cursor()

    # Generate stok_id
    cur.execute("SELECT stok_id FROM stok_masuk WHERE stok_id LIKE 'SM%' ORDER BY stok_id DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        next_num = int(row[0][2:]) + 1
    else:
        next_num = 1
    stok_id = f'SM{next_num:03d}'

    # Insert ke stok_masuk
    cur.execute("""
        INSERT INTO stok_masuk (stok_id, menu_id, jumlah, tanggal, keterangan, user_id, beli_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (stok_id, menu_id, jumlah, timestamp, keterangan, user_id, beli_id))

    # Update stok di tabel menu
    cur.execute("UPDATE menu SET stok = stok + %s WHERE menu_id = %s", (jumlah, menu_id))

    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('stok.index'))

@bp.route('/laporan')
def laporan_stok_pdf():
    print(">>> Laporan stok dipanggil")
    start = request.args.get('start')
    end = request.args.get('end')

    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT s.tanggal, m.nama, s.jumlah, s.keterangan
        FROM stok_masuk s
        JOIN menu m ON s.menu_id = m.menu_id
        WHERE s.tanggal BETWEEN %s AND %s
        ORDER BY s.tanggal DESC
    """
    cur.execute(query, (start, end + " 23:59:59"))
    rows = cur.fetchall()

    # Generate PDF
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(width / 2, y, "Laporan Stok Masuk - Relax Cafe")
    y -= 30

    if start or end:
        pdf.setFont("Helvetica", 11)
        pdf.drawCentredString(width / 2, y, f"Periode: {start or '-'} s/d {end or '-'}")
        y -= 20

    # Header
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Tanggal")
    pdf.drawString(130, y, "Menu")
    pdf.drawString(280, y, "Jumlah")
    pdf.drawString(380, y, "Keterangan")
    y -= 15
    pdf.line(40, y, 560, y)
    y -= 15

    # Rows
    pdf.setFont("Helvetica", 10)
    for tanggal, nama_menu, jumlah, keterangan in rows:
        if y < 60:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = height - 50
        pdf.drawString(40, y, tanggal.strftime('%Y-%m-%d'))
        pdf.drawString(130, y, str(nama_menu))
        pdf.drawString(280, y, str(jumlah))
        pdf.drawString(380, y, str(keterangan or "-"))
        y -= 15

    pdf.setTitle("Laporan Stok Masuk")
    pdf.showPage()
    pdf.save()
    buffer.seek(0)

    response = send_file(
        buffer,
        as_attachment=False,
        download_name=f'laporan_stok_{start}_sd_{end}.pdf',
        mimetype='application/pdf'
    )
    response.headers["Cache-Control"] = "no-store"
    return response
