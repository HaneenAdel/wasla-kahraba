try:
    from flask_socketio import emit
except ImportError:
    emit = None


def register_events(socketio):
    if socketio is None or emit is None:
        return

    @socketio.on("connect")
    def connected():
        emit("connection_status", {"connected": True})

    @socketio.on("point_updated")
    def point_updated(payload):
        emit("point_updated", payload, broadcast=True)
