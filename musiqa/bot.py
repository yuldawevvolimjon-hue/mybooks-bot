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
    ISHCHILAR      bir vaqtda nechta yuklash (standart 3)
"""

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
ISHCHILAR = int(os.environ.get("ISHCHILAR") or 3)

NATIJA_SONI = 10           # qidiruvda nechta qo'shiq ko'rsatiladi
ENG_UZUN = 20 * 60         # qidiruvda 20 daqiqadan uzun videolar (mikslar) chiqmasin
ALBOM = 10                 # bitta havoladan ko'pi bilan nechta fayl (Instagram karusel)

SALOM = (
    "Assalomu alaykum! 🎧\n\n"
    "🎵 <b>Qo'shiq nomini yozing</b> — o'zbekcha, ruscha, inglizcha, "
    "istalgan tilda. Masalan: <i>Shahzoda Yuragim</i> yoki <i>Макс Корж Мотылёк</i>.\n\n"
    "🔗 <b>Havola yuboring</b> — Instagram, TikTok, YouTube, Facebook, "
    "X (Twitter), Pinterest, VK, Likee, SoundCloud va boshqalar. "
    "Videoni yuklab beraman, xohlasangiz musiqasini ham."
)
TAVSIF = ("🎵 Istalgan qo'shiqni nomi bo'yicha topib beraman — o'zbek, rus, "
          "ingliz va boshqa tillarda.\n\n🔗 Instagram, TikTok, YouTube, Facebook "
          "va boshqa tarmoqlardan havola yuborsangiz, videoni yuklab beraman.")

URL_RE = re.compile(r"https?://[^\s<>\"']+|(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}/[^\s<>\"']*",
                    re.I)
YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
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
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row]
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


def band_qil(chat):
    with _band_lock:
        if chat in _band:
            return False
        _band.add(chat)
        return True


def boshat(chat):
    with _band_lock:
        _band.discard(chat)


def ydl_sozlama(papka, **qoshimcha):
    o = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 30,
        "retries": 3,
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
        return "😔 YouTube vaqtincha yuklashga ruxsat bermadi. Birozdan keyin urinib ko'ring."
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
def qidir(soz):
    """YouTube'dan, bo'lmasa SoundCloud'dan qo'shiqlar ro'yxati."""
    for manba, prefiks in (("youtube", "ytsearch%d:" % (NATIJA_SONI * 2)),
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
            if len(natija) >= NATIJA_SONI:
                break
        if natija:
            return natija
    return []


def qidiruv_xabar(chat, soz, reply_to):
    xabar = send(chat, "🔎 <b>%s</b> qidirilmoqda..." % escape(soz), reply_to=reply_to)
    mid = xabar.get("result", {}).get("message_id")
    natija = qidir(soz)
    if not natija:
        matn = ("😔 <b>%s</b> bo'yicha hech narsa topilmadi.\n"
                "Nomini boshqacha yozib ko'ring (ijrochi + qo'shiq nomi)." % escape(soz))
        return edit(chat, mid, matn) if mid else send(chat, matn)
    qatorlar = ["🎵 <b>%s</b>\n" % escape(soz)]
    tugmalar = []
    for i, r in enumerate(natija, 1):
        qatorlar.append("<b>%d.</b> %s%s" % (
            i, escape(r["nom"][:90]), (" <i>(%s)</i>" % vaqt(r["vaqt"])) if r["vaqt"] else ""))
        if r["manba"] == "youtube" and r["id"] and YT_ID_RE.match(r["id"]):
            data = "y:" + r["id"]                 # qayta ishga tushsa ham ishlaydi
        else:
            data = "u:" + kalit_saqla(r["url"])
        tugmalar.append((str(i), data))
    qatorlar.append("\n👇 Raqamni bosing — MP3 qilib yuboraman")
    kb = inline([tugmalar[:5], tugmalar[5:10]] if len(tugmalar) > 5 else [tugmalar])
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


def audio_yukla(chat, url, db, reply_to=None):
    """Havoladagi (YouTube, SoundCloud, TikTok...) ovozni MP3 qilib yuboradi."""
    call("sendChatAction", chat_id=chat, action="upload_voice")
    papka = tempfile.mkdtemp(prefix="musiqa-")
    try:
        with yt_dlp.YoutubeDL(ydl_sozlama(papka, skip_download=True)) as y:
            info = y.extract_info(url, download=False)
        if info.get("_type") == "playlist":
            info = next((e for e in info.get("entries") or [] if e), None)
            if not info:
                return send(chat, "Bu havolada audio topilmadi.", reply_to=reply_to)
        kalit = "audio:%s:%s" % (info.get("extractor_key", "?"), info.get("id"))
        eski = kesh_ol(db, kalit)
        if eski:
            r = call("sendAudio", chat_id=chat, audio=eski, reply_to_message_id=reply_to,
                     allow_sending_without_reply="true", caption=imzo())
            if r.get("ok"):
                return r
        sozlama = ydl_sozlama(papka, format="bestaudio/best", postprocessors=[
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}])
        with yt_dlp.YoutubeDL(sozlama) as y:
            info = y.extract_info(info.get("webpage_url") or url, download=True)
        mp3 = [f for f in fayllar(papka) if f.lower().endswith(".mp3")]
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
        elif not r.get("ok"):
            send(chat, "Telegram'ga yuborib bo'lmadi 😔", reply_to=reply_to)
        return r
    finally:
        shutil.rmtree(papka, ignore_errors=True)


