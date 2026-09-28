#!/usr/bin/env python3
"""
Musiqa va video yuklovchi Telegram bot.

Vazifasi:
  1. Musiqa qidirish: foydalanuvchi qo'shiq nomini (yoki ijrochini) yozadi —
     o'zbekcha, ruscha, inglizcha, istalgan tilda. Bot YouTube'dan (topilmasa
     SoundCloud'dan) 10 ta natija chiqaradi, raqamni bosganda MP3 yuboradi.
  2. Havola bo'yicha yuklash: istalgan ijtimoiy tarmoq havolasini yuborsa
     (Instagram, TikTok, YouTube, Facebook, X/Twitter, Pinterest, VK,
     Likee, Threads, SoundCloud va yt-dlp biladigan 1000 dan ortiq sayt),
     bot undagi video/rasm/audioni yuklab beradi. Video ostida
     «🎵 Musiqasini yuklash» tugmasi — o'sha videoning audiosini MP3 qiladi.

Yuklash yt-dlp orqali, MP3 ga aylantirish ffmpeg orqali. Bir marta yuklangan
narsa Telegram'da saqlanadi (file_id) — qayta so'ralsa, darhol yuboriladi.

Rejimlar:
    python3 bot.py                 # doimiy (server bo'lsa): long polling
    python3 bot.py --uzluksiz 50   # GitHub Actions: 50 daqiqa ishlaydi
    python3 bot.py --setup         # buyruqlar va tavsifni o'rnatadi

Muhit o'zgaruvchilari:
    BOT_TOKEN      BotFather bergan token
    STATE_FILE     musiqa.json manzili (ixtiyoriy) — kesh va foydalanuvchilar
    COOKIES_FILE   cookies.txt (ixtiyoriy) — YouTube «bot emasligingizni
                   tasdiqlang» desa yoki Instagram yopiq bo'lsa kerak bo'ladi
    API_URL        o'z Bot API serveringiz bo'lsa (masalan http://localhost:8081),
                   fayl chegarasi 50 MB o'rniga 2000 MB bo'ladi
    MAX_MB         yuboriladigan faylning eng katta hajmi (standart 50)
    ISHCHILAR      bir vaqtda nechta yuklash (standart 6)
"""

import copy
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import yt_dlp
except ImportError:              # --help yoki testlar uchun; ishga tushishda tekshiramiz
    yt_dlp = None

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
STORE = os.environ.get("STATE_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "musiqa.json")
COOKIES = os.environ.get("COOKIES_FILE", "").strip()
API_URL = (os.environ.get("API_URL") or "https://api.telegram.org").rstrip("/")
API = "%s/bot%s/" % (API_URL, TOKEN)
MAX_MB = int(os.environ.get("MAX_MB") or (2000 if "api.telegram.org" not in API_URL else 50))
MAX_BAYT = MAX_MB * 1024 * 1024
ISHCHILAR = int(os.environ.get("ISHCHILAR") or 6)

# Majburiy obuna. Telegram kanallarni bot o'zi tekshiradi — buning uchun bot
# har bir kanalda ADMIN bo'lishi kerak. TikTok va Instagram obunani hech kimga
# ko'rsatmaydi: ular uchun tugma chiqadi, «Obuna bo'ldim» bosilgach ishonamiz.
KANALLAR = [x.strip() for x in (os.environ.get("KANALLAR")
            or "@AI_VIDEOLA_VARASIMLA,@music_uz0007").split(",") if x.strip()]
TIKTOK = os.environ.get("TIKTOK", "https://www.tiktok.com/@yuldawev.olimjon0007").strip()
INSTAGRAM = os.environ.get("INSTAGRAM", "https://www.instagram.com/____0007y.o").strip()
BOTPIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rasmlar", "botpic.png")
MAXFIYLIK_URL = os.environ.get("MAXFIYLIK_URL") or \
    "https://yuldawevvolimjon-hue.github.io/mybooks-bot/musiqa-maxfiylik.html"
MAXFIYLIK = ("🔒 <b>Maxfiylik siyosati</b>\n\n"
             "• Faqat Telegram ID va ismingiz saqlanadi.\n"
             "• Qidiruvlar, havolalar va yuklangan fayllar saqlanmaydi.\n"
             "• Ma'lumotlaringiz hech kimga berilmaydi.\n\n"
             "📄 To'liq matn: %s" % MAXFIYLIK_URL)
SALOM_RASM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rasmlar", "tavsif.png")
_DB = None                 # main() da o'rnatiladi — rasm file_id keshi uchun
OBUNA_KESH = 10 * 60       # kanalga obuna tekshiruvi natijasi shuncha soniya eslab qolinadi

NATIJA_SONI = 10           # qidiruvda nechta qo'shiq ko'rsatiladi
ENG_UZUN = 20 * 60         # qidiruvda 20 daqiqadan uzun videolar (mikslar) chiqmasin
ALBOM = 10                 # bitta havoladan ko'pi bilan nechta fayl (Instagram karusel)

SALOM = (
    "👋 Assalomu alaykum, <b>%s</b>!\n\n"
    "Men — <b>%s</b> 🎧\n"
    "Istalgan qo'shiqni topaman va ijtimoiy tarmoqlardan video yuklab beraman.\n\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🎵 <b>Qo'shiq topish</b>\n"
    "Qo'shiq yoki ijrochi nomini yozing — o'zbekcha, ruscha, inglizcha...\n"
    "<i>Masalan:</i> <code>Shahzoda Yuragim</code>\n"
    "<i>Masalan:</i> <code>Макс Корж Мотылёк</code>\n\n"
    "📥 <b>Video yuklash</b>\n"
    "Havolani yuboring — videoni yuklab beraman, xohlasangiz musiqasini ham.\n"
    "━━━━━━━━━━━━━━━━━━\n\n"
    "✨ Qani, boshladik — qo'shiq nomini yozing 👇"
)
YORDAM = (
    "📖 <b>Qanday foydalaniladi?</b>\n\n"
    "<b>1️⃣ Qo'shiq topish</b>\n"
    "Qo'shiq nomini yozing → ro'yxatdan raqamni bosing → 🎧 MP3 keladi.\n"
    "💡 <i>Ijrochi + qo'shiq nomi yozilsa, aniqroq topiladi.</i>\n\n"
    "<b>2️⃣ Video yuklash</b>\n"
    "Havolani nusxalab, shu yerga yuboring → 🎬 video keladi.\n"
    "Video ostidagi <b>«🎵 Musiqasini yuklash»</b> tugmasi uning ovozini MP3 qiladi.\n\n"
    "<b>🌐 Qo'llab-quvvatlanadigan tarmoqlar:</b>\n"
    "📸 Instagram  •  🎵 TikTok  •  ▶️ YouTube\n"
    "📘 Facebook  •  ✖️ X (Twitter)  •  📌 Pinterest\n"
    "💬 VK  •  🧵 Threads  •  ☁️ SoundCloud  •  va boshqalar\n\n"
    "<b>👥 Guruhda ham ishlaydi</b> — meni guruhga qo'shing, "
    "havola tashlansa, videoni o'zim yuklab beraman."
)
TAVSIF = ("🎧 Navo Music — istalgan qo'shiq bir zumda!\n\n"
          "🎵 Qo'shiq nomini yozing — o'zbek, rus, ingliz va boshqa tillarda "
          "MP3 qilib yuboraman.\n\n"
          "📥 Instagram, TikTok, YouTube, Facebook havolasini yuboring — "
          "videoni yuklab beraman.\n\n"
          "⚡ Tez, bepul va qulay.\n\n"
          "👇 START tugmasini bosing!")
QISQA_TAVSIF = "🎧 Qo'shiq topish va Instagram, TikTok, YouTube'dan video yuklash"
RAQAM = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

URL_RE = re.compile(r"https?://[^\s<>\"']+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}/[^\s<>\"']*",
                    re.I)
YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YT_URL_RE = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)"
                       r"([A-Za-z0-9_-]{11})")
