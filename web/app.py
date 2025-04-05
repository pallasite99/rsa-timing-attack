import os
import sys
import time
import random
from flask import Flask, render_template, request, jsonify

# Fix Python path to access core/ from web/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Now import rsa_core from core/
from core.rsa_core import generate_rsa_keypair, encrypt_message, decrypt_message

app = Flask(__name__)
app.secret_key = "rsa-attack-ui"

# Globals
public_key = None
private_key = None
timing_log = []

# --- Utility ---
def save_public_key_to_file(e, n):
    with open('../network/public_key.txt', 'w') as f:
        f.write(f"{e}\n{n}")

def load_public_key_from_file():
    with open('../network/public_key.txt', 'r') as f:
        e = int(f.readline().strip())
        n = int(f.readline().strip())
    return (e, n)

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/receiver')
def receiver_page():
    return render_template('receiver.html')

@app.route('/sender')
def sender_page():
    return render_template('sender.html')

@app.route('/attacker')
def attacker_page():
    return render_template('attacker.html')

# --- APIs ---
@app.route('/start-receiver', methods=['POST'])
def start_receiver():
    global public_key, private_key
    public_key, private_key = generate_rsa_keypair()
    save_public_key_to_file(*public_key)
    return jsonify({
        "message": "Receiver started.",
        "public_key": public_key
    })

@app.route('/send-message', methods=['POST'])
def send_message():
    global public_key
    public_key = load_public_key_from_file()
    message = request.form['message']
    cipher = encrypt_message(message.encode(), public_key)
    return jsonify({"ciphertext": str(cipher)})

@app.route('/run-attacker', methods=['POST'])
def run_attacker():
    global public_key, private_key, timing_log
    e, n = load_public_key_from_file()
    results = []
    for _ in range(10):
        msg = random.randint(1, n - 1)
        msg_bytes = msg.to_bytes((msg.bit_length() + 7) // 8, 'big')
        cipher = encrypt_message(msg_bytes, (e, n))

        start = time.perf_counter()
        decrypt_message(cipher, (private_key[0], private_key[1]))
        end = time.perf_counter()
        results.append({
            "ciphertext": str(cipher)[:12] + "...",
            "time": round(end - start, 6)
        })

    timing_log = results
    return jsonify({"results": results})

@app.route('/analyze', methods=['POST'])
def analyze():
    return jsonify({"data": timing_log})

if __name__ == '__main__':
    app.run(debug=True)