def muqova(info, papka):
    """Audio uchun kichik muqova (Telegram: JPEG, 320 px gacha, 200 KB gacha)."""
    url = info.get("thumbnail")
    if not url:
        return None
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
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


def imzo():
    return "@%s" % BOT_USERNAME if BOT_USERNAME else None


VIDEO_FORMAT = ("bv*[ext=mp4][height<=720][vcodec^=avc]+ba[ext=m4a]/"
                "b[ext=mp4][height<=720]/bv*[height<=720]+ba/b[height<=720]/b")
VIDEO_FORMAT_KICHIK = ("bv*[ext=mp4][height<=480]+ba[ext=m4a]/b[height<=480]/"
                       "bv*[height<=360]+ba/b[height<=360]/wv*+wa/w")


def havola_yukla(chat, url, db, reply_to=None):
    """Havoladagi video/rasm(lar)ni yuklab yuboradi."""
    call("sendChatAction", chat_id=chat, action="upload_video")
    holat = send(chat, "⏳ Yuklanmoqda...", reply_to=reply_to)
    hid = holat.get("result", {}).get("message_id")
    papka = tempfile.mkdtemp(prefix="video-")
    try:
        kalit = None
        with yt_dlp.YoutubeDL(ydl_sozlama(papka, skip_download=True, noplaylist=True)) as y:
            info = y.extract_info(url, download=False)
        yagona = info.get("_type") != "playlist"
        if yagona:
            kalit = "video:%s:%s" % (info.get("extractor_key", "?"), info.get("id"))
            eski = kesh_ol(db, kalit)
            if eski:
                r = call(eski["usul"], chat_id=chat, **{eski["maydon"]: eski["id"]},
                         caption=imzo(), reply_markup=audio_tugma(url, eski["maydon"]),
                         reply_to_message_id=reply_to, allow_sending_without_reply="true")
                if r.get("ok"):
                    return r
        if yagona and (info.get("duration") or 0) > 3 * 3600:
            return send(chat, "Video juda uzun (3 soatdan ortiq) 😔", reply_to=reply_to)

        # Instagram karusel kabi bir nechta fayl: hammasini (ALBOM tagacha) yuklaymiz.
        sozlama = ydl_sozlama(papka, format=VIDEO_FORMAT, merge_output_format="mp4",
                              playlist_items="1-%d" % ALBOM)
        try:
            with yt_dlp.YoutubeDL(sozlama) as y:
                info = y.extract_info(info.get("webpage_url") or url, download=True)
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
                    info = y.extract_info(info.get("webpage_url") or url, download=True)
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
    return inline([[("🎵 Musiqasini yuklash", "a:" + kalit_saqla(url))]])


