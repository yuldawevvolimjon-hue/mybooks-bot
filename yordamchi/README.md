# 🤝 Shaxsiy yordamchi bot (Telegram «Chat automation»)

Bot shaxsiy akkauntingizga ulanadi va siz band paytingizda sizga yozganlarga
siz nomingizdan javob beradi.

| Rejim | Nima qiladi |
|---|---|
| ⭐ **Aralash** *(standart)* | Siz **belgilagan** odamlarga faqat «Hozir bandman, bo'shashim bilan o'zim yozaman» boradi; **qolganlar** bilan AI suhbatlashadi |
| 🤖 **Hammaga AI** | Hammaga AI javob beradi |
| ⏰ **Hammaga avtojavob** | Hammaga faqat tayyor matn |
| ⛔ **O'chiq** | Hech narsa qilmaydi |

Avtojavob bir odamga 6 soatda bir marta yuboriladi. **Guruh, kanal va
botlarga** bot hech qachon yozmaydi — faqat odamlar bilan shaxsiy chatlarda.

Siz o'zingiz biror chatda yozsangiz, bot o'sha chatda **30 daqiqa jim turadi**
va suhbatingizga aralashmaydi.

## Ishga tushirish

1. [@BotFather](https://t.me/BotFather) → `/newbot` → token oling.
2. BotFather → `/mybots` → botingiz → **Bot Settings → Business Mode → Turn on**.
3. Claude API kaliti: https://console.anthropic.com → **API Keys** (AI suhbat uchun;
   kalitsiz faqat avtojavob ishlaydi).
4. GitHub: **Settings → Secrets and variables → Actions → New repository secret**
   - `YORDAMCHI_BOT_TOKEN` — bot tokeni
   - `ANTHROPIC_API_KEY` — Claude kaliti
5. `.github/workflows/yordamchi-bot.yml` **main** shoxchada bo'lishi kerak.
   **Actions → Yordamchi bot → Run workflow → sozlash**, keyin bot jadval bilan o'zi ishlaydi.
6. Telegram: **Settings → Chat automation** → bot username'ini yozing → chatlarni
   tanlang → **javob berish** ruxsatini yoqing.

## Sozlash (botning o'ziga yozasiz)

- `/start` — holat va rejim tugmalari
- `/matn Hozir bandman, bo'shab o'zim yozaman` — avtojavob matni
- `/haqimda Ismim Ali, dizaynerman. Logotip 300 ming so'm, 3 kunda tayyor.` —
  AI shu ma'lumotga tayanadi (bilmagan narsani o'ylab topmaydi)
- `/tozala` — AI suhbat tarixini o'chirish
- **⭐ Belgilanganlar** — pastdagi **➕ Belgilash** tugmasini bosib kontaktlaringizdan
  tanlaysiz (bir yo'la 10 tagacha). Ro'yxatdan olish: ism yonidagi `/ochir_…` ni bosing.

Kompyuterda ishga tushirish: `pip install -r requirements.txt`, keyin
`BOT_TOKEN=... ANTHROPIC_API_KEY=... python3 bot.py`.
