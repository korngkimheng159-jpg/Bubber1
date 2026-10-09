# ការកែលម្អ (Fix list)

## 1) សំឡេងដាច់ពាក់កណ្ដាល / មិនពេញរឿង
- `media.split_audio` — កាត់ឈុតសំឡេង (chunk) ត្រង់ចន្លោះស្ងាត់ជិតបំផុត មិនកាត់ពាក់កណ្ដាលប្រយោគទៀត
- `ai._stt_one` — បើ Gemini សរសេរតិចជាងសំឡេងពិត នឹងសួរម្ដងទៀត (model/temperature ផ្សេង) ហើយមិន cache លទ្ធផលទទេ
- `tts.render_clips` — Edge TTS ស្របគ្នា 8 → 5; ជួរដែលបរាជ័យនឹងព្យាយាមម្ដងទៀតម្ដងមួយៗ (ជំនួសឲ្យទុកស្ងាត់)
- `tts._voice_to_wav` — ប្រយោគដែលខ្លីខុសធម្មតា (server ផ្ដាច់កណ្ដាលផ្លូវ) នឹងបង្កើតឡើងវិញ
- `tts.compose` — ជួរដែលចប់ក្រោយគេមិនត្រូវកាត់ចុងទៀតទេ

## 2) សំឡេងយឺតជាងវីដេអូដើម
- `tts._trim_silence` — កាត់ស្ងាត់ដើម/ចុងនៃសំឡេង AI (0.2–0.5 វិនាទី ក្នុងមួយជួរ)
- `tts.compose` — ជួរវែងជាងពេលតួសម្តែង ចាប់ផ្តើមមុនបន្តិច (≤0.35 វិនាទី) ជំនួសឲ្យចប់យឺត; ពន្យារអតិបរមា 0.8 → 0.6 វិនាទី
- `tts.slot_for` — សំឡេងត្រូវចប់មុនជួរបន្ទាប់ចាប់ផ្តើម
- Auto-Fit: Soft 1.35→1.45×, Hard 1.8→1.9×
- Gemini ត្រូវសរសេរខ្លីជាងមុន (Khmer 12 តួ/វិនាទី, ×1.05)

## 3) បកប្រែមិនចំតួអង្គ
- STT ឥឡូវផ្ដល់ `speaker` (S1,S2…) ហើយ gender របស់អ្នកនិយាយម្នាក់ៗត្រូវបានបូកសន្លឹកឆ្នោត (majority vote) កុំឲ្យប្តូរប្រុស/ស្រីរាល់ជួរ
- Translate ទទួល gender អ្នកនិយាយ → ជ្រើស ខ្ញុំ/បង/អូន/គាត់… និងសម្ដីឲ្យត្រូវតួ ហើយរក្សាឈ្មោះ/សព្វនាមឲ្យដូចគ្នា
- Auto Dub: ទាយ gender (Whisper) មុនបកប្រែ; `detect_genders` មើលបរិបទ 6 ជួរមុន

## 4) បកប្រែលឿនជាងមុន និងត្រូវតាម script ដើម
- `freetr.translate` — ផ្ញើច្រើនជួរក្នុង request តែមួយ (≤20 ជួរ) ជំនួសឲ្យមួយជួរម្តង; បើចំនួនជួរមិនត្រូវ នឹងធ្វើឡើងវិញតែ batch នោះម្តងមួយជួរ
- `freetr.detect_sl` — ស្គាល់ភាសាដើម (ចិន/ជប៉ុន/កូរ៉េ) ដោយអក្សរ ជំនួសឲ្យឲ្យ Google ទាយ (ជួរខ្លីមិនច្រឡំទៀត)
- `ai._gemini_batch` — បញ្ជាឲ្យបកប្រែគ្រប់ពាក្យ មិនលុប មិនបន្ថែម មិនកែអត្ថន័យ; ប្រវែង (`target_chars`) ជាគោលដៅទន់ប៉ុណ្ណោះ (សំឡេងត្រូវបាន Auto-Fit បង្កើនល្បឿនឲ្យ); temperature 0.1
- Gemini: batch 30 ជួរ, ស្របគ្នាបានដល់ 12, context ជុំវិញ 4 ជួរ
- `ai.shorten_texts` — កាត់ខ្លីតែពេលចាំបាច់ ហើយរក្សាអត្ថន័យសំខាន់ទាំងអស់
- Whisper (Local): beam 2, `condition_on_previous_text=False`, prompt ចិនសាមញ្ញ → អត្ថបទដើមត្រឹមត្រូវជាង
- Groq: គ្មានកូដ Groq ទៀតទេ (នៅសល់តែបន្ទាត់ប្តូរ config ចាស់ → Whisper)