RASM = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
AUDIO = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"}
KERAKSIZ = {".part", ".ytdl", ".json", ".vtt", ".srt", ".description"}

_db_lock = threading.Lock()
_band = set()              # hozir yuklayotgan foydalanuvchilar (bittadan)
_band_lock = threading.Lock()
# Qisqa kalit → ma'lumot. callback_data 64 baytdan oshmasligi kerak, shuning
# uchun uzun havolalarni shu yerda saqlaymiz. Bot qayta ishga tushsa, eskiradi.
_xotira = {}


# ---------------------------------------------------------------- Telegram API
def call(method, **params):
    data = urlencode({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                      for k, v in params.items() if v is not None}).encode()
    return _yubor(Request(API + method, data=data), method)


def _yubor(req, method, timeout=70):
    try:
        with urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except HTTPError as e:
        try:
            body = json.load(e)
        except ValueError:
            body = {"description": str(e)}
        print("telegram xatosi:", method, body.get("description"), file=sys.stderr)
        return {"ok": False, **body}
    except (URLError, OSError) as e:
        print("tarmoq xatosi:", method, e, file=sys.stderr)
        return {"ok": False}


def multipart(fields, files):
    """multipart/form-data tanasi: fields — oddiy qiymatlar, files — {nom: yo'l}."""
    chegara = "----musiqa" + uuid.uuid4().hex
    qism = []
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        qism.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                     % (chegara, k, v)).encode())
    for k, yol in files.items():
        nom = os.path.basename(yol).replace('"', "'")
        tur = mimetypes.guess_type(yol)[0] or "application/octet-stream"
        qism.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                     'Content-Type: %s\r\n\r\n' % (chegara, k, nom, tur)).encode())
        with open(yol, "rb") as f:
            qism.append(f.read())
        qism.append(b"\r\n")
    qism.append(("--%s--\r\n" % chegara).encode())
    return b"".join(qism), "multipart/form-data; boundary=" + chegara


def upload(method, fields, files):
    body, tur = multipart(fields, files)
    req = Request(API + method, data=body, headers={"Content-Type": tur})
    return _yubor(req, method, timeout=600)


def send(chat_id, text, keyboard=None, reply_to=None):
    return call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                disable_web_page_preview="true", reply_markup=keyboard,
                reply_to_message_id=reply_to, allow_sending_without_reply="true")


def edit(chat_id, message_id, text, keyboard=None):
    return call("editMessageText", chat_id=chat_id, message_id=message_id, text=text,
                parse_mode="HTML", disable_web_page_preview="true", reply_markup=keyboard)


def inline(rows):
    """Tugmalar: (matn, callback_data) yoki (matn, "https://...") — havola tugmasi."""
    return {"inline_keyboard": [[{"text": t, "url": d} if d.startswith("https://")
                                 else {"text": t, "callback_data": d} for t, d in row]
                                for row in rows]}


# ---------------------------------------------------------------- saqlash
def load():
    try:
        with open(STORE, encoding="utf-8") as f:
            db = json.load(f)
    except (OSError, ValueError):
        db = {}
    db.setdefault("kesh", {})       # "audio:youtube:ID" → Telegram file_id
    db.setdefault("users", {})      # chat_id → {"ism", "birinchi", "soni"}
    return db


def save(db):
    with _db_lock:
        data = json.dumps(db, ensure_ascii=False)
    os.makedirs(os.path.dirname(os.path.abspath(STORE)), exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, STORE)


def kesh_ol(db, kalit):
    with _db_lock:
        return db["kesh"].get(kalit)


def kesh_yoz(db, kalit, qiymat):
    with _db_lock:
        db["kesh"][kalit] = qiymat


# ---------------------------------------------------------------- yordamchilar
def havola_top(text):
    m = URL_RE.search(text or "")
    if not m:
        return None
    url = m.group(0).rstrip(").,!?»")
    if not url.lower().startswith("http"):
        url = "https://" + url
    return url


def vaqt(soniya):
    if not soniya:
        return ""
    soniya = int(soniya)
    s, m = divmod(soniya, 3600)
    m, sek = divmod(m, 60)
    return "%d:%02d:%02d" % (s, m, sek) if s else "%d:%02d" % (m, sek)


def kalit_saqla(qiymat):
    k = secrets.token_urlsafe(6)
    _xotira[k] = qiymat
    return k


def band_qil(kalit):
    with _band_lock:
        if kalit in _band:
            return False
        _band.add(kalit)
        return True


def boshat(kalit):
    with _band_lock:
        _band.discard(kalit)


def ydl_sozlama(papka, **qoshimcha):
    o = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 30,
        "retries": 3,
        "concurrent_fragment_downloads": 8,     # HLS/DASH bo'laklarini parallel yuklash
        "http_chunk_size": 10 * 1024 * 1024,
        "outtmpl": os.path.join(papka, "%(title).80B [%(id)s].%(ext)s"),
        "restrictfilenames": False,
        "windowsfilenames": True,
        "noplaylist": True,
        "max_filesize": MAX_BAYT,
        "http_headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"},
    }
    if COOKIES and os.path.exists(COOKIES):
        o["cookiefile"] = COOKIES
    o.update(qoshimcha)
    return o


def xato_matn(e):
    s = str(e)
    if "Sign in to confirm" in s or "not a bot" in s:
        return ("😔 Bu qo'shiqni YouTube hozir bermayapti, boshqa manbalarda ham topilmadi.\n"
                "💡 Ro'yxatdan boshqa variantini tanlang yoki nomini boshqacha yozing.")
    if "login" in s.lower() or "private" in s.lower() or "cookies" in s.lower():
        return "🔒 Bu post yopiq (private) yoki kirishni talab qiladi — yuklab bo'lmadi."
    if "Unsupported URL" in s:
        return "Bu havolani qo'llab-quvvatlamayman 😔"
    if "File is larger" in s or "max_filesize" in s:
        return "📦 Fayl juda katta (%d MB dan ortiq) — Telegram orqali yubora olmayman." % MAX_MB
    if "Video unavailable" in s or "removed" in s.lower() or "404" in s:
        return "😔 Video topilmadi yoki o'chirilgan."
    return "Yuklab bo'lmadi 😔 Havolani tekshirib, qayta urinib ko'ring."


