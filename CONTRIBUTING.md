# Contributing to ViralClip AI Studio

Welcome to the **ViralClip AI Studio** development repository! We are excited to collaborate and continuously improve the video engine, viral extraction intelligence, and creator experience.

---

## 🔒 1. Secrets & Credentials Policy (STRICT)

**NEVER commit private secrets, API keys, or OAuth credentials to Git.**

* **`.env` is gitignored:** Keep your personal keys in your local `.env`. Copy `.env.example` to get started:
  ```bash
  cp .env.example .env
  ```
* **YouTube OAuth:** Do NOT share your `client_secret.json` or personal channel `token.json`. Each developer should test with their own Google Cloud test project.
* **Storage Protection:** The `storage/` directory contains active downloaded media and personal databases. These are excluded from Git to prevent repository bloat and credential leakage.

---

## 🛠️ 2. Developer Setup

### Prerequisites
* **Python 3.10+** (64-bit recommended)
* **FFmpeg:** Must be installed and accessible in your system `PATH`. Test with:
  ```bash
  ffmpeg -version
  ```

### Quick Installation
1. **Clone the repository:**
   ```bash
   git clone <repo_url>
   cd VIRAL_CLIPPER
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the development server:**
   ```bash
   python run.py
   ```
   The app will automatically launch and open `http://localhost:5001/studio` in your browser.

---

## 🏗️ 3. Architecture Overview

* **`app/routes.py`:** Flask backend REST API endpoints (clipping, prescan, rendering, channel sync, YouTube publishing).
* **`app/core/video_engine.py`:** Native FFmpeg rendering pipeline (9:16 safe-zone framing, subtitle burning, Hook Audio SFX synthesis, -14 LUFS audio normalization).
* **`app/core/viral_ai.py`:** Gemini AI viral extraction heuristics, 3 Title Archetypes, and linguistic seamless loop retention matcher.
* **`app/core/quality_guard.py`:** 19-point automated quality assurance checklist certifying clips exclusively for YouTube Shorts.
* **`app/core/subtitle.py`:** Advanced ASS subtitle generator with dynamic word-level highlights and Outro Monetization CTA subscribe banner.
* **`app/core/tracker.py`:** SQLite-backed high-concurrency analytics engine tracking views, conversion metrics, and YPP progress.
* **`app/templates/studio.html`:** Single-page reactive Creator Studio with review cards, timeline nudging, and caption quick-fix modals.

---

## 📦 4. Building the Executable (.exe)

To compile the standalone Windows executable with the embedded app icon:
```bash
python build_exe.py
```
This produces `ViralShorts_Studio.exe` in the root directory, fully bundled and ready to run with 1-click.

---

## 📜 5. Intellectual Property & Ownership

All code contributed to this repository becomes part of **ViralClip AI Studio** under the terms of the project [LICENSE](LICENSE). All rights are reserved by the Project Owner.