## 5) សំឡេងដាច់ពាក់កណ្ដាល + Auto GPU/CPU
- `tts._ends_abruptly` — ស្គាល់ថាសំឡេងឈប់ពេលកំពុងលាន់ឮ (Network ផ្ដាច់ចុងប្រយោគ) → បង្កើតឡើងវិញរហូត 4 ដង ហើយរក្សា take វែងជាងគេ
- `tts._trim_silence` — threshold ទាក់ទងនឹងសំឡេង (មិនកាត់ចុងពាក្យខ្មែរដែលស្ងាត់), tail 0.16s, fade-out 20ms
- ក្លីបដែលនៅតែដាច់ ត្រូវបានចំណាំ (`.bad`) ហើយបង្កើតឡើងវិញលើកក្រោយ ជំនួសឲ្យ cache ដាច់រហូត
- `tts._clean` — សញ្ញាចិន/ក្រចក/សញ្ញាសម្រង់ ដែលធ្វើឲ្យសំឡេងរំលង ត្រូវបានសម្អាត
- `core/device.py` — Auto GPU/CPU: Whisper ប្រើ GPU តែពេលវាគាំទ្រ float16 (កាតចាស់ដូច 940MX → CPU int8 លឿនជាង); បើ GPU error ណាមួយ → CPU ស្វ័យប្រវត្តិ
- Demucs: GPU តែពេល VRAM ≥ 3.5 GB និងកាតថ្មីគ្រប់គ្រាន់ មិនដូច្នេះ CPU (`-j` ច្រើន core)
- Settings → Device: auto / cpu / cuda (បង្ខំ)

## 6) ឃ្លាបាត់ពាក់កណ្ដាលវីដេអូ (Transcribe រំលងសំឡេងនិយាយ)
- `ai.find_gaps` — រកចន្លោះដែលមានសំឡេង ប៉ុន្តែគ្មានជួរអត្ថបទគ្របដណ្តប់ (≥ 2.5 វិនាទី)
- Whisper (Local): រួចពី pass ដំបូង ស្តាប់ឡើងវិញតែចន្លោះទាំងនោះ (VAD ស្រាលជាង, តម្រង no_speech/logprob ការពារ hallucination); VAD មេ threshold 0.4
- Gemini: ស្នើឲ្យ Transcribe ឡើងវិញតែចន្លោះដែលបាត់
- Source = Target (ឧ. Khmer → Khmer) ត្រូវប្តូរទៅ Auto-detect ដោយស្វ័យប្រវត្តិ (ភាសាដើមខុស ធ្វើឲ្យ Whisper រំលង/ស្តាប់ខុស)

## 7) លឿនជាងមុន + បកប្រែពេញ (round 7)
- `tts.make_clip` — ទស្សន៍ទាយល្បឿនមុនហៅ Edge TTS (តាមប្រវែងអក្សរ ÷ ពេលដែលមាន) → ហៅម្តងគត់ ជំនួសឲ្យ ២ដងលើជួរដែលត្រូវនិយាយលឿន
- `tts._decode` — បម្លែង mp3→wav ក្នុង Python (soundfile) មិនបើក ffmpeg ម្តងមួយជួរ (fallback ffmpeg)
- retry sleep ខ្លីជាងមុន; workers ស្របគ្នា 5 → 6
- `ai._bad` — បកប្រែខ្លីពេក (ធ្លាក់ឃ្លា) ត្រូវបានចាប់ ហើយបកឡើងវិញជា batch តូច

## 8) Lite model · Short · Speed · Subtitle · Stage (round 8)
- `gemini-3.5-flash-lite` ក្នុងបញ្ជី model; ប៊ូតុង **⚡ Lite** (row Auto-Fit) = បកប្រែ + shorten ដោយ Lite
- ប៊ូតុង **✂ Short** = Gemini បកខ្លី (target_chars តឹងជាង) + shorten ស្វ័យប្រវត្តិពេលសំឡេងវែងជាងវីដេអូ (ទាំង Generate Dub និង Export)
- **SPEED វីដេអូ** (0.75x–2x) លើ player: preview + Export (សំឡេង/subtitle ទៅតាម)
- Subtitle ខ្មែរ: កាត់ជាបំណែកខ្លីៗតាមពេលនិយាយ (Subtitles ▸ អក្សរអតិបរមា/ជួរ, default 28); style ថ្មី TikTok Khmer (លឿង + គែមខ្មៅ + ស្រមោល); អក្សរខ្លីរីកពេញទទឹង (≤1.35×)
- Stage (ស៊ុម/ផ្ទៃក្រោយវីដេអូ): combo លើ player; preset ថ្មី Sunset Neon, Cyber Purple, Emerald Glow, Rose Gold; ចេញក្នុង Export

