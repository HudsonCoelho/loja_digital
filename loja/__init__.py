from flask import Flask, send_from_directory, request
import os

def create_app(config_overrides: dict | None = None):
    # static_folder is relative to the app root (loja/), so we go up one directory
    app = Flask(__name__, static_folder="../static/erp", static_url_path="/static/erp")
    
    from .config import build_config
    app.config.from_mapping(build_config(config_overrides))

    from .db import close_db
    app.teardown_appcontext(close_db)

    # Register CSRF protection
    from .security import verificar_csrf
    app.before_request(verificar_csrf)

    # Register all blueprints
    from .routes import auth, produtos, vendas, caixa, clientes, estoque, relatorios, usuarios, config as config_routes
    app.register_blueprint(auth.bp)
    app.register_blueprint(produtos.bp)
    app.register_blueprint(vendas.bp)
    app.register_blueprint(caixa.bp)
    app.register_blueprint(clientes.bp)
    app.register_blueprint(estoque.bp)
    app.register_blueprint(relatorios.bp)
    app.register_blueprint(usuarios.bp)
    app.register_blueprint(config_routes.bp)

    # Inicia agendador de backup diário em segundo plano
    from .services.backup import iniciar_agendador_backup
    iniciar_agendador_backup(app)

    @app.route("/")
    def index():
        r = app.send_static_file("index.html")
        r.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return r
        
    @app.route("/login")
    def login_page():
        return app.send_static_file("login.html")
        
    @app.route("/cupom")
    def cupom_page():
        return app.send_static_file("cupom.html")

    @app.route("/favicon.ico")
    def favicon():
        return app.send_static_file("img/favicon.ico")

    @app.route("/media/<path:filename>")
    def media_files(filename):
        return send_from_directory(app.config["UPLOAD_DIR"], filename)

    @app.after_request
    def set_secure_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    from .utils import ErroNegocio
    @app.errorhandler(ErroNegocio)
    def handle_erro_negocio(error):
        payload = {"success": False, "error": error.mensagem}
        if hasattr(error, 'extra') and error.extra:
            payload.update(error.extra)
        return payload, error.status

    return app