# ---------------------------------------------------------------- qidiruv
_qidiruv_kesh = {}         # so'z → (vaqt, natijalar): bir xil so'rov darhol chiqadi
QIDIRUV_KESH_VAQT = 6 * 3600


def qidir(soz):
    """YouTube'dan, bo'lmasa SoundCloud'dan qo'shiqlar ro'yxati (keshlangan)."""
    k = " ".join(soz.lower().split())
    eski = _qidiruv_kesh.get(k)
    if eski and time.time() - eski[0] < QIDIRUV_KESH_VAQT:
        return eski[1]
    natija = _qidir(soz)
    if natija:
        if len(_qidiruv_kesh) > 5000:
            _qidiruv_kesh.clear()
        _qidiruv_kesh[k] = (time.time(), natija)
    return natija


UZBEKCHA_ULUSH = 7          # 10 ta natijadan nechtasi o'zbekcha bo'lsin (70%)
_UZ_HARF = re.compile(r"[ўқғҳЎҚҒҲ]|\b(?:o|g)['‘’ʻʼ`]", re.I)
_UZ_SOZ = re.compile(
    r"\b(?:uzbek\w*|o['‘’ʻʼ`]?zbek\w*|ozbek\w*|uzb|qo['‘’ʻʼ`]?shi\w*|yangi|klip|jonli|ijro\w*|"
    r"konsert\w*|xit|tarona\w*|sevgi\w*|onajon\w*|yor\w*|yurag\w*|muhabbat\w*|jonim|"
    r"sevaman|ketma|kelgin|kechir\w*|dunyo\w*|hayot\w*|bahor\w*|uzbekistan|toshkent\w*|"
    r"sevimli|milliy|zo['‘’ʻʼ`]?r ?tv|yoshlar|musiqa\w*|ashula\w*|qizlar|bolalar|"
    r"юраг\w*|севги\w*|узбек\w*|янги|клип|жонли|онажон\w*|муҳаббат\w*|ёр\w*)\b", re.I)
# Mashhur o'zbek xonandalari — nomida shular bo'lsa ham o'zbekcha deb hisoblanadi.
_UZ_IJROCHI = re.compile(
    r"\b(?:shahzoda|sevara|yulduz|ozoda|lola|rayhon|rayxon|jaloliddin|ulug['‘’ʻʼ`]?bek|"
    r"shohruhxon|shoxruxxon|konsta|ummon|bojalar|xamdam|hamdam|sardor|jasur umirov|munisa|"
    r"dilsoz|farrux|sherali|ziyoda|manzura|shaxriyor|shahriyor|lobar|benom|xurshid|alisher|"
    r"muxlisa|nigina|diyor|asilbek|bahrom|doston|mohirbek|ozodbek|nasiba|nilufar|"
    r"gulsanam|dildora|kumush|zarina|madina|mirjalol|rustam|ruhshona|shabnam|surayyo|xamid|"
    r"yunus|g['‘’ʻʼ`]?ayrat|abdulla|ortiqov|jahongir|javlon|izzat|fayz|shoira|umid|otabek|"
    r"xushnud|mehriniso|feruza|dilnoza|sanjar|zafar|shaxzoda|sevinch|nigora|oybek)\b", re.I)
_RUS_HARF = re.compile(r"[ыэщъЫЭЩЪ]")


def uzbekchami(r):
    """Natija o'zbekcha qo'shiqqa o'xshaydimi (nomi yoki kanali bo'yicha)."""
    matn = "%s %s" % (r["nom"], r["ijrochi"])
    return bool(_UZ_HARF.search(matn) or _UZ_SOZ.search(matn) or _UZ_IJROCHI.search(matn))


def _yt_qidir(soz, soni):
    """Bitta manbadan qidiruv: YouTube, bo'lmasa SoundCloud."""
    for manba, prefiks in (("youtube", "ytsearch%d:" % soni),
                           ("soundcloud", "scsearch%d:" % NATIJA_SONI)):
        try:
            with yt_dlp.YoutubeDL(ydl_sozlama(tempfile.gettempdir(), extract_flat=True,
                                              skip_download=True)) as y:
                info = y.extract_info(prefiks + soz, download=False)
        except Exception as e:
            print("qidiruv xatosi:", manba, repr(e)[:300], file=sys.stderr)
            continue
        natija = []
        for e in info.get("entries") or []:
            if not e:
                continue
            dur = e.get("duration") or 0
            if dur and dur > ENG_UZUN:
                continue
            if e.get("live_status") in ("is_live", "is_upcoming"):
                continue
            url = e.get("url") or e.get("webpage_url")
            if manba == "youtube" and e.get("id"):
                url = "https://www.youtube.com/watch?v=" + e["id"]
            if not url:
                continue
            natija.append({"id": e.get("id"), "manba": manba, "url": url,
                           "nom": e.get("title") or "Nomsiz",
                           "ijrochi": e.get("uploader") or e.get("channel") or "",
                           "vaqt": dur})
        if natija:
            return natija
    return []


def _qidir(soz):
    """Ko'pchilik o'zbekcha qo'shiq qidiradi: natijalarning ~70% i o'zbekcha bo'ladi.

    Ikki qidiruv parallel: so'zning o'zi va «so'z + uzbek». O'zbekcha natijalar
    (so'rovdagi so'zlardan biri nomida bo'lsa) oldinga chiqadi, qolgan joylar
    asl qidiruv natijalari bilan to'ldiriladi. Ruscha so'rovga tegmaymiz.
    """
    if _RUS_HARF.search(soz) or re.search(r"\buzbek|o['‘’ʻʼ`]?zbek", soz, re.I):
        return _yt_qidir(soz, NATIJA_SONI + 5)[:NATIJA_SONI]
    with ThreadPoolExecutor(max_workers=2) as p:
        asl_f = p.submit(_yt_qidir, soz, NATIJA_SONI + 5)
        uz_f = p.submit(_yt_qidir, soz + " uzbek", NATIJA_SONI + 5)
        asl, uz = asl_f.result(), uz_f.result()
    sozlar = [w for w in re.findall(r"\w{3,}", soz.lower())]

    def mos(r):                                   # so'rovga aloqasi bormi
        matn = ("%s %s" % (r["nom"], r["ijrochi"])).lower()
        return not sozlar or any(w in matn for w in sozlar)

    natija, bor = [], set()

    def qosh(r):
        k = r["id"] or r["url"]
        if k not in bor and len(natija) < NATIJA_SONI:
            bor.add(k)
            natija.append(r)

    # Asl qidiruvning birinchisi — eng aniq javob, doim birinchi turadi.
    if asl:
        qosh(asl[0])
    for r in [x for x in asl + uz if uzbekchami(x) and mos(x)]:
        if len(natija) >= UZBEKCHA_ULUSH:
            break
        qosh(r)
    for r in asl + uz:                            # qolgan joylar — asl natijalar
        qosh(r)
    return natija


