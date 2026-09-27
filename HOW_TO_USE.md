# ⚡ ViralClip AI Studio — Master Creator & User Manual

Welcome to **ViralClip AI Studio** — the automated YouTube Shorts engine designed to turn long-form videos into viral, high-retention 9:16 Shorts with dynamic animated captions, audio SFX hooks, and 1-click publishing.

---

## 🚀 1. Quick Start (Running the App)

### Option A: 1-Click Standalone Executable (No Setup Required)
1. Double-click **`ViralShorts_Studio.exe`**.
2. A console window will initialize the engine and **automatically open your browser** to:
   ```
   http://localhost:5001/studio
   ```
3. To exit, simply close the console window or press `Ctrl + C`.

### Option B: Running from Source
```bash
pip install -r requirements.txt
python run.py
```

---

## 🔑 2. Free Setup ($0 Cost)

### Step 1: Google Gemini API Key
1. Get a free API key at [Google AI Studio](https://aistudio.google.com/apikey).
2. Go to the **Settings** tab in ViralClip AI Studio (`http://localhost:5001/settings`).
3. Paste your key into the **Google Gemini API Key** field and click **Save Settings**.
*(Alternatively, create a `.env` file with `GEMINI_API_KEY=your_key_here`)*.

### Step 2: YouTube 1-Click Publishing (Optional but Recommended)
1. Open Google Cloud Console -> Create a project -> Enable **YouTube Data API v3**.
2. Create an **OAuth 2.0 Client ID** (Desktop app) and download `client_secret.json`.
3. Drop `client_secret.json` into the `storage/` folder.
4. In the **Settings** tab, click **Connect YouTube Channel** to authorize 1-click publishing.

---

## 🎬 3. The 5-Step Viral Workflow

### Step 1: Paste Long Video URL & Auto-Prescan
* Copy any long YouTube podcast, interview, or lecture (e.g. Diary of a CEO, Joe Rogan, Huberman Lab).
* Paste the link into the **YouTube Video URL** box in Studio.
* The system performs an **instant pre-scan**, analyzing spoken audio pitch, question density, and emotional peaks in $<2$ seconds.

### Step 2: Extract Viral Moments
* Click **Extract High-Retention Clips**.
* The AI identifies the 5–10 moments with the highest retention potential, scored from 0–100.
* Each clip candidate includes:
  * Hook Virality Score & Spoken Hook
  * Seamless Loop Retention Metric ($>90\%$ for infinite replays)
  * Outro Safe-Zone Monetization Subscribe Banner

### Step 3: Creator Quick Tools
* **Nudge Timestamps (`[-1s]` / `[+1s]`):** Fine-tune where the hook begins or ends with millisecond precision.
* **🏷️ 3 Title Archetypes:** Click to choose between *Curiosity Gap*, *High Stakes*, or *Story Arc* titles for maximum click-through rate.
* **✏️ Edit Captions:** Fix any misheard proper nouns or transcript typos before burning.
* **Auto-Style Dropdown:** Switch subtitle themes (*Alex Hormozi Green Box*, *Dynamic Pop*, *Electric Yellow*, *Crimson Thriller*, *Cyber Cyan*, etc.).

### Step 4: Render with 1-Click
* Click **Render Vertical Short**.
* The engine burns:
  - 9:16 safe-zone framing (blur stack or center crop).
  - High-speed dynamic animated word-by-word captions.
  - Sub-second Hook Audio SFX at $T=0.0s$ to halt scrolling.
  - Outro Monetization Subscribe Banner in the final 3.5 seconds.
  - EBU R128 (-14 LUFS) broadcast loudness audio.

### Step 5: 1-Click Publish or Schedule
* **Publish Now:** Uploads directly to your YouTube channel as Public, then automatically cleans up local storage.
* **Auto-Schedule:** Batch spaces your videos across peak US viewing times (**12:00 PM**, **4:00 PM**, and **8:00 PM EST**).

---

## 📊 4. Monetization & Analytics Dashboard

* Go to **Analytics** (`http://localhost:5001/analytics`) to track:
  * Real-time views, likes, and comments.
  * **Shorts Subs Attributed:** AI conversion modeling from swipe-feed engagement.
  * **YPP Progress Bar:** Live tracking toward the 1,000 subscribers YouTube Partner Program threshold.

---

## 🛠️ 5. Troubleshooting & FAQ

* **Q: FFmpeg not found?**
  * Ensure FFmpeg is installed and added to your Windows environment `PATH`. Run `ffmpeg -version` in PowerShell to test.
* **Q: Port 5001 already in use?**
  * Set `PORT=5002` in your `.env` file or terminate lingering python processes in Task Manager.
* **Q: Where are my rendered videos stored?**
  * Videos are located in `storage/processed/`. When published, local files are automatically cleaned to save drive space.
