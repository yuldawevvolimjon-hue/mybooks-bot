# 🎵 Musiqa va video yuklovchi bot

- **Qo'shiq nomini yozing** (o'zbek, rus, ingliz — istalgan tilda) → bot 10 ta
  natija chiqaradi → raqamni bosing → MP3 keladi.
- **Havola yuboring** (Instagram, TikTok, YouTube, Facebook, X/Twitter,
  Pinterest, VK, Likee, Threads, SoundCloud va yt-dlp biladigan boshqa saytlar)
  → bot videoni (yoki rasmlarni) yuklab beradi. Video ostidagi
  «🎵 Musiqasini yuklash» tugmasi uning ovozini MP3 qiladi.
- Guruhga qo'shsangiz, guruhda faqat havolalarga javob beradi.

## Ishga tushirish (GitHub Actions — server kerak emas)

1. Telegram'da [@BotFather](https://t.me/BotFather) → `/newbot` → token oling.
2. GitHub: **Settings → Secrets and variables → Actions → New repository secret**
   - `MUSIQA_BOT_TOKEN` — token.
   - `MUSIQA_COOKIES` *(ixtiyoriy)* — `cookies.txt` matni, agar YouTube
     «bot emasligingizni tasdiqlang» desa yoki Instagram yopiq postlarni yuklamasa.
3. `.github/workflows/musiqa-bot.yml` **main** shoxchada bo'lishi kerak
   (jadval faqat main'da ishlaydi).
4. **Actions → Musiqa bot → Run workflow → sozlash** — buyruqlar va tavsifni o'rnatadi.
   Keyin bot har 10 daqiqalik jadval bilan o'zi ishlab turadi.

## O'z serveringizda

```bash
sudo apt install ffmpeg
pip install -r musiqa/requirements.txt
BOT_TOKEN=... python3 musiqa/bot.py
```

## Cheklovlar

- Oddiy Telegram Bot API botga **50 MB** gacha fayl yuborishga ruxsat beradi.
  Katta videolarni bot avval 720p, keyin 480p/360p da yuklashga urinadi.
  O'z [Bot API serveringiz](https://github.com/tdlib/telegram-bot-api) bo'lsa,
  `API_URL=http://localhost:8081` qo'ying — chegara 2000 MB bo'ladi.
- YouTube GitHub serverlaridan kelgan so'rovlarni ba'zan bloklaydi — shunda
  `MUSIQA_COOKIES` kerak bo'ladi (yoki qidiruv SoundCloud'ga o'tadi).
- Yopiq (private) akkauntlardagi postlarni yuklab bo'lmaydi.