def qidiruv_xabar(chat, soz, reply_to):
    xabar = send(chat, "🔎 Qidiryapman: <b>%s</b>\n⏳ Bir soniya..." % escape(soz),
                 reply_to=reply_to)
    mid = xabar.get("result", {}).get("message_id")
    natija = qidir(soz)
    if not natija:
        matn = ("😔 <b>%s</b> bo'yicha hech narsa topilmadi.\n\n"
                "💡 Nomini boshqacha yozib ko'ring — masalan, ijrochi va qo'shiq nomini "
                "birga yozing." % escape(soz))
        return edit(chat, mid, matn) if mid else send(chat, matn)
    qatorlar = ["🔎 <b>%s</b>\n🎶 Topildi: %d ta qo'shiq\n" % (escape(soz), len(natija))]
    tugmalar = []
    for i, r in enumerate(natija, 1):
        qatorlar.append("%s %s%s" % (
            RAQAM[i - 1], escape(r["nom"][:80]),
            (" <i>· %s</i>" % vaqt(r["vaqt"])) if r["vaqt"] else ""))
        if r["manba"] == "youtube" and r["id"] and YT_ID_RE.match(r["id"]):
            data = "y:" + r["id"]                 # qayta ishga tushsa ham ishlaydi
            _nomlar[r["id"]] = (r["nom"], r["vaqt"])
        else:
            data = "u:" + kalit_saqla(r["url"])
        tugmalar.append((str(i), data))
    qatorlar.append("\n👇 <b>Kerakli raqamni bosing</b> — MP3 qilib yuboraman")
    kb = inline([q for q in (tugmalar[:5], tugmalar[5:10]) if q] + [[("❌ Yopish", "x")]])
    matn = "\n".join(qatorlar)
    return edit(chat, mid, matn, kb) if mid else send(chat, matn, kb)


# ---------------------------------------------------------------- yuklash
def fayllar(papka):
    out = []
    for nom in sorted(os.listdir(papka)):
        yol = os.path.join(papka, nom)
        if os.path.isfile(yol) and os.path.splitext(nom)[1].lower() not in KERAKSIZ:
            out.append(yol)
    return out


# YouTube server (GitHub) manzillaridan kelgan so'rovlarni ba'zan «bot» deb to'sadi.
# Unda boshqa «ilova» nomidan kirib ko'ramiz; ishlagani eslab qolinadi.
YT_MIJOZLAR = [None, ["tv_simply"], ["web_embedded"], ["android_vr"], ["mweb"], ["tv"]]
_yaxshi_mijoz = [None]
_nomlar = {}               # YouTube ID → (nomi, davomiyligi) — qidiruv natijalaridan


def yt_tosildi(e):
    s = str(e)
    return any(x in s for x in ("Sign in to confirm", "not a bot", "HTTP Error 403",
                                "Requested format is not available", "po_token",
                                "This content isn't available", "Precondition check failed"))


def mijoz_sozlama(mijoz):
    return {"extractor_args": {"youtube": {"player_client": mijoz}}} if mijoz else {}


def yt_bilan(url, ish):
    """ish(qoshimcha_sozlama) ni avval ishlagan, keyin boshqa YouTube mijozlari bilan sinaydi."""
    if not YT_URL_RE.search(url):
        return ish({})
    tartib = _yaxshi_mijoz[:1] + [m for m in YT_MIJOZLAR if m != _yaxshi_mijoz[0]]
    oxirgi = None
    for mijoz in tartib:
        try:
            natija = ish(mijoz_sozlama(mijoz))
            _yaxshi_mijoz[0] = mijoz
            return natija
        except Exception as e:
            if not yt_tosildi(e):
                raise
            print("youtube to'sdi (%s): %s" % (mijoz or "odatiy", str(e)[:150]), file=sys.stderr)
            oxirgi = e
    raise oxirgi


def yt_nomi(url):
    """YouTube videosi nomi: qidiruvdan eslab qolingan yoki oEmbed orqali (to'silmaydi)."""
    m = YT_URL_RE.search(url)
    if m and m.group(1) in _nomlar:
        return _nomlar[m.group(1)]
    try:
        with urlopen("https://www.youtube.com/oembed?format=json&url=" +
                     "https://www.youtube.com/watch?v=%s" % (m.group(1) if m else ""),
                     timeout=10) as f:
            return (json.load(f).get("title"), 0)
    except Exception:
        return (None, 0)


def zaxira_top(nom, dur):
    """YouTube bermasa — shu qo'shiqni SoundCloud'dan qidiramiz."""
    toza = re.sub(r"[\(\[][^\)\]]*(official|video|clip|klip|audio|lyric|music|hd|4k|"
                  r"premyera|premiere)[^\)\]]*[\)\]]", "", nom, flags=re.I)
    toza = re.sub(r"\s+", " ", toza.replace("|", " ")).strip() or nom
    try:
        with yt_dlp.YoutubeDL(ydl_sozlama(tempfile.gettempdir(), extract_flat=True,
                                          skip_download=True)) as y:
            info = y.extract_info("scsearch5:" + toza, download=False)
    except Exception as e:
        print("soundcloud zaxira xatosi:", repr(e)[:200], file=sys.stderr)
        return None
    natija = [e for e in info.get("entries") or [] if e and (e.get("url") or e.get("webpage_url"))]
    if dur:                                        # davomiyligi yaqinini afzal ko'ramiz
        yaqin = [e for e in natija if e.get("duration") and abs(e["duration"] - dur) <= 20]
        natija = yaqin or natija
    return (natija[0].get("webpage_url") or natija[0].get("url")) if natija else None


def audio_yukla(chat, url, db, reply_to=None):
    """Havoladagi (YouTube, SoundCloud, TikTok...) ovozni MP3 qilib yuboradi.

    YouTube to'sib qo'ysa — boshqa mijoz bilan, u ham bo'lmasa SoundCloud'dan.
    """
    call("sendChatAction", chat_id=chat, action="upload_voice")
    # YouTube qo'shig'i avval yuklangan bo'lsa — hech narsa yuklamasdan, darhol.
    m = YT_URL_RE.search(url)
    if m and kesh_audio(chat, db, "audio:Youtube:" + m.group(1), reply_to):
        return None
    try:
        return yt_bilan(url, lambda q: _audio(chat, url, db, reply_to, q))
    except Exception as e:
        if not (m and yt_tosildi(e)):
            raise
        nom, dur = yt_nomi(url)
        zaxira = zaxira_top(nom, dur) if nom else None
        if not zaxira:
            raise
        print("zaxira: SoundCloud dan olinmoqda:", nom, file=sys.stderr)
        return _audio(chat, zaxira, db, reply_to, {}, "audio:Youtube:" + m.group(1))


