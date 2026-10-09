# ធ្វើ app ទូរស័ព្ទ (APK / iPhone) — មិនបាច់ដំឡើង Flutter ក្នុងកុំព្យូទ័រ

## Android APK (build ក្នុង cloud ឥតគិតថ្លៃ)
1. បង្កើត account ឥតគិតថ្លៃលើ github.com → New repository (Private ក៏បាន)។
2. Upload ឯកសារទាំងអស់ក្នុងថត KhmerDubber (រួមទាំងថត `.github` និង `android_app`) ទៅ repo នោះ។
3. ផ្ទាំង **Actions** → **Build apps** → **Run workflow**។
4. រង់ចាំប្រហែល 5–10 នាទី → ចុច run នោះ → ក្រោម **Artifacts** ទាញយក `Dubber-khmer-android-apk` (zip មាន app-release.apk)។
5. ផ្ញើ APK ទៅទូរស័ព្ទ → ដំឡើង (អនុញ្ញាត "Install unknown apps")។
6. បើក app → ⚙ Settings → ដាក់ URL server (`http://192.168.x.x:8765` ឬ https tunnel) + Token → ប្រើ។

## iPhone
- **ងាយបំផុត (មិនបាច់ app store):** បើក URL server ក្នុង Safari → Share → **Add to Home Screen** (ត្រូវការ HTTPS សម្រាប់ app ពេញលេញ)។
- **app ពិត (.ipa):** Actions → Build apps → Run workflow (job `ios`, ពិសោធន៍) → ទាញយក `.ipa` មិនទាន់ sign →
  sign ដោយ Sideloadly/AltStore (Apple ID ឥតគិតថ្លៃ: ផុត 7 ថ្ងៃ ត្រូវ sign ឡើងវិញ) ឬ Apple Developer Program ($99/ឆ្នាំ) សម្រាប់ដាក់យូរ/TestFlight។
- macOS runner របស់ GitHub ឥតគិតថ្លៃសម្រាប់ repo ដែល **Public** ប៉ុណ្ណោះ (Private ស៊ីម៉ោង quota លឿន)។
