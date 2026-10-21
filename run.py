"""Start StructuraSense:   python run.py        (then open http://127.0.0.1:5000)"""
import argparse
import sys

from backend import config


def main():
    ap = argparse.ArgumentParser(description="StructuraSense server")
    ap.add_argument("--host", default=config.HOST, help="use 0.0.0.0 to let other devices on your network connect (ESP32)")
    ap.add_argument("--port", type=int, default=config.PORT)
    ap.add_argument("--reset", action="store_true", help="wipe the local database and reload demo data")
    a = ap.parse_args()
    if a.reset:
        from backend import db
        from backend.services import seed
        db.init_db()
        seed.reset_all()
        print("Database reset with demo data.")
    from backend.app import create_app
    app = create_app()
    print(f"\n  StructuraSense is running.  Open  http://{'127.0.0.1' if a.host == '0.0.0.0' else a.host}:{a.port}  in Chrome or Edge.")
    print("  Demo sign-ins are listed in README.md.  Press Ctrl+C to stop.\n")
    app.run(host=a.host, port=a.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    sys.exit(main())