def _audio(chat, url, db, reply_to, qosh, yt_kalit=None):
    papka = tempfile.mkdtemp(prefix="musiqa-")
    try:
        with yt_dlp.YoutubeDL(ydl_sozlama(papka, skip_download=True, **qosh)) as y:
            info = y.extract_info(url, download=False)
        if info.get("_type") == "playlist":
            info = next((e for e in info.get("entries") or [] if e), None)
            if not info:
                return send(chat, "Bu havolada audio topilmadi.", reply_to=reply_to)
        kalit = "audio:%s:%s" % (info.get("extractor_key", "?"), info.get("id"))
        if kesh_audio(chat, db, kalit, reply_to):
            return None
        # M4A ni Telegram o'zi ijro etadi — qayta kodlamaymiz (tezroq).
        # Boshqa format (webm/opus) bo'lsa, MP3 ga aylantiramiz.
        sozlama = ydl_sozlama(papka, format="bestaudio[ext=m4a]/bestaudio/best", postprocessors=[
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192",
             "nopostoverwrites": False}], **qosh)
        if any(f.get("ext") == "m4a" and f.get("vcodec") == "none"
               for f in info.get("formats") or []):
            sozlama["postprocessors"] = []
        with yt_dlp.YoutubeDL(sozlama) as y:
            info = y.process_ie_result(info, download=True)   # qayta ochmaymiz
        mp3 = [f for f in fayllar(papka) if f.lower().endswith((".mp3", ".m4a"))]
        if not mp3:
            return send(chat, "Audioni ajratib bo'lmadi 😔", reply_to=reply_to)
        if os.path.getsize(mp3[0]) > MAX_BAYT:
            return send(chat, "Fayl juda katta (%d MB dan ortiq)." % MAX_MB, reply_to=reply_to)
        nom = info.get("track") or info.get("title") or "audio"
        ijrochi = info.get("artist") or info.get("creator") or info.get("uploader") or ""
        fields = {"chat_id": chat, "title": nom[:64], "performer": ijrochi[:64],
                  "duration": int(info.get("duration") or 0) or None,
                  "caption": imzo(), "parse_mode": "HTML",
                  "reply_to_message_id": reply_to, "allow_sending_without_reply": "true"}
        files = {"audio": mp3[0]}
        rasm = muqova(info, papka)
        if rasm:
            files["thumbnail"] = rasm
        call("sendChatAction", chat_id=chat, action="upload_voice")
        r = upload("sendAudio", fields, files)
        fid = (r.get("result") or {}).get("audio", {}).get("file_id")
        if fid:
            kesh_yoz(db, kalit, fid)
            if yt_kalit:                           # keyingi safar YouTube tugmasidan ham darhol
                kesh_yoz(db, yt_kalit, fid)
        elif not r.get("ok"):
            send(chat, "Telegram'ga yuborib bo'lmadi 😔", reply_to=reply_to)
        return r
    finally:
        shutil.rmtree(papka, ignore_errors=True)


def kesh_audio(chat, db, kalit, reply_to):
    eski = kesh_ol(db, kalit)
    if not eski:
        return False
    r = call("sendAudio", chat_id=chat, audio=eski, reply_to_message_id=reply_to,
             allow_sending_without_reply="true", caption=imzo(), parse_mode="HTML")
    return bool(r.get("ok"))


def muqova(info, papka):
    """Audio uchun kichik muqova (Telegram: JPEG, 320 px gacha, 200 KB gacha)."""
    url = info.get("thumbnail")
    if not url:
        return None
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=5) as r:
            data = r.read(2_000_000)
    except Exception:
        return None
    asl = os.path.join(papka, "muqova_asl")
    yol = os.path.join(papka, "muqova.jpg")
    with open(asl, "wb") as f:
        f.write(data)
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", asl, "-vf",
                        "scale=320:320:force_original_aspect_ratio=increase,crop=320:320",
                        "-q:v", "5", yol], timeout=60, check=False)
    os.remove(asl)
    if os.path.exists(yol) and os.path.getsize(yol) <= 200_000:
        return yol
    return None


def imzo(sarlavha=None, belgi="🎧"):
    """Fayl ostidagi chiroyli yozuv: nomi va bot havolasi."""
    qator = []
    if sarlavha:
        qator.append("%s <b>%s</b>" % (belgi, escape(sarlavha[:200])))
    if BOT_USERNAME:
        qator.append("📥 @%s orqali yuklandi" % BOT_USERNAME)
    return "\n\n".join(qator) or None


VIDEO_FORMAT = ("bv*[ext=mp4][height<=720][vcodec^=avc]+ba[ext=m4a]/"
                "b[ext=mp4][height<=720]/bv*[height<=720]+ba/b[height<=720]/b")
VIDEO_FORMAT_KICHIK = ("bv*[ext=mp4][height<=480]+ba[ext=m4a]/b[height<=480]/"
                       "bv*[height<=360]+ba/b[height<=360]/wv*+wa/w")


def havola_yukla(chat, url, db, reply_to=None):
    """Havoladagi video/rasm(lar)ni yuklab yuboradi."""
    call("sendChatAction", chat_id=chat, action="upload_video")
    holat = send(chat, "📥 <b>Yuklab olyapman...</b>\n⏳ Biroz kuting, tez orada tayyor bo'ladi",
                 reply_to=reply_to)
    hid = holat.get("result", {}).get("message_id")
    papka = tempfile.mkdtemp(prefix="video-")
    try:
        kalit = None

        def ochish(q):
            with yt_dlp.YoutubeDL(ydl_sozlama(papka, skip_download=True, noplaylist=True, **q)) as y:
                return y.extract_info(url, download=False), q
        info, qosh = yt_bilan(url, ochish)
        yagona = info.get("_type") != "playlist"
        if yagona:
            kalit = "video:%s:%s" % (info.get("extractor_key", "?"), info.get("id"))
            eski = kesh_ol(db, kalit)
            if eski:
                r = call(eski["usul"], chat_id=chat, **{eski["maydon"]: eski["id"]},
                         caption=imzo(), parse_mode="HTML",
                         reply_markup=audio_tugma(url, eski["maydon"]),
                         reply_to_message_id=reply_to, allow_sending_without_reply="true")
                if r.get("ok"):
                    return r
        if yagona and (info.get("duration") or 0) > 3 * 3600:
            return send(chat, "Video juda uzun (3 soatdan ortiq) 😔", reply_to=reply_to)

        # Instagram karusel kabi bir nechta fayl: hammasini (ALBOM tagacha) yuklaymiz.
        sozlama = ydl_sozlama(papka, format=VIDEO_FORMAT, merge_output_format="mp4",
                              playlist_items="1-%d" % ALBOM, **qosh)
        asl = copy.deepcopy(info)                # kichik sifatda qayta urinish uchun
        try:
            with yt_dlp.YoutubeDL(sozlama) as y:
                info = y.process_ie_result(info, download=True)   # qayta ochmaymiz
        except Exception as e:
            if "larger than max-filesize" not in str(e) and "File is larger" not in str(e):
                raise
        topildi = fayllar(papka)
        if not topildi or any(os.path.getsize(f) > MAX_BAYT for f in topildi):
            for f in topildi:                    # kattasi chiqdi — sifatini pasaytiramiz
                os.remove(f)
            sozlama["format"] = VIDEO_FORMAT_KICHIK
            try:
                with yt_dlp.YoutubeDL(sozlama) as y:
                    info = y.process_ie_result(asl, download=True)
            except Exception as e:
                print("kichik sifat xatosi:", repr(e)[:300], file=sys.stderr)
            topildi = [f for f in fayllar(papka) if os.path.getsize(f) <= MAX_BAYT]
        if not topildi:
            return send(chat, "Fayl juda katta (%d MB dan ortiq) yoki yuklab bo'lmadi 😔" % MAX_MB,
                        reply_to=reply_to)

        natija = None
        for i, f in enumerate(topildi[:ALBOM]):
            oxirgi = i == len(topildi[:ALBOM]) - 1
            natija = fayl_yubor(chat, f, info, url if oxirgi else None, reply_to if i == 0 else None)
        if yagona and kalit and natija and natija.get("ok") and len(topildi) == 1:
            saqla = tg_fayl(natija.get("result") or {})
            if saqla:
                kesh_yoz(db, kalit, saqla)
        return natija
    finally:
        shutil.rmtree(papka, ignore_errors=True)
        if hid:
            call("deleteMessage", chat_id=chat, message_id=hid)


