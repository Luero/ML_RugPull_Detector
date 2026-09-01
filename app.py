# Single entry point to the application

from ui_module.webapp import app


if __name__ == '__main__':
    # Port 5001 (5000 is used by macOS)
    app.run(port=5001)
