# UI for the rug-pull detector

from flask import Flask, render_template

app = Flask(__name__)


# Main page of UI
@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    # Port 5001 (5000 is used by macOS)
    app.run(debug=True, port=5001)