# ⚡ ViralClip AI — Automated YouTube Shorts Studio & 1-Click Publisher

> Transform any long YouTube podcast, interview, or lecture into high-retention, viral 9:16 Shorts with dynamic animated captions, audio SFX hooks, seamless loop scoring, and 1-click publishing. Built exclusively to reach YouTube Partner Program (YPP) monetization as fast as possible.

[![Exclusively for YouTube Shorts](https://img.shields.io/badge/Platform-YouTube%20Shorts%20Only-FF0000?style=for-the-badge&logo=youtube)](https://youtube.com)
[![Features](https://img.shields.io/badge/Features-18%20Power%20Tools-00FF66?style=for-the-badge)](FEATURES.md)
[![User Manual](https://img.shields.io/badge/User%20Guide-HOW__TO__USE.md-blue?style=for-the-badge)](HOW_TO_USE.md)
[![Contributing](https://img.shields.io/badge/Collaborate-CONTRIBUTING.md-purple?style=for-the-badge)](CONTRIBUTING.md)

---

## 📚 Essential Documentation

- **⭐ [FEATURES.md](FEATURES.md)** — **Complete 18-Point Feature Matrix & Technical Deep Dive** (Loop engine, SFX synthesizer, subtitle themes, monetization banners, quality guard).
- **📖 [HOW_TO_USE.md](HOW_TO_USE.md)** — **Creator User Manual** (Step-by-step 5-minute tutorial, executable usage, and troubleshooting).
- **🤝 [CONTRIBUTING.md](CONTRIBUTING.md)** — **Developer & Friend Collaboration Guide** (How to contribute features safely without exposing secrets).
- **⚖️ [LICENSE](LICENSE)** — Proprietary creator license (All Rights Reserved).

---

## 🌟 Top Highlighted Features

| Feature | Description | Benefit |
| :--- | :--- | :--- |
| **🧠 Gemini 2.5 Flash Detection** | Multi-model fallback chain (Flash + Flash Lite + Heuristics) | Identifies the top 1% highest-retention hooks |
| **🔁 Seamless Loop Scorer** | End-to-beginning linguistic cohesion analysis | Triggers >100% Average Percentage Viewed |
| **🏷️ 3 Title Archetypes** | Curiosity Gap, High Stakes, and Story Arc | 1-click A/B testing for maximum CTR |
| **💬 Pinned Discussion Spark** | Automated polarizing comment generator | Drives comment section engagement velocity |
| **🔊 Hook SFX Synthesizer** | Native FFmpeg pink noise impact whoosh at T=0.0s | Stops the swipe in the first 400 milliseconds |
| **🔔 Monetization Banner** | Safe-zone (Y=1460px) animated lower-third | Converts casual viewers to 1,000 subscribers |
| **🎚️ EBU R128 Loudness** | Dual-pass -14 LUFS broadcast normalization | Perfect competitive loudness with 0 clipping |
| **🎨 ASS Dynamic Subtitles** | 8 Viral Palettes (Hormozi, Pop, Neon, Cyber, etc.) | High-retention word-by-word karaoke zoom |
| **📐 Adaptive 9:16 Framing** | Blur Stack (Podcasts) & Center Crop modes | Studio-grade vertical composition |
| **⏱️ Interactive Trimmer** | [-1s] / [+1s] timestamp nudge buttons | Sub-second precision editing in preview card |
| **✏️ Caption Quick-Fix** | In-browser modal transcript editor | Corrects guest names & jargon before burning |
| **🛡️ 19-Point Quality Guard** | Automated pre-flight video checklist | Prevents corrupt renders & YouTube policy flags |
| **📈 Live Monetization Tracker** | Real-time YPP progress & Shorts Attribution model | Tracks 1,000 Subs and 10M Views goals |
| **📅 Batch US Peak Scheduler** | Auto-queues for 12 PM, 4 PM, and 8 PM EST | Captures maximum US prime-time viewer traffic |
| **💻 Standalone Executable** | 1-Click `ViralShorts_Studio.exe` with auto-browser launch | Run instantly without terminal setup |

*👉 For the complete breakdown of all capabilities, read **[FEATURES.md](FEATURES.md)**.*

---

## 🚀 The "Lazy Creator" 30-Minute Weekly Routine
To hit **1,000 subscribers** and **10,000,000 Shorts views** for the YouTube Partner Program with zero start capital:

1. **Find 2 High-Performing Podcasts per week:**
   - Great channels: *The Diary of a CEO*, *Joe Rogan Experience*, *Andrew Huberman*, *Chris Williamson / Modern Wisdom*, *Lex Fridman*.
2. **Batch Extract:**
   - Paste the link into ViralClip AI Studio.
   - The AI identifies 5–10 viral moments with high-tension hooks in the first 3 seconds.
3. **Render with 1-Click:**
   - Select **Blur Stack** (Podcast standard) or **Center Crop**.
   - Subtitles, Hook SFX, and Subscribe Banner are generated and burnt automatically.
4. **Auto-Schedule 3 Shorts/Day:**
   - Go to **Queue & Schedule** -> Click **Auto-Schedule Selected**.
   - The app spaces your videos out at peak US times: **12:00 PM**, **4:00 PM**, and **8:00 PM EST**.
5. **Track Your Views & Monetization:**
   - Watch the **Monetization Progress Bar** on the Analytics dashboard update live as views roll in.

---

## 🛠️ Quick Start

### Option A: Standalone Executable (Windows)
1. Double-click **`ViralShorts_Studio.exe`**.
2. The server will initialize and automatically open **`http://localhost:5001/studio`** in your browser.

### Option B: Run from Source
```bash
# 1. Clone repository
git clone https://github.com/soltan02/yt.shorts-gen-v0.git
cd yt.shorts-gen-v0

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch application
python run.py
```
Open your browser at: **`http://localhost:5001`**

---

## 🔑 API Keys ($0 Cost)
1. **Google Gemini Key:**
   - Get a free key at [Google AI Studio](https://aistudio.google.com/apikey).
   - Enter it in the **Settings** page in the app.
2. **YouTube Channel 1-Click Upload (Optional but Recommended):**
   - Follow the 2-minute guide in the app's **Settings** tab to place `client_secret.json` in the `storage/` folder.
   - Click **Connect YouTube Channel** once to authorize 1-click uploads and real-time view tracking.

---

## 🔒 Security & Privacy Notice
All personal credentials (`.env`, `client_secret*.json`, OAuth tokens, channel settings, and SQLite databases) are protected by `.gitignore` and are never committed to version control. See **[CONTRIBUTING.md](CONTRIBUTING.md)** for details.