## 9) បកប្រែយឺត (round 9)
- Gemini Lite បរាជ័យ → សាក model header → gemini-flash-latest → ទើប Free; បង្ហាញមូលហេតុ (⚠) ក្រោយបកចប់
- Free translate លឿនជាង: 12 workers, 30 ជួរ/request

## 10) Transcribe ដាច់ពាក់កណ្ដាល (round 10)
- `ai.fill_holes` — រកចន្លោះ ≥10 វិនាទីដែលគ្មានជួរសោះ (ទោះ BGM មិនស្ងាត់) ហើយសួរ Gemini ម្តងទៀតតែកន្លែងនោះ
- STT cache ចាំ model ផង (ប្តូរ model = transcribe ថ្មី មិនយក chunk ខូចចាស់)
- Engine "Gemini" ធម្មតា មិនប្រើ Lite សម្រាប់ transcribe ទៀត (ប្រើ gemini-3.5-flash)

## 11) បកប្រែនៅជាភាសាចិន → សំឡេងស្ងាត់ (round 11)
- `tts.render_dub` — ជួរដែលនៅជាភាសាចិន (សំឡេងខ្មែរអានមិនបាន = ស្ងាត់) ត្រូវបកប្រែដោយ Free translate មុនបង្កើតសំឡេង; បើនៅមិនបាន បង្ហាញក្នុង ⚠ ព្រមាន

## 12) សំឡេងរលូន មិនដាច់ (round 12)
- ល្បឿនអតិបរមា Hard 1.9→1.7, Soft 1.45→1.35 (លើសនេះស្តាប់ប្រញាប់/ដាច់ៗ)
- Edge ផ្ដាច់ពាក់កណ្ដាលប្រយោគវែង (ក្រោយ 4 ដង) → បង្កើតជា ២ ចំណែកតាមចន្លោះពាក្យ រួចភ្ជាប់គ្នា (`_voice_split`)
- កម្រិតសំឡេងរាល់ជួរស្មើគ្នា (`_normalize`); fade-in 12ms / fade-out 45ms ក្នុង `compose` (គ្មាន click ចុងដាច់)
- Prompt បកប្រែ: ជួរជិតគ្នាជាប្រយោគតែមួយ → បកឱ្យតភ្ជាប់ មិនចប់ប្រយោគមុនកាល មិនស្ទួន

## 13) Demucs (Mute Original / Keep Music) ដាច់ពាក់កណ្ដាល (round 13)
- `media.separate_vocals` — កាត់សំឡេងជាបំណែក 8 នាទី ធ្វើម្តងមួយបំណែក (RAM តិច) រួចភ្ជាប់; run ម្តងទៀតបន្តពីបំណែកដែលចប់
- `media.run` — កាត់របារ progress (tqdm) ចេញពី error ដើម្បីឃើញមូលហេតុពិត

## 14) Export លឿន (round 14)
- Export ប្រើ GPU encoder ស្វ័យប្រវត្តិ (NVENC → QSV → AMF; បើ GPU មិនទទួល ត្រឡប់ទៅ CPU ដោយខ្លួនឯង) — ពីមុនប្រើ CPU ជានិច្ច
- Quality default = fast (x264 superfast CRF23 / NVENC p3); ជម្រើស config.json: export_quality = turbo | fast | balanced | best, export_encoder = auto | cpu | nvenc | qsv | amf
- FFmpeg filter graph ប្រើ thread ច្រើន

## 15) Export: ល្បាក់ GPU (round 15)
- `media.encoder_chain` — សាក NVENC → QSV → AMF → CPU តាមលំដាប់ (GeForce 940M/940MX GM108 គ្មាន NVENC → ប្តូរទៅ Intel QSV ភ្លាម)
- config `export_res` (0 = ទំហំដើម, 720 = លឿនជាង)

