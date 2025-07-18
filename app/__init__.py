from flask import Flask
from .models.db import init_db

def create_app():
    app = Flask(__name__)
    app.config.from_pyfile('../config.py')

    init_db(app)

    from .routes import dashboard, transaksi, menu, stok, pembelian, supplier, request
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(transaksi.bp)
    app.register_blueprint(menu.bp)
    app.register_blueprint(stok.bp)
    app.register_blueprint(pembelian.bp)
    app.register_blueprint(supplier.bp)
    app.register_blueprint(request.bp)

    return app
