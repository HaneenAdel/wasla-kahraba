from flask_app import create_app, socketio

app, socketio_instance = create_app()

if __name__ == "__main__":
    print("Starting Wasla Kahraba...")
    print("Open your browser to: http://localhost:8080" )

    if socketio_instance is not None:
        socketio_instance.run(
            app,
            host="0.0.0.0",
            port=8080,
            debug=True,
            allow_unsafe_werkzeug=True
        )
    else:
        app.run(
            host="0.0.0.0",
            port=8080,
            debug=True
        )