def audio_tugma(url, maydon):
    if maydon not in ("video", "animation"):
        return None
    return inline([[("🎵 Musiqasini yuklash (MP3)", "a:" + kalit_saqla(url))]])


def fayl_yubor(chat, yol, info, url, reply_to):
    ext = os.path.splitext(yol)[1].lower()
    fields = {"chat_id": chat, "caption": imzo(), "parse_mode": "HTML",
              "reply_to_message_id": reply_to,
              "allow_sending_without_reply": "true"}
    if ext in RASM:
        call("sendChatAction", chat_id=chat, action="upload_photo")
        r = upload("sendPhoto", fields, {"photo": yol})
        if not r.get("ok"):                       # juda katta/kichik rasm — hujjat qilib
            r = upload("sendDocument", fields, {"document": yol})
        return r
    if ext in AUDIO:
        fields.update(title=(info.get("title") or "")[:64] or None,
                      performer=(info.get("uploader") or "")[:64] or None)
        return upload("sendAudio", fields, {"audio": yol})
    call("sendChatAction", chat_id=chat, action="upload_video")
    fields.update(caption=imzo(info.get("title"), "🎬"), supports_streaming="true",
                  width=info.get("width"), height=info.get("height"),
                  duration=int(info.get("duration") or 0) or None,
                  reply_markup=audio_tugma(url, "video") if url else None)
    r = upload("sendVideo", fields, {"video": yol})
    if not r.get("ok"):
        r = upload("sendDocument", fields, {"document": yol})
    return r


def tg_fayl(msg):
    """Yuborilgan xabardan qayta ishlatiladigan file_id."""
    for maydon, usul in (("video", "sendVideo"), ("animation", "sendAnimation"),
                         ("audio", "sendAudio"), ("document", "sendDocument")):
        if msg.get(maydon):
            return {"usul": usul, "maydon": maydon, "id": msg[maydon]["file_id"]}
    if msg.get("photo"):
        return {"usul": "sendPhoto", "maydon": "photo", "id": msg["photo"][-1]["file_id"]}
    return None


# ---------------------------------------------------------------- ishlov
def ish(band, chat, fn, *args):
    """Yuklashni alohida oqimda bajaradi; bitta foydalanuvchi — bitta yuklash."""
    try:
        fn(chat, *args)
    except Exception as e:
        print("yuklash xatosi:", fn.__name__, repr(e)[:500], file=sys.stderr)
        reply = args[2] if len(args) > 2 else None
        send(chat, xato_matn(e), reply_to=reply)
    finally:
        boshat(band)


def navbatga(pool, chat, fn, *args):
    # Qidiruv va yuklash alohida: fayl yuklanayotganda ham qo'shiq qidirsa bo'ladi.
    qidiruv = fn is qidiruv_ish
    band = (chat, "q" if qidiruv else "d")
    if not band_qil(band):
        send(chat, "⏳ Oldingi so'rovingiz hali tayyorlanmoqda, biroz kuting...")
        return False
    (pool["q"] if qidiruv else pool["d"]).submit(ish, band, chat, fn, *args)
    return True


def handle(msg, db, pool):
    chat = str(msg["chat"]["id"])
    text = (msg.get("text") or msg.get("caption") or "").strip()
    frm = msg.get("from") or {}
    with _db_lock:
        u = db["users"].setdefault(chat, {"birinchi": int(time.time()), "soni": 0})
        u["ism"] = frm.get("first_name", "")
        u["soni"] = u.get("soni", 0) + 1
    if text.split()[:1] and text.split()[0].split("@")[0].lower() == "/privacy":
        return send(chat, MAXFIYLIK)              # obunasiz ham ko'rinsin
    if msg["chat"].get("type") == "private" and not obunachi(db, chat):
        kutilgan = msg if text and not text.startswith("/") else None
        return obuna_sora(chat, frm, kutilgan)
    if not text:
        return send(chat, "✍️ Qo'shiq nomini yoki havolani <b>matn</b> qilib yuboring 🙂")
    if text.startswith("/"):
        buyruq = text.split()[0].split("@")[0].lower()
        if buyruq == "/start":
            return salom(chat, frm)
        if buyruq in ("/help", "/yordam"):
            return send(chat, YORDAM)
        if buyruq == "/stat":
            with _db_lock:
                return send(chat, "👥 Foydalanuvchilar: %d\n💾 Keshdagi fayllar: %d" % (
                    len(db["users"]), len(db["kesh"])))
        text = text[len(text.split()[0]):].strip()   # /musiqa nom → nom
        if not text:
            return salom(chat, frm)
    url = havola_top(text)
    if url:
        return navbatga(pool, chat, havola_yukla, url, db, msg["message_id"])
    if len(text) > 200:
        return send(chat, "✂️ Juda uzun 🙂 Faqat qo'shiq nomi va ijrochini yozing.")
    if msg["chat"].get("type") != "private":
        return None                               # guruhda oddiy gaplarga javob bermaymiz
    return navbatga(pool, chat, qidiruv_ish, text, db, msg["message_id"])


# ---------------------------------------------------------------- majburiy obuna
_kanal_nomi = {}           # "@kanal" → kanal sarlavhasi (getChat)
_obuna_ok = {}             # user_id → oxirgi muvaffaqiyatli tekshiruv vaqti
_kutayotgan = {}           # user_id → obunadan oldin yozgan so'rovi (keyin bajariladi)
_ogohlantirildi = set()