def fayl_yubor(chat, yol, info, url, reply_to):
    ext = os.path.splitext(yol)[1].lower()
    fields = {"chat_id": chat, "caption": imzo(), "reply_to_message_id": reply_to,
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
    fields.update(supports_streaming="true",
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
def ish(chat, fn, *args):
    """Yuklashni alohida oqimda bajaradi; bitta foydalanuvchi — bitta yuklash."""
    try:
        fn(chat, *args)
    except Exception as e:
        print("yuklash xatosi:", fn.__name__, repr(e)[:500], file=sys.stderr)
        reply = args[2] if len(args) > 2 else None
        send(chat, xato_matn(e), reply_to=reply)
    finally:
        boshat(chat)


def navbatga(pool, chat, fn, *args):
    if not band_qil(chat):
        send(chat, "⏳ Oldingi so'rovingiz hali tayyorlanmoqda, biroz kuting...")
        return False
    pool.submit(ish, chat, fn, *args)
    return True


def handle(msg, db, pool):
    chat = str(msg["chat"]["id"])
    text = (msg.get("text") or msg.get("caption") or "").strip()
    frm = msg.get("from") or {}
    with _db_lock:
        u = db["users"].setdefault(chat, {"birinchi": int(time.time()), "soni": 0})
        u["ism"] = frm.get("first_name", "")
        u["soni"] = u.get("soni", 0) + 1
    if not text:
        return send(chat, "Qo'shiq nomini yoki havolani matn qilib yuboring 🙂")
    if text.startswith("/"):
        buyruq = text.split()[0].split("@")[0].lower()
        if buyruq in ("/start", "/help", "/yordam"):
            return send(chat, SALOM)
        if buyruq == "/stat":
            with _db_lock:
                return send(chat, "👥 Foydalanuvchilar: %d\n💾 Keshdagi fayllar: %d" % (
                    len(db["users"]), len(db["kesh"])))
        text = text[len(text.split()[0]):].strip()   # /musiqa nom → nom
        if not text:
            return send(chat, SALOM)
    url = havola_top(text)
    if url:
        return navbatga(pool, chat, havola_yukla, url, db, msg["message_id"])
    if len(text) > 200:
        return send(chat, "Juda uzun 🙂 Faqat qo'shiq nomi va ijrochini yozing.")
    if msg["chat"].get("type") != "private":
        return None                               # guruhda oddiy gaplarga javob bermaymiz
    return navbatga(pool, chat, qidiruv_ish, text, db, msg["message_id"])


def qidiruv_ish(chat, soz, db, reply_to):
    qidiruv_xabar(chat, soz, reply_to)


def callback(cq, db, pool):
    data = cq.get("data") or ""
    chat = str(cq["message"]["chat"]["id"]) if cq.get("message") else str(cq["from"]["id"])
    tur, _, qiymat = data.partition(":")
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


def bot_nomi():
    global BOT_USERNAME
    BOT_USERNAME = call("getMe").get("result", {}).get("username", "") or BOT_USERNAME


def setup():
    r1 = call("setMyCommands", commands=[
        {"command": "start", "description": "Botdan foydalanish"},
        {"command": "help", "description": "Yordam"},
    ])
    r2 = call("setMyDescription", description=TAVSIF)
    r3 = call("setMyShortDescription",
              short_description="🎵 Qo'shiq qidirish va 🔗 Instagram, TikTok, YouTube'dan yuklash")
    bot_nomi()
    print("bot: @%s" % (BOT_USERNAME or "?"))
    print("buyruqlar:", r1.get("ok"), "| tavsif:", r2.get("ok"), r3.get("ok"))
    return all(x.get("ok") for x in (r1, r2, r3))


def main(argv):
    if not TOKEN:
        sys.exit("BOT_TOKEN o'zgaruvchisini kiriting.")
    if yt_dlp is None:
        sys.exit("yt-dlp o'rnatilmagan: pip install -U 'yt-dlp[default]'")
    if not shutil.which("ffmpeg"):
        print("ogohlantirish: ffmpeg topilmadi — MP3 ga aylantirib bo'lmaydi.", file=sys.stderr)
    db = load()

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
    if not db.get("buyruqlar_v1"):                   # bir marta: buyruqlar va tavsif
        db["buyruqlar_v1"] = setup()
    print("Musiqa boti ishga tushdi: @%s" % BOT_USERNAME)
    pool = ThreadPoolExecutor(max_workers=ISHCHILAR)
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
        pool.shutdown(wait=True)                     # boshlangan yuklashlar tugasin
        if offset is not None:
            call("getUpdates", offset=offset, timeout=0)   # «shulargacha ko'rdim»
        save(db)
        print("qayta ishlandi: %d ta, foydalanuvchilar: %d" % (soni, len(db["users"])))


if __name__ == "__main__":
    main(sys.argv[1:])
