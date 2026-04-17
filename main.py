import os
from app import create_app

# The environment is loaded during bot_instance initialization, 
# so by the time we call create_app, everything is set.
app = create_app()

if __name__ == "__main__":
    # Start the app on the default production port 5000
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    print(f"\nHomefy Chatbot running at http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
