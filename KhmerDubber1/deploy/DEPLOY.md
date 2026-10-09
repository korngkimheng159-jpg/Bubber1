# ដាក់ server ឲ្យដំណើរការ 24/7 (មិនចាំបាច់បើកកុំព្យូទ័រ)

ត្រូវការ VPS/Server Linux មួយ (Ubuntu) ដែលមាន RAM ≥ 2 GB ហើយបើកអ៊ីនធឺណិតជានិច្ច។

## 1) ដំឡើង Docker (ម្តងគត់)
```
curl -fsSL https://get.docker.com | sh
```

## 2) ដាក់កូដ
Upload ថត KhmerDubber1 ទៅ server (scp / SFTP) រួច៖
```
cd KhmerDubber1
cp .env.example .env && nano .env      # កំណត់ KD_TOKEN (ពាក្យសម្ងាត់វែង)
docker compose up -d --build
docker compose logs -f                 # មើល log
```
Server ឡើងលើ port 8765 ហើយចាប់ផ្តើមឡើងវិញដោយខ្លួនឯងពេល server restart។

## 3) ភ្ជាប់ app
- គ្មាន domain: Settings ក្នុង app → `http://<IP server>:8765` + Token (ត្រូវបើក port 8765 ក្នុង firewall)
- មាន domain (ណែនាំ): ដកមតិយោបល់ `caddy` ក្នុង docker-compose.yml, ដាក់ `DOMAIN=...` ក្នុង .env,
  លុបផ្នែក `ports` របស់ dubber → ប្រើ `https://domain` ក្នុង app (សុវត្ថិភាពជាង)

## ចំណាំ
- គ្មាន GPU: Whisper លើ CPU យឺត។ ប្រើ size `tiny`/`base`, ឬ **STT = Gemini** (ត្រូវការ Gemini key — លឿនបំផុតលើ server ខ្សោយ)។
- សំឡេង Edge ត្រូវការ Internet ពី server; បើ Microsoft រារាំង IP របស់ server សូមប្តូរទៅ gTTS (ប្រាប់ខ្ញុំឲ្យបន្ថែមជម្រើសក្នុង app)។
- ឯកសារវីដេអូ/លទ្ធផលត្រូវលុបស្វ័យប្រវត្តិក្រោយ 24 ម៉ោង (`KD_KEEP_HOURS`)។
- កុំបើក server ទៅ Internet ដោយគ្មាន KD_TOKEN។
- ថ្លៃ/គម្រោងឥតគិតថ្លៃរបស់ VPS ផ្លាស់ប្តូរ សូមពិនិត្យនៅអ្នកផ្តល់សេវាមុនជ្រើស។
