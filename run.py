import os
import sys
import threading
import multiprocessing
import webbrowser
import time
from dotenv import load_dotenv

# Configure UTF-8 encoding for Windows terminals
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure multiprocessing works correctly in PyInstaller frozen executables
multiprocessing.freeze_support()

# Load .env from executable's directory if frozen, else project root
app_dir = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
env_file = os.path.join(app_dir, ".env")
if os.path.exists(env_file):
    load_dotenv(env_file)
else:
    load_dotenv()

from app import create_app

def launch_browser(port: int):
    """Wait for server to bind, then open the Studio interface in the default browser."""
    time.sleep(1.2)
    try:
        webbrowser.open(f"http://localhost:{port}/studio")
    except Exception as e:
        print(f"[Launcher] Could not open browser automatically: {e}")

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", 5001))
    is_frozen = getattr(sys, 'frozen', False)

    print("\n" + "=" * 62)
    print("  [*] VIRALCLIP AI - YOUTUBE SHORTS STUDIO (10/10 EDITION)")
    print(f"  [>] Local Studio URL : http://localhost:{port}/studio")
    print(f"  [>] Storage Folder   : {os.path.join(app_dir, 'storage')}")
    print("=" * 62 + "\n")

    # Launch browser automatically
    threading.Thread(target=launch_browser, args=(port,), daemon=True).start()

    # In frozen exe, disable debug/reloader to prevent child process forks
    app.run(
        debug=not is_frozen,
        use_reloader=not is_frozen,
        host="127.0.0.1",
        port=port
    )
