import os
from app import create_app

# The environment is loaded during bot_instance initialization.
if __name__ == "__main__":
    app = create_app()
    # Start the app on the default production port 5000
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    print(f"\nHomefy Chatbot running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
else:
    # This allows WSGI servers to find the 'app' if they import main
    app = create_app()
