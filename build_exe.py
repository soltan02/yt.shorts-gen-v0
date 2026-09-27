import os
import sys
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(BASE_DIR, 'icon.ico')
APP_DIR = os.path.join(BASE_DIR, 'app')
TEMPLATES_DIR = os.path.join(APP_DIR, 'templates')
STATIC_DIR = os.path.join(APP_DIR, 'static')

def build():
    print('=' * 60)
    print('  BUILDING VIRALSHORTS STUDIO STANDALONE EXECUTABLE (.EXE)')
    print('=' * 60)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--name=ViralShorts_Studio',
        '--onefile',
        '--clean',
        '--noconfirm',
        f'--icon={ICON_PATH}',
        f'--add-data={TEMPLATES_DIR};app/templates',
        f'--add-data={STATIC_DIR};app/static',
        '--hidden-import=jinja2',
        '--hidden-import=flask',
        '--hidden-import=google.genai',
        '--hidden-import=googleapiclient',
        '--hidden-import=google_auth_oauthlib',
        '--hidden-import=google.auth',
        '--hidden-import=yt_dlp',
        '--hidden-import=youtube_transcript_api',
        '--hidden-import=sqlite3',
        '--hidden-import=PIL',
        '--hidden-import=requests',
        '--hidden-import=dotenv',
        os.path.join(BASE_DIR, 'run.py')
    ]

    print('Running PyInstaller build...')
    res = subprocess.run(cmd, cwd=BASE_DIR)
    if res.returncode != 0:
        print(f'[ERROR] PyInstaller failed with exit code {res.returncode}')
        sys.exit(res.returncode)

    exe_dist = os.path.join(BASE_DIR, 'dist', 'ViralShorts_Studio.exe')
    exe_root = os.path.join(BASE_DIR, 'ViralShorts_Studio.exe')

    if os.path.exists(exe_dist):
        shutil.copy2(exe_dist, exe_root)
        print("\n" + "=" * 60)
        print("  BUILD SUCCESSFUL!")
        print(f"  [>] Standalone Executable created at: {exe_root}")
        print("  [>] Ready to double-click and run directly!")
        print("=" * 60)

if __name__ == '__main__':
    build()
