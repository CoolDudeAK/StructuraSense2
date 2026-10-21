"""Flask application factory. Serves the JSON API under /api and the static frontend at /."""
from flask import Flask, jsonify, send_from_directory

from . import auth, config, db
from .routes import (alerts_routes, auth_routes, business_routes, cloud_routes, ingest, lab_routes, models_routes, signals, sim_routes,
                     structures, system_routes, vision_routes)
from .services import cloud_sync, seed, simulator


def create_app(start_workers=True, seed_demo=None):
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    app.json.sort_keys = False

    db.init_db()
    if (config.SEED_DEMO if seed_demo is None else seed_demo):
        seed.seed_all()
    for m in (auth_routes, structures, ingest, signals, vision_routes, alerts_routes, sim_routes, models_routes, cloud_routes,
              system_routes, business_routes, lab_routes):
        app.register_blueprint(m.bp)

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if not resp.headers.get("Cache-Control"):
            resp.headers["Cache-Control"] = "no-cache"
        import os
        origin = os.environ.get("SS_CORS_ORIGIN")  # e.g. a separate front-end or Supabase edge function
        if origin:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Device-Key"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return resp

    @app.errorhandler(404)
    def nf(e):
        return auth.error("not_found", "That address does not exist.", 404)

    @app.errorhandler(405)
    def mna(e):
        return auth.error("method_not_allowed", "That method is not allowed here.", 405)

    @app.errorhandler(413)
    def big(e):
        return auth.error("too_large", "The upload is larger than 16 MB.", 413)

    @app.errorhandler(Exception)
    def boom(e):
        import traceback
        traceback.print_exc()
        return auth.error("server_error", "Something went wrong on the server. Check the terminal for details.", 500)

    @app.get("/")
    def index():
        return send_from_directory(config.FRONTEND_DIR, "index.html")

    @app.get("/<path:p>")
    def static_files(p):
        if p.startswith("api/"):
            return auth.error("not_found", "That address does not exist.", 404)
        return send_from_directory(config.FRONTEND_DIR, p)

    if start_workers:
        simulator.start()
        cloud_sync.start_worker()
    return app
