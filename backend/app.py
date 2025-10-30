import os
from dotenv import load_dotenv
from flask import Flask, jsonify

# Load environment variables from a .env file (if you use one)
load_dotenv()

app = Flask(__name__)

# --- Basic Health Check Route ---
@app.route('/')
def hello_world():
    """Returns a simple greeting to confirm the server is running."""
    return 'Hello, World! The backend is active.'

# --- Example API Endpoint ---
@app.route('/status')
def status_check():
    """Returns a JSON response with the application status."""
    return jsonify({
        'status': 'OK',
        'service': 'Python Backend',
        'version': '1.0'
    })

if __name__ == '__main__':
    # Get the port from environment variable, default to 8080
    port = int(os.environ.get("PORT", 8080))
    # Run the application
    app.run(host='0.0.0.0', port=port, debug=True)