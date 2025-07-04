from flask import Blueprint, render_template, request, redirect, session, url_for
import psycopg2
from flask import g, current_app
from app.models.db import get_db

bp = Blueprint('dashboard', __name__)

@bp.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT kasir_id, nama FROM kasir WHERE username=%s AND password=%s", (username, password))
        kasir = cur.fetchone()

        cur.close()
        conn.close()

        if kasir:
            session['user'] = {
                'kasir_id': kasir[0],
                'nama': kasir[1]
            }
            return redirect(url_for('dashboard.main'))
        else:
            return render_template('index.html', error='Username atau password salah')

    return render_template('index.html')


@bp.route('/dashboard')
def main():
    if 'user' not in session:
        return redirect(url_for('dashboard.login'))
    return render_template('dashboard.html', user=session['user'])

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('dashboard.login'))
