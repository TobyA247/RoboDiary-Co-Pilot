RoboDiary Co-Pilot
---
All-local, no internet.
Portal: http://127.0.0.1:5055 · Ollama: http://127.0.0.1:11434
Models: llava:7b (image captions) + gpt-oss:20b (Ask + Travel Diary)
---
Heads-up: Run every command in PowerShell from the repository root folder after you clone/unzip this pack.
---
🧰 Hardware (recommended)
Item	Recommendation
OS	Windows 10/11
CPU	8+ cores
RAM	24–32 GB (20B ≈ 13 GB + overhead)
Storage	NVMe SSD (faster model loading)
---
📁 What’s in this repo
.
├─ diary_portal.py              # Flask web app (the local portal)
├─ requirements.txt             # Python dependencies
├─ run_portal.ps1               # One-shot launcher for PowerShell
├─ tools/
│  ├─ send_sample.ps1           # Sends the newest image in mock_rover/mock_images
│  └─ diagnose_and_prompt.ps1   # Quick environment checks + helper prompts
├─ mock_rover/
│  ├─ run_mock_rover.ps1        # Sends a short sequence as if from a rover
│  └─ mock_images/              #  JPG/PNG test images  <<< alternativly use your own images here
│     ├─ sample01.jpg
│     └─ ...
└─ README.md                    # this file
---
Tip: Use your own photos freely — any number of .jpg/.png files in mock_rover/mock_images/ with any names will be picked up by the tools.
---
🚀 One-time setup
# 1) Ollama + models
``` winget install -e --id Ollama.Ollama --source winget
``` ollama pull llava:7b
``` ollama pull gpt-oss:20b
```````````````````````````````````````````````````````
# 2) Python environment (Windows)
``` py -3.10 -m venv .venv
``` .\.venv\Scripts\Activate.ps1
``` pip install -U pip
``` pip install -r .\requirements.txt
`````````````````````````````````````
▶️ Run the portal
# From the repo root in PowerShell first Window:
``` pwsh -ExecutionPolicy Bypass -File .\run_portal.ps1
```````````````````````````````````````````````````````
Open the UI: http://127.0.0.1:5055/
(Also reachable on your LAN as http://<your-ip>:5055 if your firewall allows.)

Note: Any image you post is copied to
C:\Users\<you>\Documents\diary_data\img\img_*.jpg automatically.
---
# From the repo root in PowerShell second Window:

## For a quick try

Option A — One image (newest in mock_rover/mock_images)

``` pwsh -ExecutionPolicy Bypass -File .\tools\send_sample.ps1
``````````````````````````````````````````````````````````````

## Option B — Short “journey” (multiple images)

# Sends the first 3 images found in .\mock_rover\mock_images
``` pwsh -ExecutionPolicy Bypass -File .\mock_rover\run_mock_rover.ps1 -ImagesPath .\mock_rover\mock_images -Count 3
`````````````````````````````````````````````````````````````````````````````````````````````````````````````````````

## Option C — Manual curl (explicit file)

# Replace the path with any JPG/PNG you want:
``` curl -F "title=manual" `
     -F "text=hello" `
     -F "image=@C:\path\to\your\photo.jpg" `
     http://127.0.0.1:5055/api/post
``````````````````````````````````````````````

## Tip: If captions say “timeout,” llava:7b may be warming up. Give it a moment and try again.

✅ Expected Outcome (functional checklist)

## New timeline entry with a caption
Post an image (any option above). You should see a new card: image on the left, and a short 1–2 line caption on the right (title like “update”/“pi test”, state “idle”, risk near 0).

## Ask (20B) answers a question
Type a question (e.g., “What changed recently?”) and click Ask (20B). A concise answer appears near the input box, using only the recent timeline.

## Create travel diary (20B) summarises
(Optional) add a short note in the textbox, then click Create travel diary (20B). A new travel diary entry is added with two           short paragraphs that weave in your note.
---
🩺 Troubleshooter 
```pwsh -ExecutionPolicy Bypass -File .\tools\diagnose_and_prompt.ps1 -QuickTests
``````````````````````````````````````````````````````````````````````````````````

Common fixes

## Portal not reachable → Keep the PowerShell window running; check firewall; visit http://127.0.0.1:5055/.

## Caption error / timeout → Ensure ollama serve is running; ollama list shows llava:7b; retry after warm-up.

## Ask/Diary timeout → Confirm gpt-oss:20b is pulled; ensure enough RAM; close heavy apps and try again.

## No images appear → Post to /api/post; run scripts from the repo root; put JPG/PNG files under .\mock_rover\mock_images\.
---
🔒 Privacy

RoboDiary Co-Pilot runs entirely offline. Images and text never leave the machine; all reasoning is done via local Ollama models.
---
📜 License

Use under the license included in this pack. Models (llava:7b, gpt-oss:20b) are pulled and run via Ollama under their respective licenses.
---

