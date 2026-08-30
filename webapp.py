# UI for the rug-pull detector

import math
import re
import threading
import uuid

import numpy as np
from flask import Flask, render_template, request, jsonify

from app import scan_token
from feature_extraction_helpers.config import ETHERSCAN_CHAIN_IDS
from prediction_module.predictor import Predictor, PREDICTION_THRESHOLD

app = Flask(__name__)
predictor = Predictor()

# A token is marked 'low risk', if it is below a threshold
SUSPICION_THRESHOLD = 0.5

TOKEN_ADDRESS_PATTERN = re.compile(r'0x[0-9a-fA-F]{40}')

# Saving started scans
scan_jobs = {}


# Main page of UI
@app.route('/')
def index():
    return render_template('index.html')


# Starts to calculate prediction and returns job id to further check status, since scanning a queried token can be
# long for busy and / or old tokens, so a browser may drop a request before recieving a response
@app.route('/api/predict', methods=['POST'])
def start_prediction():
    payload = request.get_json(silent=True) or {}
    chain = payload.get('chain')
    token_address = payload.get('token_address') or ''
    if chain not in ETHERSCAN_CHAIN_IDS:
        return jsonify({'error': f'Unsupported chain, expected one of: {", ".join(ETHERSCAN_CHAIN_IDS)}'}), 400
    if not isinstance(token_address, str) or not TOKEN_ADDRESS_PATTERN.fullmatch(token_address):
        return jsonify({'error': 'Token address must be 0x followed by 40 hex characters'}), 400

    job_id = uuid.uuid4().hex
    scan_jobs[job_id] = {'status': 'running', 'chain': chain, 'token_address': token_address,
                         'result': None, 'error': None}
    threading.Thread(target=calculate_prediction, args=(job_id, chain, token_address), daemon=True).start()
    return jsonify({'job_id': job_id}), 202


# Returns info about queried prediction (status and result once completed)
@app.route('/api/predict/<job_id>')
def get_prediction_status(job_id):
    job = scan_jobs.get(job_id)
    if job is None:
        return jsonify({'error': 'Unknown job id'}), 404
    return jsonify(job)


# Makes a prediction on background thread
def calculate_prediction(job_id, chain, token_address):
    print(f'Scan {job_id} started for {chain} {token_address}')
    try:
        result = scan_token(predictor, chain, token_address)
        result['risk_band'] = get_risk_band(result['scam_probability'])
        scan_jobs[job_id]['result'] = make_json_safe(result)
        scan_jobs[job_id]['status'] = 'done'
        print(f'Scan {job_id} finished: {result["prediction"]} ({result["scam_probability"]})')
    except Exception as error:
        print(f'Scan {job_id} failed: {error}')
        scan_jobs[job_id]['status'] = 'failed'
        scan_jobs[job_id]['error'] = str(error)


# Maps a scam probability to a risk band displayed to user
def get_risk_band(scam_probability):
    if scam_probability is None:
        return None
    if scam_probability >= PREDICTION_THRESHOLD:
        return 'high'
    if scam_probability >= SUSPICION_THRESHOLD:
        return 'suspicious'
    return 'low'


# NaN is not valid JSON and numpy values may produce errors or nulls, so result should be cleared before returning
def make_json_safe(value):
    if isinstance(value, dict):
        return {key: make_json_safe(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [make_json_safe(inner) for inner in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


if __name__ == '__main__':
    # Port 5001 (5000 is used by macOS)
    app.run(debug=True, port=5001)