## 16) Keep Music ភ្លាមៗ + Blur ធម្មជាតិ (round 16)
- `media.fast_bgm` — Keep Music វិនាទី (មិនប្រើ AI): លុបសំឡេង center + បន្ថយសំឡេងដើមពេល AI និយាយ; source mono → ducking តែប៉ុណ្ណោះ. Demucs នៅមាន: config `music_mode` = "ai"
- BUG Blur: export មិនដែលដាក់ plate (preview បង្ហាញ តែ export gblur ស្រាល → អក្សរចិននៅលេច). ឥឡូវ export = blur ខ្លាំងរលោង (បង្រួម ÷14 → blur → ពង្រីក) + គែមទន់ (feather mask) + plate (បើជ្រើស)
- Blur default = "Blur only" (ដូចរូប: ទិដ្ឋភាពពិតធ្វើ blur), ទទឹង 94% × 11% លើតំបន់ hard-sub; preview បង្ហាញ blur ពិតពី frame បច្ចុប្បន្ន

## 17) Export: subtitle ជាបន្ទះស្តើង (round 17)
- `build_sub_track` — PNG subtitle ជាបន្ទះ (ទទឹងពេញ × កម្ពស់តែល្មម) ជំនួសឲ្យ frame ពេញ 1080x1920 ម្តងមួយជួរ → FFmpeg scale/overlay តិចជាង ១០ដង; PNG តូចជាង បង្កើតលឿនជាង

## 18) ផ្ទាំង Dialogue — layout ៤ ជួរ អក្សរមិនដាច់ (round 18)
- `ui/flow.py` (FlowLayout ថ្មី): ប៊ូតុងរក្សាទំហំពេញអក្សរ ហើយរុំចុះជួរក្រោមពេលបង្អួចតូច (មិនត្រូវបានច្របាច់/កាត់ទៀត)
- `build_dialogue`: ជួរ 1 = ចំណងជើង + Gemini/Gemini Lite/Whisper · ជួរ 2 = ភាសា, engine, Transcribe, Translate, Auto Dub · ជួរ 3 = Add Text, Edit, Delete, Find & Replace, A−/A+, Follow · ជួរ 4 = VOICE, Male, Female, Detect Speakers, selected, Set voice, Generate, Clear

## 19) Transcribe យឺតនៅ "Fill missing speech" (round 19)
- ជំហានបំពេញចន្លោះ ពីមុនហៅ Gemini ម្តងមួយចន្លោះ (11 ដងបន្តបន្ទាប់ ហើយបើជាប់ 429 រង់ចាំ ~70 វិនាទីម្តងៗ → 960s)។ ឥឡូវរួមចន្លោះស្ងាត់ + ចន្លោះគ្មានជួរ ជាមួយគ្នា (មិនស្ទួន) ហើយហៅស្របគ្នាតែម្តង

## 20) ប្រើលើទូរស័ព្ទ (round 20)
- `web/index.html` + `GET /` ក្នុង server.py: ទំព័រវេបសម្រាប់ទូរស័ព្ទ (upload → transcribe/translate → កែអត្ថបទ → export → play/download) មិនបាច់ APK
- `auth` ទទួល `?token=` (សម្រាប់ <video>/download ក្នុង browser)
- Server export: Keep Music លឿន (fast_bgm), encoder chain + quality fast; Dockerfile copy `web/`

## 21) App ទូរស័ព្ទ (PWA) + ម៉ូដលឿន (round 21)
- `web/`: manifest + service worker + icon → ដំឡើងជា app លើអេក្រង់ដើម (Android: ប៊ូតុង ⬇ App / Chrome menu; iPhone: Share → Add to Home Screen). PWA ពេញលេញត្រូវការ HTTPS (tunnel/VPS); លើ Wi-Fi HTTP ធម្មតា ក្លាយជា shortcut
- ⚡ ម៉ូដលឿន: Gemini transcribe + បកប្រែដោយ Lite + បកខ្លី (server Form `fast`)
- server: transcribe មិនប្រើ Lite model ដោយចៃដន្យ (ប្តូរទៅ gemini-3.5-flash)

## 22) APK / iPhone (round 22)
- `.github/workflows/build-apps.yml`: build APK (Android) និង .ipa មិនទាន់ sign (iOS, ពិសោធន៍) ក្នុង GitHub Actions — មិនបាច់ដំឡើង Flutter
- `BUILD_APP.md`: ជំហានជាខ្មែរ

## 23) App Flutter: ម៉ូដលឿន ⚡ (round 23)
- `android_app/lib/api.dart` + `home.dart`: switch ⚡ ម៉ូដលឿន (ផ្ញើ `fast=1` ទៅ server) — ត្រូវការ Gemini key

