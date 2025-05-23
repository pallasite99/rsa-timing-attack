import os
import sys
import time
import random
import json
from flask import Flask, render_template, request, jsonify

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.rsa_core import generate_rsa_keypair, encrypt_message, decrypt_message

app = Flask(__name__)
app.secret_key = "rsa-attack-ui"

# Globals
public_key = None
private_key = None
timing_log = []
sender_logs = []
receiver_logs = []
last_ciphertext = None
constant_time_enabled = False

def save_public_key_to_file(e, n):
    with open('../network/public_key.txt', 'w') as f:
        f.write(f"{e}\n{n}")

def load_public_key_from_file():
    with open('../network/public_key.txt', 'r') as f:
        e = int(f.readline().strip())
        n = int(f.readline().strip())
    return (e, n)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sender')
def sender_page():
    return render_template('sender.html')

@app.route('/receiver')
def receiver_page():
    return render_template('receiver.html')

@app.route('/attacker')
def attacker_page():
    return render_template('attacker.html')

@app.route('/start-receiver', methods=['POST'])
def start_receiver():
    global public_key, private_key
    public_key, private_key = generate_rsa_keypair()
    save_public_key_to_file(*public_key)
    return jsonify({
        "message": "Receiver started and keys generated.",
        "public_key": public_key
    })

@app.route('/send-message', methods=['POST'])
def send_message():
    global sender_logs, receiver_logs, last_ciphertext
    public_key = load_public_key_from_file()
    message = request.form['message']

    start = time.perf_counter()
    ciphertext = encrypt_message(message.encode(), public_key)
    end = time.perf_counter()
    encryption_time = round(end - start, 6)

    last_ciphertext = ciphertext

    entry = {
        "message": message,
        "ciphertext": str(ciphertext),
        "encryption_time": encryption_time
    }
    sender_logs.append(entry)
    with open('sender_logs.json', 'w') as f:
        json.dump(sender_logs, f)

    if private_key:
        if constant_time_enabled:
            time.sleep(0.01)  # Constant-time decryption simulation
        plaintext = decrypt_message(ciphertext, private_key).decode(errors='ignore')

        receiver_logs.append({
            "ciphertext": str(ciphertext),
            "decrypted": plaintext
        })
        with open('receiver_logs.json', 'w') as f:
            json.dump(receiver_logs, f)

    return jsonify({"ciphertext": str(ciphertext)})

@app.route('/api/receiver/logs', methods=['GET'])
def get_receiver_logs():
    if os.path.exists('receiver_logs.json'):
        with open('receiver_logs.json', 'r') as f:
            logs = json.load(f)
    else:
        logs = []
    return jsonify({"logs": logs})

@app.route('/run-attacker', methods=['POST'])
def run_attacker():
    global public_key, private_key, timing_log
    e, n = load_public_key_from_file()
    results = []

    for _ in range(20):
        msg = random.randint(1, n - 1)
        msg_bytes = msg.to_bytes((msg.bit_length() + 7) // 8, 'big')
        cipher = encrypt_message(msg_bytes, (e, n))

        start = time.perf_counter()
        decrypt_message(cipher, private_key)
        end = time.perf_counter()

        delta = round(end - start, 6)
        results.append({
            "ciphertext": str(cipher)[:12] + "...",
            "time": delta
        })

    times = [r['time'] for r in results]
    avg = sum(times) / len(times)
    stddev = (sum((t - avg)**2 for t in times) / len(times))**0.5
    threshold = avg + stddev

    for r in results:
        r['bit_guess'] = 1 if r['time'] > threshold else 0
        r['is_slow'] = r['time'] > threshold
        r['replay'] = False

    timing_log.extend(results)
    return jsonify({"results": results})

@app.route('/replay-last', methods=['POST'])
def replay_last():
    global last_ciphertext, timing_log
    if not last_ciphertext:
        return jsonify({"error": "No message to replay."}), 400

    start = time.perf_counter()
    decrypt_message(last_ciphertext, private_key)
    end = time.perf_counter()
    delta = round(end - start, 6)

    times = [r['time'] for r in timing_log]
    threshold = (sum(times) / len(times)) * 1.10 if times else delta

    entry = {
        "ciphertext": str(last_ciphertext)[:12] + "...",
        "time": delta,
        "bit_guess": 1 if delta > threshold else 0,
        "replay": True
    }
    timing_log.append(entry)
    return jsonify({"replayed": entry})

@app.route('/replay-message', methods=['POST'])
def replay_last_message():
    global sender_logs, private_key, receiver_logs

    if not sender_logs:
        return jsonify({"error": "No message to replay."}), 400

    last_entry = sender_logs[-1]
    message = last_entry["message"]

    start = time.perf_counter()
    ciphertext = encrypt_message(message.encode(), load_public_key_from_file())
    end = time.perf_counter()
    encryption_time = round(end - start, 6)

    entry = {
        "message": message,
        "ciphertext": str(ciphertext),
        "encryption_time": encryption_time
    }
    sender_logs.append(entry)
    with open('sender_logs.json', 'w') as f:
        json.dump(sender_logs, f)

    if private_key:
        if constant_time_enabled:
            time.sleep(0.01)
        plaintext = decrypt_message(ciphertext, private_key).decode(errors='ignore')

        receiver_logs.append({
            "ciphertext": str(ciphertext),
            "decrypted": plaintext
        })
        with open('receiver_logs.json', 'w') as f:
            json.dump(receiver_logs, f)

    return jsonify({"ciphertext": str(ciphertext)})

@app.route('/analyze', methods=['POST'])
def analyze():
    return jsonify({"data": timing_log})

@app.route('/api/encryption-times', methods=['GET'])
def encryption_times():
    if not os.path.exists('sender_logs.json'):
        return jsonify({"data": []})
    with open('sender_logs.json', 'r') as f:
        logs = json.load(f)
    return jsonify({
        "data": [
            {"label": f"#{i+1}", "time": entry.get("encryption_time", 0)}
            for i, entry in enumerate(logs)
        ]
    })

@app.route('/api/attacker/bit-recovery', methods=['GET'])
def bit_recovery():
    global timing_log
    if not timing_log:
        return jsonify({"data": []})
    return jsonify({
        "guessed_bits": [r['bit_guess'] for r in timing_log],
        "data": timing_log
    })

@app.route('/toggle-constant-time', methods=['POST'])
def toggle_constant_time():
    global constant_time_enabled
    enabled = request.args.get('enabled', 'false').lower() == 'true'
    constant_time_enabled = enabled
    return jsonify({"message": f"Constant-time decryption {'enabled' if enabled else 'disabled'}."})

if __name__ == '__main__':
    app.run(debug=True)
