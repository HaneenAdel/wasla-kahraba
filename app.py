"""
app.py — entry point. Run: python app.py
Then open http://localhost:8080
"""

from flask_app import create_app

app = create_app()

if __name__ == "__main__":
    print("Starting Wasla Kahraba...")
    print("Open your browser to: http://localhost:8080")
    app.run(host='0.0.0.0', port=8080, debug=True)