## 24) Public mode — អ្នកដទៃប្រើបាន (round 24)
- server: `KD_TOKENS` (token ម្នាក់ម្ន), ម្នាក់ឃើញតែការងារខ្លួន, `KD_MAX_MB/MIN`, ជួររង់ចាំ `KD_MAX_JOBS`, `KD_PER_USER`, Gemini key server មិនចែកឱ្យអ្នកដទៃ (`KD_SHARE_KEY`)
- `deploy/PUBLIC.md` + docker-compose env

## 25) កម្មវិធី Windows ឯកសារតែមួយ (round 25)
- `.github/workflows/build-windows.yml` (PyInstaller) → `DubberKhmer-Windows.zip` (មាន FFmpeg ក្នុងខ្លួន; មិនត្រូវការ Python/server)
- `requirements-win.txt` (កំណែស្រាល គ្មាន Whisper), `run.py` (ffmpeg ក្នុងថត exe, crash log), គ្មានបង្អួចខ្មៅពេលហៅ ffmpeg (`NOWIN`), `WINDOWS_APP.md`

## 26) Workflow រកថតគម្រោងដោយខ្លួនឯង (round 26)
- build-windows.yml / build-apps.yml: រកថតដែលមាន run.py / android_app ដោយស្វ័យប្រវត្តិ (ដោះស្រាយករណីឯកសារត្រូវ upload ចូលក្នុងថតរង)

## 27) សំឡេងមិនជាន់គ្នា · លុបសំឡេងតួអង្គ · UI ស្អាតជាង (round 27)
- `tts.plan_starts` + `compose`: ជួរសំឡេង AI មិនចាប់ផ្តើមមុនជួរមុនចប់ (លែងនិយាយជាន់គ្នា); ជួរមិនទាន់ពេល → បង្កើនល្បឿនបន្ថែម ≤1.5× (កាត់ចោលតាម atempo), ជួរយឺតជាង 1.5s → ≥1.25× ដើម្បីតាមទាន់វីដេអូ
- `media.mute_voices` (Keep Music): សំឡេងដើមនៅដដែលរវាងប្រយោគ; ពេលតួអង្គនិយាយ (ពី start–end នៃជួរ) លុបសំឡេងមនុស្ស (center-cancel រក្សាតន្ត្រី/ambience; source mono → បន្ថយខ្លាំង), ramp 70ms, ដំណើរការជា block
- UI: theme engine (`ui/theme.py`) — ម៉ឺនុយ ☰ → 🎨 Theme: Neon Cyan / Violet / Rose / Emerald / Gold; polish: ព្រួញ combo, hover ក្នុង table, scrollbar ស្តើង, focus ring, menu separator

## 28) Export ចប់ → ចូល Folder ភ្លាម (round 28)
- Export វីដេអូ/SRT ចប់ → បើក Explorer/Finder ហើយ **ជ្រើសឯកសារ** ភ្លាម (មិនមានប្រអប់ OK រង់ចាំ)
- ប្រអប់ Save ចាប់ផ្តើមពីថតដែលបាន Export ចុងក្រោយ (config `export_dir`)

## 29) កែប៊ូតុង VISUALS ត្រូវច្របាច់ (round 29)
- បណ្តាលដោយ QSS `QPushButton { min-height: 20px }` ដែលរំលង `setMinimumHeight(84)` របស់ប៊ូតុង tool → ដកចេញ ហើយកំណត់ `QPushButton#tool { min-height: 84px }`; ដក `:focus` ដែលធ្វើឱ្យប៊ូតុងមើលទៅដូចត្រូវបានជ្រើស

## 30) Mute Original បិទជាដើម · Subtitle តូចបាន · UX (round 30)
- **Mute Original** ចាប់ផ្តើម "បិទ" (មិន mute) ហើយចងចាំការជ្រើស; ចុចដើម្បីបើកពេលត្រូវការ (config `mute_orig`)
- **Subtitle ទំហំ**: slider 2.0–9.0% + ប៊ូតុង តូចណាស់/តូច/មធ្យម/ធំ + preview ផ្ទាល់; switch "ពង្រីកអក្សរខ្លីឱ្យពេញទទឹង"; ទំហំដើម 4.0%
- Drag & Drop វីដេអូ/.srt ចូលបង្អួច; Ctrl+O (បើក), Ctrl+E (Export), Ctrl+Space (Play/Pause)

