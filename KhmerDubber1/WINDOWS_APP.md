# Dubber ខ្មែរ — កម្មវិធី Windows (មិនបាច់ server / មិនបាច់ដំឡើង Python)

## សម្រាប់អ្នកប្រើ
1. Unzip `DubberKhmer-Windows.zip` (ដាក់ក្នុងថតណាក៏បាន ឧ. `C:\DubberKhmer`)។
2. ចុចពីរដង `DubberKhmer.exe`។
   - Windows SmartScreen អាចព្រមាន ("Windows protected your PC") → ចុច **More info** → **Run anyway** (កម្មវិធីមិនទាន់ sign)។
   - Antivirus ខ្លះអាចសន្មតថាគួរឱ្យសង្ស័យ (កម្មវិធី pack ដោយ PyInstaller) — អ្នកអាចអនុញ្ញាតបាន។
3. ចុច ⚙ Settings ដាក់ **Gemini API Key** (ឥតគិតថ្លៃ: aistudio.google.com/apikey)។
   កំណែនេះជាកំណែស្រាល (គ្មាន Whisper) ដូច្នេះការស្តាប់សំឡេងប្រើ Gemini (ត្រូវការ Internet)។
4. បើកវីដេអូ → Transcribe → Translate → Generate Dub → Export។

## កំណែស្រាល ខុសអ្វី
- គ្មាន Whisper (offline) និង Demucs (ដកសំឡេងដោយ AI) — Keep Music ប្រើវិធីលឿន (ក្នុង FFmpeg)។
- ត្រូវការ Internet សម្រាប់ Gemini, Free translate និងសំឡេង Edge។

## សម្រាប់អ្នកបង្កើត (build)
GitHub → Actions → **Build Windows app** → Run workflow → ទាញយក `DubberKhmer-Windows.zip` ក្រោម Artifacts។
ចង់ឱ្យមានតំណសាធារណៈ: បង្កើត tag `v1.0` (Releases → Draft a new release) → ឯកសារត្រូវភ្ជាប់ដោយស្វ័យប្រវត្តិ (repo ត្រូវ Public)។
FFmpeg ដែលភ្ជាប់មកជា build GPL — រក្សាសេចក្តីជូនដំណឹង license របស់វា។
