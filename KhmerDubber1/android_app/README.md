# Dubber ខ្មែរ — Android app (Flutter)

App នេះជា **client**: ទូរស័ព្ទ Upload វីដេអូ → កែអត្ថបទ → Download វីដេអូដែលបានដាក់សំឡេង។
ការងារធ្ងន់ (Whisper / បកប្រែ / សំឡេង Edge / FFmpeg) រត់លើកុំព្យូទ័រ ដោយ `server.py` (ថតមេ)។

## 1) Server (កុំព្យូទ័រ)
```
pip install -r requirements-server.txt        # និង FFmpeg ក្នុង PATH
python server.py                              # បង្ហាញ http://<IP>:8765
# ជម្រើស: ដាក់ពាក្យសម្ងាត់  →  set KD_TOKEN=secret   (Linux/Mac: export KD_TOKEN=secret)
```
ទូរស័ព្ទ និងកុំព្យូទ័រត្រូវនៅ Wi-Fi តែមួយ។ បើ Windows Firewall សួរ សូមអនុញ្ញាត Python។
កុំបើក port នេះទៅ Internet ដោយគ្មាន `KD_TOKEN`។

## 2) បង្កើត project Flutter (ម្តងគត់)
Flutter SDK ≥ 3.22 និង Android Studio (ឬ command-line tools)។
```
flutter create --org com.khmerdubber --project-name khmer_dubber_app --platforms android my_app
cp -r android_app/lib/*  my_app/lib/
cp android_app/pubspec.yaml my_app/pubspec.yaml      # (Windows: copy ដោយដៃ)
cd my_app && flutter pub get
```

## 3) Android Manifest (ចាំបាច់ — បើមិនដូច្នេះទេ app ភ្ជាប់ server មិនបាន)
បើក `my_app/android/app/src/main/AndroidManifest.xml` ហើយ៖
1. ដាក់មុន `<application`:  `<uses-permission android:name="android.permission.INTERNET"/>`
2. ក្នុង tag `<application` បន្ថែម:  `android:usesCleartextTraffic="true"`   (server ជា http លើ Wi-Fi)

## 4) រត់ / Build APK
```
flutter run                      # ទូរស័ព្ទភ្ជាប់ USB (បើក USB debugging)
flutter build apk --release      # → build/app/outputs/flutter-apk/app-release.apk
```
ផ្ញើ APK ទៅទូរស័ព្ទ ហើយដំឡើង (អនុញ្ញាត "Install unknown apps")។

## ប្រើ
⚙ Settings → ដាក់ URL server (ឧ. `http://192.168.1.5:8765`) → "សាកល្បងការភ្ជាប់" →
ជ្រើសវីដេអូ → ⚡ Transcribe + Translate → កែអត្ថបទ (ប្តូរ ប្រុស/ស្រី បាន) → 🔊 បង្កើតសំឡេង + Export → Share/Save។

## Google Colab (ជំនួសកុំព្យូទ័រ)
រត់ `server.py` ក្នុង Colab (GPU) ហើយបើក tunnel (cloudflared/ngrok) ដាក់ URL https ក្នុង Settings។
ត្រូវកំណត់ `KD_TOKEN` ជានិច្ច ពេលប្រើ tunnel។ (ជាមួយ https មិនចាំបាច់ usesCleartextTraffic ទេ)