## 14) UI/UX + បកប្រែ/សំឡេងកាន់តែល្អ (round 14)
UI
- ស៊ុម Dialogue ធំជាងមុន (ក្រឡាតារាងមើលឃើញច្រើនជួរ): ជួរប៊ូតុងកាត់បន្ថយ, `Set voice / Generate selected / Detect Speakers` ផ្លាស់ទៅក្រោមតារាង, ជួរឈរ DUB TEXT មិនត្រូវបានច្របាច់ទៀត
- ជំហានលេខ ① Transcribe → ② Translate → ③ Generate Dub → ④ Export (+ ⚡ Auto Dub ពណ៌មាស = ចុចម្តងចប់)
- បន្ទះខាងក្រោម: ៣ ជួរស្អាត (Voice engine/Auto-Fit · Play/Progress/Generate · Sliders/Zoom) ហើយចុះបន្ទាត់ស្វ័យប្រវត្តិពេលតូច
- ស៊ុមវីដេអូ: Speed/Frame ចុះទៅជួរទី២ (ជួរឈរតូចជាងមុន ទុកកន្លែងឲ្យតារាង)
- ឈ្មោះឯកសារវីដេអូបង្ហាញលើ Header; លុប logo ស្ទួន; LED strip ស្តើងជាងមុន; ប៊ូតុង tool ទាបជាងមុន; muted text ច្បាស់ជាងមុន
- Shortcut ថ្មី: Ctrl+G = Generate Dub, Ctrl+T = Transcribe; ទំហំអប្បបរមា 1280×700
បកប្រែ / ដាក់សំឡេង
- `ai.build_glossary` — មុនបកប្រែ ស្កេន script ទាំងមូលម្តង រកឈ្មោះមនុស្ស/ទីកន្លែង/ពាក្យពិសេស ហើយកំណត់ការសរសេរខ្មែរមួយដដែល ប្រើគ្រប់ batch (ឈ្មោះមិនប្តូរពាក់កណ្ដាលវីដេអូ)
- បរិបទជុំវិញ 4 → 6 ជួរ ពេលបកប្រែ
- `tts.assign_voices` — តួអង្គ S1/S2/S3 ភេទដូចគ្នា ទទួលសំឡេង (Male 1 / Male 2 / Young Male …, Actress 1 / Mature Female …) ផ្សេងគ្នា; Seg មាន field `speaker`
- `tts.render_dub` — កាត់ប្រយោគវែង ២ ជុំ (ជុំ២ សម្រាប់ជួរដែលនៅវែងជាងពេលបន្ទាប់ពីជុំ១)

## 15) Logo ថ្មី · UI ទំនើប · LICENSE សម្រាប់ជួល (round 15)
- Logo ថ្មី (assets/logo.svg + web icons): bubble សំឡេង + រលក + ផ្កាយមាស VIP
- UI: panel/ប៊ូតុង/ក្រឡា rounded ជាងមុន, gradient ជ្រៅជាងមុន, header glow, chip ទំនើប
- LICENSE: key ចុះហត្ថលេខា Ed25519 (`core/license.py`) — ថ្ងៃផុតកំណត់, ចងជាប់កុំព្យូទ័រ (HWID) ជាជម្រើស, ការពារកែម៉ោងថយក្រោយ
  - ចាប់ផ្តើមកម្មវិធី: គ្មាន/ផុត License → ផ្ទាំង Activate; ពិនិត្យរាល់ 30 នាទី; ព្រមាន ≤7 ថ្ងៃ; chip 🔑 លើ Header (ចុចដើម្បីដូរ key)
  - កម្មវិធីមានតែ public key ប៉ុណ្ណោះ; ធ្វើ key ដោយ `LicenseAdmin/license_admin.py` (ម្ចាស់តែម្នាក់ — កុំដាក់ក្នុង zip អតិថិជន)
  - requirements: + cryptography; LICENSE.txt (លក្ខខណ្ឌប្រើប្រាស់)

## 16) Logo ម្ចាស់ · License ផ្តល់ Gemini key · Admin GUI (round 16)
- Logo "សម្រាយរឿង Movie Recap" របស់ម្ចាស់ → `assets/logo.svg/png`, web icons, `app.ico` (កាត់មូល)
- License អាចផ្ទុក Gemini key(s) (`gkey`) ដែលម្ចាស់ដាក់ឲ្យអតិថិជន — អតិថិជនមិនបាច់ដាក់ API; key មិនត្រូវបានសរសេរក្នុង config.json ហើយ Settings មិនបង្ហាញ key
- គ្មាន key សោះ: Whisper (Local) + Free translate ដំណើរការស្វ័យប្រវត្តិ (មិនបាច់ API)