def kanal_nomlari():
    for k in KANALLAR:
        r = call("getChat", chat_id=k)
        _kanal_nomi[k] = (r.get("result") or {}).get("title") or k.lstrip("@")


def kanal_havola(k):
    return "https://t.me/" + k.lstrip("@") if k.startswith("@") else k


def obuna_emas(user_id):
    """Foydalanuvchi obuna bo'lmagan Telegram kanallar ro'yxati."""
    if time.time() - _obuna_ok.get(user_id, 0) < OBUNA_KESH:
        return []
    yoq = []
    for k in KANALLAR:
        r = call("getChatMember", chat_id=k, user_id=user_id)
        if not r.get("ok"):
            # Bot kanalda admin emas — tekshira olmaymiz, foydalanuvchini to'smaymiz.
            if k not in _ogohlantirildi:
                _ogohlantirildi.add(k)
                print("ogohlantirish: %s kanalini tekshirib bo'lmadi (%s) — botni kanalga "
                      "admin qiling." % (k, r.get("description")), file=sys.stderr)
            continue
        m = r["result"]
        if m.get("status") in ("left", "kicked") or (
                m.get("status") == "restricted" and not m.get("is_member")):
            yoq.append(k)
    if not yoq:
        _obuna_ok[user_id] = time.time()
    return yoq


def obunachi(db, user_id):
    with _db_lock:
        tasdiq = (db["users"].get(user_id) or {}).get("obuna")
    return bool(tasdiq) and not obuna_emas(user_id)


def obuna_matn(ism, yoq=None):
    qator = ["🔒 <b>%s, botdan foydalanish uchun quyidagilarga obuna bo'ling:</b>\n" % ism]
    for i, k in enumerate(KANALLAR, 1):
        belgi = "❌" if yoq and k in yoq else ("✅" if yoq is not None else "📢")
        qator.append("%s <b>%d-kanal:</b> %s" % (belgi, i, escape(_kanal_nomi.get(k, k))))
    if TIKTOK:
        qator.append("🎵 <b>TikTok</b> sahifamiz")
    if INSTAGRAM:
        qator.append("📸 <b>Instagram</b> sahifamiz")
    if yoq:
        qator.append("\n⚠️ <b>Siz hali %s ga obuna bo'lmadingiz!</b>\nObuna bo'lib, "
                     "qaytadan tekshiring 👇" % ", ".join(
                         "«%s»" % escape(_kanal_nomi.get(k, k)) for k in yoq))
    else:
        qator.append("\n✅ Hammasiga obuna bo'lgach, <b>«Obuna bo'ldim»</b> tugmasini bosing 👇")
    return "\n".join(qator)


def obuna_tugmalar(yoq=None):
    rows = []
    for i, k in enumerate(KANALLAR, 1):
        belgi = "❌ " if yoq and k in yoq else ("✅ " if yoq is not None else "📢 ")
        rows.append([(belgi + _kanal_nomi.get(k, "%d-kanal" % i), kanal_havola(k))])
    ijtimoiy = []
    if TIKTOK:
        ijtimoiy.append(("🎵 TikTok", TIKTOK))
    if INSTAGRAM:
        ijtimoiy.append(("📸 Instagram", INSTAGRAM))
    if ijtimoiy:
        rows.append(ijtimoiy)
    rows.append([("✅ Obuna bo'ldim — tekshirish", "t")])
    return inline(rows)


def obuna_sora(chat, frm, kutilgan=None):
    if kutilgan:
        _kutayotgan[chat] = kutilgan
    ism = escape(frm.get("first_name") or "Do'stim")
    return send(chat, obuna_matn(ism), obuna_tugmalar())


def obuna_tekshir(cq, db, pool):
    chat = str(cq["from"]["id"])
    msg = cq.get("message") or {}
    ism = escape(cq["from"].get("first_name") or "Do'stim")
    _obuna_ok.pop(chat, None)
    yoq = obuna_emas(chat)
    if yoq:
        call("answerCallbackQuery", callback_query_id=cq["id"], show_alert="true",
             text="❌ Siz hali %s ga obuna bo'lmadingiz!\n\nObuna bo'lib, qaytadan bosing."
                  % ", ".join("«%s»" % _kanal_nomi.get(k, k) for k in yoq))
        if msg:
            edit(chat, msg["message_id"], obuna_matn(ism, yoq), obuna_tugmalar(yoq))
        return None
    with _db_lock:
        db["users"].setdefault(chat, {"birinchi": int(time.time()), "soni": 0})["obuna"] = True
    call("answerCallbackQuery", callback_query_id=cq["id"], text="✅ Rahmat! Obuna tasdiqlandi")
    if msg:
        call("deleteMessage", chat_id=chat, message_id=msg["message_id"])
    kutilgan = _kutayotgan.pop(chat, None)
    if kutilgan:                                  # obunadan oldin so'ragan narsasini bajaramiz
        send(chat, "✅ <b>Rahmat, obuna tasdiqlandi!</b> So'rovingizni bajaryapman...")
        return handle(kutilgan, db, pool)
    return salom(chat, cq["from"])


def foydalanuvchilar_soni():
    """Botga yozgan odamlar soni (guruhlar hisobga kirmaydi)."""
    if _DB is None:
        return 0
    with _db_lock:
        return sum(1 for k in _DB["users"] if not k.startswith("-"))


def salom(chat, frm):
    ism = escape(frm.get("first_name") or "do'stim")
    tugmalar = [[("📖 Qanday ishlaydi?", "h")]]
    if BOT_USERNAME:
        tugmalar.append([("➕ Guruhga qo'shish",
                          "https://t.me/%s?startgroup=true" % BOT_USERNAME)])
    matn = SALOM % (ism, escape(BOT_NOMI or "musiqa boti"))
    soni = foydalanuvchilar_soni()
    if soni:
        matn = matn.replace("✨ Qani, boshladik", "👥 Botdan <b>%s</b> kishi foydalanmoqda\n\n"
                            "✨ Qani, boshladik" % "{:,}".format(soni).replace(",", " "), 1)
    kb = inline(tugmalar)
    return rasm_bilan(chat, SALOM_RASM, "salom_rasm", matn, kb)


def rasm_bilan(chat, yol, kesh_kalit, matn, kb=None):
    """Rasm + matn: rasm bir marta yuklanadi, keyin Telegram file_id si ishlatiladi."""
    db = _DB
    fid = kesh_ol(db, kesh_kalit) if db is not None else None
    if fid:
        r = call("sendPhoto", chat_id=chat, photo=fid, caption=matn, parse_mode="HTML",
                 reply_markup=kb)
        if r.get("ok"):
            return r
    if os.path.exists(yol):
        r = upload("sendPhoto", {"chat_id": chat, "caption": matn, "parse_mode": "HTML",
                                 "reply_markup": kb}, {"photo": yol})
        if r.get("ok"):
            if db is not None:
                kesh_yoz(db, kesh_kalit, r["result"]["photo"][-1]["file_id"])
            return r
    return send(chat, matn, kb)


