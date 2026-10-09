# Dubber ខ្មែរ (Khmer Dubber Studio)

Video -> Transcribe -> Translate (any language incl. Khmer/Chinese) -> Khmer/other voice -> Export.
Includes: draggable Blur (cover hard-coded subtitles), Read Screen Text (OCR via Gemini Vision),
Text/Logo/Sponsor/Watermark/Avatar overlays, Crop/Flip, Vocal Remover (Demucs), timeline editor with
drag-to-move segments, per-line voice profiles and preview, Auto Dub one-click pipeline.

## Install
1. Python 3.10-3.12, and FFmpeg (ffmpeg + ffprobe in PATH)
2. `pip install -r requirements.txt`
3. (Optional Vocal Remover / Isolate BGM) `pip install demucs`
4. `python run.py`

## Setup
Header (⚙ Settings): Gemini API Key (free: aistudio.google.com/apikey) — OPTIONAL.
**គ្មាន key ក៏បានដែរ:** Whisper (Local, offline) សម្រាប់ Transcribe + `Free (No API key)` សម្រាប់ Translate + Edge voice។
Groq ត្រូវបានដកចេញហើយ។
Header (⟳): list every Gemini model available on your key.

## Translate (2 modes)
- **Free (No API key)** — លឿនខ្លាំង (ប្រយោគច្រើនក្នុងពេលតែមួយ + cache), ប្រើ Internet តែមិនត្រូវការ key។ ជាលំនាំដើមពេលគ្មាន Gemini key។
- **Gemini (AI)** — បកប្រែតាមបរិបទ + កាត់ប្រយោគឱ្យល្មមពេលវេលានិយាយក្នុងវីដេអូ (ត្រូវការ key)។ បើ Gemini ដាច់/គ្មាន key កម្មវិធីប្តូរទៅ Free ដោយស្វ័យប្រវត្តិ។
- ☰ → **Quick Translate (No API key)** សម្រាប់បកប្រែអត្ថបទដោយឥតបង្កើតគម្រោង។

## Workflow
- Fast: Open Video (📂) -> ⚡ Auto Dub -> Export (⬆)
- Manual: 🎤 Transcribe -> 🌐 Translate -> tick rows -> Generate N selected -> 🔊 Generate Dub -> Export
- Hard-coded subtitles (e.g. Chinese burned into the video): 🌫 Blur (drag over the text) -> 🔎 Read Screen Text
  -> 🌐 Translate to Khmer -> Generate Dub
- Visuals: Blur / Text / Photo-logo / Sponsor / Watermark / Avatar / Music are draggable on the video preview
  (scroll to resize, Delete key to remove) and are baked in on Export.

## ចិន → ខ្មែរ (ជំហានខ្លី)
1. ⚙ Settings → ដាក់ Gemini API Key → ចុច ⟳
2. Source language = Chinese, Target (ក្នុងប្រអប់ខាងស្តាំ) = Khmer
3. 📂 បើកវីដេអូ → ⚡ Auto Dub (ឬ 🎤 Transcribe → 🌐 Translate → 🔊 Generate Dub) → ⬆ Export
4. មានស្រាប់ជា SRT ចិន? ⬇ Import SRT → 🌐 Translate → 🔊 Generate Dub

## ប្រសិនបើមាន error
- `pip install -U edge-tts` (សំឡេងខ្មែរ Piseth/Sreymom ត្រូវការ edge-tts ថ្មី + Internet)
- ពិនិត្យ `ffmpeg -version` និង `ffprobe -version` ដំណើរការក្នុង Terminal
- ជួរណាបង្កើតសំឡេងមិនបាន កម្មវិធីទុកស្ងាត់ ហើយបង្ហាញបញ្ជីជួរនោះ (មិនបញ្ឈប់ទាំងមូលទេ)
- ☰ → View log ដើម្បីមើលសារលម្អិត

## Android
`server.py` (FastAPI) + `android_app/` (Flutter client) — មើល `android_app/README.md`។

## ប្រើលើទូរស័ព្ទ (មិនបាច់ដំឡើង app)
1. លើកុំព្យូទ័រ: `pip install -r requirements-server.txt` (និង FFmpeg) រួច `python server.py`
2. វានឹងបង្ហាញ `http://192.168.x.x:8765` — បើកអាសយដ្ឋាននេះក្នុង Chrome/Safari នៃទូរស័ព្ទ (Wi-Fi តែមួយ)
3. ជ្រើសវីដេអូ → ចាប់ផ្តើម → កែអត្ថបទ/ប្រុស-ស្រី → បង្កើតសំឡេង + Export → ទាញយក
4. ចង់ដាក់លើអេក្រង់ដើម: Chrome ⋮ → "Add to Home screen"
5. បើ Windows Firewall សួរ សូមអនុញ្ញាត Python។ កុំបើក server ទៅ Internet ដោយគ្មាន `KD_TOKEN` (set KD_TOKEN=ពាក្យសម្ងាត់)
