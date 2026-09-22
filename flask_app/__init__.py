import os

from flask import Flask

try:
    from flask_socketio import SocketIO
except ImportError:
    SocketIO = None

if SocketIO:
    socketio = SocketIO(
        cors_allowed_origins="*",
        async_mode="threading"
    )
else:
    socketio = None


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-for-production")

    from .utils.database import Database
    db = Database()
    db.create_tables(purge=False)
    db.backfill_embeddings()
    app.db = db

    if socketio:
        socketio.init_app(app)

    from .routes import main
    app.register_blueprint(main)

    try:
        from .utils.socket_events import register_events
        register_events(socketio)
    except ImportError:
        pass

    @app.after_request
    def disable_cache(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    return app, socketio
