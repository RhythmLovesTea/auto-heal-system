from flask import Flask, jsonify
import os

app = Flask(__name__)

# This flag is flipped by inject.py to simulate a failure
UNHEALTHY = False

@app.route("/health")
def health():
    if UNHEALTHY:
        return jsonify({"status": "unhealthy", "service": "nginx"}), 500
    return jsonify({"status": "healthy", "service": "nginx"}), 200

@app.route("/")
def index():
    return jsonify({"service": "nginx", "running": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
