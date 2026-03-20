from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route("/health")
def health():
    if os.path.exists("/tmp/unhealthy"):
        return jsonify({"status": "unhealthy", "service": "payments-api"}), 500
    return jsonify({"status": "healthy", "service": "payments-api"}), 200

@app.route("/")
def index():
    return jsonify({"service": "payments-api", "running": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