def qidiruv_ish(chat, soz, db, reply_to):
    qidiruv_xabar(chat, soz, reply_to)


def callback(cq, db, pool):
    data = cq.get("data") or ""
    chat = str(cq["message"]["chat"]["id"]) if cq.get("message") else str(cq["from"]["id"])
    tur, _, qiymat = data.partition(":")
    if tur == "t":                                  # ✅ Obuna bo'ldim — tekshirish
        return obuna_tekshir(cq, db, pool)
    xabar_chat = (cq.get("message") or {}).get("chat", {})
    if xabar_chat.get("type", "private") == "private" and not obunachi(db, str(cq["from"]["id"])):
        call("answerCallbackQuery", callback_query_id=cq["id"])
        return obuna_sora(str(cq["from"]["id"]), cq["from"])
    if tur == "x":                                  # ❌ Yopish
        call("answerCallbackQuery", callback_query_id=cq["id"])
        return call("deleteMessage", chat_id=chat, message_id=cq["message"]["message_id"])
    if tur == "h":                                  # 📖 Qanday ishlaydi?
        call("answerCallbackQuery", callback_query_id=cq["id"])
        return send(chat, YORDAM)
    url = None
    if tur == "y" and YT_ID_RE.match(qiymat):
        url = "https://www.youtube.com/watch?v=" + qiymat
    elif tur in ("u", "a"):
        url = _xotira.get(qiymat)
    if not url:
        return call("answerCallbackQuery", callback_query_id=cq["id"], show_alert="true",
                    text="Bu tugma eskirgan. Qo'shiq nomini yoki havolani qayta yuboring.")
    if navbatga(pool, chat, audio_yukla, url, db, None):
        call("answerCallbackQuery", callback_query_id=cq["id"], text="🎵 MP3 tayyorlanmoqda...")
    else:
        call("answerCallbackQuery", callback_query_id=cq["id"],
             text="⏳ Oldingi so'rov hali tayyorlanmoqda")


def process(updates, db, pool):
    last = None
    for upd in updates:
        last = upd["update_id"]
        try:                                      # bitta xato botni to'xtatmasin
            if upd.get("message"):
                handle(upd["message"], db, pool)
            elif upd.get("callback_query"):
                callback(upd["callback_query"], db, pool)
        except Exception as e:
            print("xato:", repr(e), file=sys.stderr)
    return last


BOT_USERNAME = ""
BOT_NOMI = ""


def bot_nomi():
    global BOT_USERNAME, BOT_NOMI
    me = call("getMe").get("result", {})
    BOT_USERNAME = me.get("username", "") or BOT_USERNAME
    BOT_NOMI = me.get("first_name", "") or BOT_NOMI


# Menyudagi buyruqlar. /privacy ro'yxatda yo'q, lekin yozilsa ishlaydi.
BUYRUQLAR = [
    {"command": "start", "description": "🏠 Bosh sahifa"},
    {"command": "help", "description": "📖 Qanday foydalaniladi"},
]


def setup():
    r1 = call("setMyCommands", commands=BUYRUQLAR)
    r2 = call("setMyDescription", description=TAVSIF)
    r3 = call("setMyShortDescription", short_description=QISQA_TAVSIF)
    bot_nomi()
    # Bot rasmi (Botpic). Yangi Bot API'da bor; eski serverda bo'lmasa — shunchaki o'tamiz.
    r4 = {"ok": False}
    if os.path.exists(BOTPIC):
        r4 = upload("setMyProfilePhoto", {"photo": {"type": "static", "photo": "attach://rasm"}},
                    {"rasm": BOTPIC})
    print("bot: @%s" % (BOT_USERNAME or "?"))
    print("buyruqlar:", r1.get("ok"), "| tavsif:", r2.get("ok"), r3.get("ok"),
          "| bot rasmi:", r4.get("ok"), r4.get("description") or "")
    return all(x.get("ok") for x in (r1, r2, r3))


def main(argv):
    if not TOKEN:
        sys.exit("BOT_TOKEN o'zgaruvchisini kiriting.")
    if yt_dlp is None:
        sys.exit("yt-dlp o'rnatilmagan: pip install -U 'yt-dlp[default]'")
    if not shutil.which("ffmpeg"):
        print("ogohlantirish: ffmpeg topilmadi — MP3 ga aylantirib bo'lmaydi.", file=sys.stderr)
    global _DB
    db = _DB = load()

    if "--setup" in argv:
        sys.exit(0 if setup() else 1)

    tugash = None
    if "--uzluksiz" in argv:
        # GitHub Actions: belgilangan daqiqa davomida ishlaydi, keyin navbatdagi
        # ishga tushish davom ettiradi.
        i = argv.index("--uzluksiz")
        daqiqa = int(argv[i + 1]) if len(argv) > i + 1 and argv[i + 1].isdigit() else 50
        tugash = time.time() + daqiqa * 60

    bot_nomi()
    kanal_nomlari()
    if not db.get("buyruqlar_v3"):                   # bir marta: buyruqlar va tavsif
        db["buyruqlar_v3"] = setup()
    if not db.get("buyruqlar_v4"):                   # bir marta: menyu faqat /start va /help
        db["buyruqlar_v4"] = bool(call("setMyCommands", commands=BUYRUQLAR).get("ok"))
    print("Musiqa boti ishga tushdi: @%s" % BOT_USERNAME)
    # Qidiruv tez — alohida ishchilar, uzoq yuklashlar ularni to'sib qo'ymasin.
    pool = {"q": ThreadPoolExecutor(max_workers=8), "d": ThreadPoolExecutor(max_workers=ISHCHILAR)}
    offset, soni, keyingi_saqlash = None, 0, 0
    try:
        while True:
            timeout = 50
            if tugash is not None:
                qoldi = int(tugash - time.time())
                if qoldi <= 0:
                    break
                timeout = max(1, min(50, qoldi))
            r = call("getUpdates", offset=offset, timeout=timeout,
                     allowed_updates=["message", "callback_query"])
            natija = r.get("result", [])
            last = process(natija, db, pool)
            if last is not None:
                offset = last + 1
                soni += len(natija)
            elif not r.get("ok"):
                time.sleep(5)                        # tarmoq xatosi — biroz kutamiz
            if time.time() >= keyingi_saqlash:
                save(db)
                keyingi_saqlash = time.time() + 60
    finally:
        for p in pool.values():
            p.shutdown(wait=True)                    # boshlangan yuklashlar tugasin
        if offset is not None:
            call("getUpdates", offset=offset, timeout=0)   # «shulargacha ko'rdim»
        save(db)
        print("qayta ishlandi: %d ta, foydalanuvchilar: %d" % (soni, len(db["users"])))


if __name__ == "__main__":
    main(sys.argv[1:])
