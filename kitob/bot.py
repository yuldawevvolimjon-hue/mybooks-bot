#!/usr/bin/env python3
"""
Kitob olami — Telegram bot (kitob do'koni).

Vazifasi:
  1. Ro'yxatdan o'tish: /start → «📝 Ro'yxatdan o'tish» → ism, familiya,
     telefon, yosh, qiziqqan kitob janri.
  2. Juma aksiyasi: har juma bitta kitob odatiy narxidan arzonga sotiladi,
     lekin tannarxdan arzon emas — do'kon zarar ko'rmaydi. Aksiyani do'kon
     egasi bot ichida qo'shadi.
  3. Band qilish (bron): juma kelmasdan oldin aksiya xabari ostidagi
     «📌 Band qilish» → soni → kitob pulining YARMINI oldindan to'lab, chek
     rasmini yuboradi → tasdiqlash. Do'kon egasi chekni ✅/❌ bilan qabul
     qiladi yoki rad etadi. Qolgan yarmi juma kuni kitob olinganda to'lanadi.
     Band qilganlarga shaxsiy eslatma: 1 kun oldin va juma kuni ertalab.
  4. Eslatmalar (Toshkent vaqti bilan, soat ESLATMA_SOAT dan keyin):
       - do'kon egasiga — aksiyadan 4 hafta oldin (kitobni tayyorlash uchun)
         va 4 hafta keyingi juma bo'sh bo'lsa, «aksiya qo'ying» deb;
       - do'kon egasiga — mijozlarga e'lon ketishidan bir kun oldin;
       - mijozlarga — 1 hafta oldin, bir kun oldin va juma kuni ertalab.
     Mijozlar aksiyani faqat 1 hafta qolganda biladi — undan oldin bot
     hech kimga ko'rsatmaydi.

Do'kon egasi (ADMIN_IDS) uchun buyruqlar:
    ➕ Aksiya qo'shish   — sana, kitob, janr, narxlar so'raladi
    📋 Aksiyalar          — rejalashtirilgan aksiyalar, chegirma va foyda
    📦 Buyurtmalar        — kutilayotgan buyurtmalar, ✅/❌ tugmalari bilan
    👥 Mijozlar           — ro'yxatdan o'tganlar
    📊 Marketing          — mijozlar, sotuv, xarajat va haftalik grafik
    /ochir 3              — 3-aksiyani o'chirish
    /xabar matn           — barcha mijozlarga xabar
    /men                  — o'z Telegram ID ingizni bilish

Rejimlar:
    python3 bot.py              # doimiy (server bo'lsa): long polling
    python3 bot.py --once       # GitHub Actions: xabarlar + eslatmalar
    python3 bot.py --setup      # buyruqlar va tavsif

Muhit o'zgaruvchilari:
    BOT_TOKEN      BotFather bergan token
    ADMIN_IDS      do'kon egasining Telegram ID lari, vergul bilan
    STATE_FILE     kitob.json manzili (ixtiyoriy)
    ESLATMA_SOAT   eslatmalar yuboriladigan soat, Toshkent vaqti (standart 10)
    TOLOV_KARTA    oldindan to'lov kartasi. Bo'lsa, mijoz yarim pulni shu kartaga
                   o'tkazib chek yuboradi; bo'lmasa, yarim pulni do'konga kelib to'laydi.
"""

import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMINS = {x.strip() for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()}
STORE = os.environ.get("STATE_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "kitob.json")
ESLATMA_SOAT = int(os.environ.get("ESLATMA_SOAT") or 10)
TOLOV_KARTA = os.environ.get("TOLOV_KARTA", "").strip()
API = "https://api.telegram.org/bot%s/" % TOKEN
TOSHKENT = timezone(timedelta(hours=5))

EGA_OLDIN = 28          # do'kon egasi aksiyani necha kun oldin bilishi kerak
MIJOZ_OLDIN = 7         # mijozlar necha kun oldin biladi
CHEGIRMA_TAVSIYA = 10   # aksiya narxi taklifi: odatiy narxdan shuncha foiz arzon
CHEGIRMA_OGOH = 30      # chegirma shu foizdan oshsa, ogohlantiramiz
BIR_KISHIGA = 5         # bitta buyurtmada ko'pi bilan nechta kitob
AKSIYA_SONI = int(os.environ.get("AKSIYA_SONI") or 100)   # har juma nechta kitob aksiyada

BTN_ROYXAT = "📝 Ro'yxatdan o'tish"
BTN_AKSIYA = "🔥 Juma aksiyasi"
BTN_MEN = "👤 Ma'lumotlarim"
BTN_QAYTA = "✏️ Ma'lumotni o'zgartirish"
BTN_BEKOR = "❌ Bekor qilish"
BTN_TELEFON = "📱 Raqamimni yuborish"
BTN_QOSH = "➕ Aksiya qo'shish"
BTN_ROYXAT_AKSIYA = "📋 Aksiyalar"
BTN_MIJOZLAR = "👥 Mijozlar"
BTN_HA = "✅ Ha, saqlash"
BTN_BUYURTMALAR = "📦 Buyurtmalar"
BTN_BUYURTMALARIM = "📦 Buyurtmalarim"
BTN_MARKETING = "📊 Marketing"
BTN_RASMSIZ = "⏭ Rasmsiz"
BTN_TASDIQ = "✅ Band qilishni tasdiqlash"
HOLAT = {"kutilmoqda": "⏳ to'lov tekshirilmoqda", "tasdiqlandi": "✅ band qilindi",
         "rad": "❌ rad etildi"}
BTN_YOQ = "❌ Yo'q"
HAMMA = "📚 Hamma uchun"

JANRLAR = [
    "💪 Motivatsion",
    "🎬 Kino asosidagi kitoblar",
    "💕 Romanlar",
    "🕌 Diniy va tarixiy",
    "🧠 Psixologiya",
    "💼 Biznes",
    "🧸 Bolalar kitoblari",
    "📖 Badiiy adabiyot",
]

OYLAR = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul",
         "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]

SALOM = (
    "Assalomu alaykum! <b>Kitoblar olamiga xush kelibsiz</b> 📚\n\n"
    "Har <b>juma</b> kuni bitta kitobni aksiya narxida sotamiz — "
    "masalan, «Muqaddima» yoki «Saodat asri qissalari».\n\n"
    "Ro'yxatdan o'ting — juma aksiyasini bir hafta oldin sizga "
    "birinchilardan bo'lib aytamiz 👇"
)
# Botga birinchi kirganda, rasm (rasmlar/salom.png) ostida chiqadigan matn.
TAVSIF = ("Assalomu alaykum! Kitoblar olamiga xush kelibsiz 📚\n\n"
          "Har juma bitta kitob aksiya narxida — «Muqaddima», "
          "«Saodat asri qissalari» va boshqalar.\n\n"
          "START tugmasini bosing, ro'yxatdan o'ting va juma aksiyasini "
          "bir hafta oldin biling.")


# ---------------------------------------------------------------- Telegram API
def call(method, **params):
    data = urlencode({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                      for k, v in params.items() if v is not None}).encode()
    try:
        with urlopen(Request(API + method, data=data), timeout=70) as r:
            return json.load(r)
    except HTTPError as e:
        try:
            body = json.load(e)
        except ValueError:
            body = {"description": str(e)}
        print("telegram xatosi:", method, body.get("description"), file=sys.stderr)
        return {"ok": False, **body}
    except URLError as e:
        print("tarmoq xatosi:", e, file=sys.stderr)
        return {"ok": False}


def send(chat_id, text, keyboard=None):
    return call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                disable_web_page_preview="true", reply_markup=keyboard)


def send_photo(chat_id, photo, caption, keyboard=None):
    return call("sendPhoto", chat_id=chat_id, photo=photo, caption=caption,
                parse_mode="HTML", reply_markup=keyboard)



def inline(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row]
                                for row in rows]}


def send_long(chat_id, lines, keyboard=None):
    """Telegram bitta xabarga 4096 belgidan ko'p sig'dirmaydi — bo'lib yuboramiz."""
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) > 3800:
            send(chat_id, chunk)
            chunk = ""
        chunk += line + "\n"
    send(chat_id, chunk or "—", keyboard)


def kb(rows):
    return {"keyboard": [[b if isinstance(b, dict) else {"text": b} for b in row]
                         for row in rows],
            "resize_keyboard": True}


def menyu(chat, db):
    if not royxatda(db, chat):
        rows = [[BTN_ROYXAT], [BTN_AKSIYA]]
    else:
        rows = [[BTN_AKSIYA], [BTN_BUYURTMALARIM, BTN_MEN], [BTN_QAYTA]]
    if chat in ADMINS:
        rows += [[BTN_QOSH, BTN_ROYXAT_AKSIYA], [BTN_BUYURTMALAR, BTN_MIJOZLAR],
                 [BTN_MARKETING]]
    return kb(rows)


def ustunlar(items, n=2):
    return [items[i:i + n] for i in range(0, len(items), n)]


# ---------------------------------------------------------------- saqlash
def load():
    try:
        with open(STORE, encoding="utf-8") as f:
            db = json.load(f)
    except (OSError, ValueError):
        db = {}
    db.setdefault("users", {})
    db.setdefault("promos", [])
    db.setdefault("sent", {})
    db.setdefault("seq", 0)
    db.setdefault("orders", [])
    db.setdefault("oseq", 1000)             # buyurtma raqamlari #1001 dan boshlanadi
    return db


def save(db):
    os.makedirs(os.path.dirname(os.path.abspath(STORE)), exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STORE)


def royxatda(db, chat):
    return bool(db["users"].get(chat, {}).get("royxat"))


# ---------------------------------------------------------------- yordamchilar
def bugun():
    return datetime.now(TOSHKENT).date()


def sana_matn(d):
    return "%d-%s" % (d.day, OYLAR[d.month - 1])


def som(n):
    return "{:,}".format(int(n)).replace(",", " ") + " so'm"


def son(text):
    """«120 000», «120.000 so'm», «120000» → 120000."""
    raqam = re.sub(r"[^\d]", "", text or "")
    return int(raqam) if raqam else None


def telefon_tozala(text):
    raqam = re.sub(r"[^\d]", "", text or "")
    if len(raqam) == 9:                       # 901234567
        raqam = "998" + raqam
    if len(raqam) < 9 or len(raqam) > 15:
        return None
    return "+" + raqam


def jumalar(soni=8):
    """Bugundan keyingi jumalar (bugun juma bo'lsa, u ham kiradi)."""
    d = bugun()
    d += timedelta(days=(4 - d.weekday()) % 7)
    return [d + timedelta(weeks=i) for i in range(soni)]


def sana_oqi(text):
    text = (text or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    m = re.match(r"^(\d{1,2})[- ]([a-z']+)", text.lower())   # «2-oktabr»
    if m and m.group(2) in OYLAR:
        oy = OYLAR.index(m.group(2)) + 1
        d = bugun()
        yil = d.year + (1 if (oy, int(m.group(1))) < (d.month, d.day) else 0)
        try:
            return date(yil, oy, int(m.group(1)))
        except ValueError:
            return None
    return None


def kelgusi(db):
    """Bugundan boshlab kelgusi aksiyalar, sana bo'yicha tartiblangan."""
    b = bugun().isoformat()
    return sorted((p for p in db["promos"] if p["sana"] >= b), key=lambda p: p["sana"])


def foyda(p):
    """Bitta kitobdan foyda (aksiya narxi − tannarx); tannarx mijozga ko'rinmaydi."""
    return p["narx"] - p["tannarx"]


def chegirma_foiz(p):
    return 100.0 * (p["odatiy"] - p["narx"]) / p["odatiy"] if p.get("odatiy") else 0


def band_soni(db, p):
    """Aksiya kitobidan buyurtma qilingan (rad etilmagan) nusxalar soni."""
    return sum(o["soni"] for o in db["orders"]
               if o["promo"] == p["id"] and o["holat"] != "rad")


def qolgan(db, p):
    if not p.get("soni"):
        return None                          # cheklanmagan
    return max(0, p["soni"] - band_soni(db, p))


def korinadi(p):
    """Mijozlar aksiyani faqat MIJOZ_OLDIN kun qolganda ko'radi."""
    return 0 <= (date.fromisoformat(p["sana"]) - bugun()).days <= MIJOZ_OLDIN


def tugadi_matn(p):
    """Aksiya kitoblari tugaganda mijozga: keyingi juma aksiyasiga taklif."""
    keyingi = date.fromisoformat(p["sana"]) + timedelta(weeks=1)
    return ("😔 <b>Kitob qolmadi</b> — bu aksiyadagi %d ta kitobning hammasi band qilindi.\n\n"
            "📅 Keyingi juma aksiyasida (%s) kitob olasiz! Qaysi kitob bo'lishini "
            "bir hafta oldin shu yerga yozamiz 📚" % (p.get("soni") or 0, sana_matn(keyingi)))


def aksiya_yubor(db, chat, p, u=None):
    """Aksiyani mijozga yuboradi: rasm (bo'lsa), matn, qoldiq va «Band qilish» tugmasi."""
    matn = aksiya_matn(p, u)
    q = qolgan(db, p)
    if q == 0:
        matn += "\n\n" + tugadi_matn(p)
        tugma = None
    else:
        if q is not None:
            matn += "\n\n📦 Aksiyada %d ta kitob — qoldi: <b>%d</b> ta" % (p["soni"], q)
        tugma = inline([[("📌 Band qilish — yarim pulini to'lab", "buy:%d" % p["id"])]])
    if p.get("rasm"):
        r = send_photo(chat, p["rasm"], matn, tugma)
        if r.get("ok") or r.get("error_code") == 403:
            return r
    return send(chat, matn, tugma)


def aksiya_matn(p, u=None):
    """Mijozga ko'rsatiladigan aksiya matni (tannarx ko'rsatilmaydi)."""
    d = date.fromisoformat(p["sana"])
    qoldi = (d - bugun()).days
    if qoldi == 0:
        qachon = "🔥 <b>BUGUN — juma aksiyasi!</b>"
    elif qoldi == 1:
        qachon = "⏰ <b>Ertaga — juma aksiyasi!</b>"
    else:
        qachon = "📢 <b>%s, juma — aksiya</b> (%d kun qoldi)" % (sana_matn(d), qoldi)
    lines = [qachon, "", "📖 <b>%s</b>" % escape(p["kitob"])]
    if p.get("odatiy") and p["odatiy"] > p["narx"]:
        lines.append("Narxi: <s>%s</s> → <b>%s</b> (−%.0f%%)"
                     % (som(p["odatiy"]), som(p["narx"]), chegirma_foiz(p)))
    else:
        lines.append("Narxi: <b>%s</b>" % som(p["narx"]))
    lines.append("Bu narx faqat shu juma kuni.")
    if u and p.get("janr") and p["janr"] != HAMMA and u.get("qiziqish") == p["janr"]:
        lines.append("\n💚 Bu siz yoqtirgan janrdan: %s" % escape(p["janr"]))
    if u and u.get("ism"):
        lines.insert(0, "Hurmatli %s!\n" % escape(u["ism"]))
    return "\n".join(lines)


# ---------------------------------------------------------------- ro'yxatdan o'tish
def royxat_qadam(chat, u, msg, text, db):
    qadam = u.get("qadam")
    q = u.setdefault("vaqtincha", {})

    if qadam == "ism":
        if not text or len(text) > 50 or text.startswith("/"):
            send(chat, "Ismingizni yozing (masalan: <i>Aziz</i>).")
            return
        q["ism"] = text
        u["qadam"] = "familiya"
        send(chat, "Familiyangizni yozing:", kb([[BTN_BEKOR]]))
        return

    if qadam == "familiya":
        if not text or len(text) > 50 or text.startswith("/"):
            send(chat, "Familiyangizni yozing (masalan: <i>Karimov</i>).")
            return
        q["familiya"] = text
        u["qadam"] = "telefon"
        send(chat, "Telefon raqamingizni yuboring — pastdagi tugmani bosing "
                   "yoki yozing (masalan: <i>+998 90 123 45 67</i>):",
             kb([[{"text": BTN_TELEFON, "request_contact": True}], [BTN_BEKOR]]))
        return

    if qadam == "telefon":
        contact = msg.get("contact")
        raqam = telefon_tozala(contact["phone_number"] if contact else text)
        if not raqam:
            send(chat, "Raqam noto'g'ri. Masalan: <i>+998 90 123 45 67</i> — "
                       "yoki «%s» tugmasini bosing." % BTN_TELEFON)
            return
        q["telefon"] = raqam
        u["qadam"] = "yosh"
        send(chat, "Yoshingiz nechada?", kb([[BTN_BEKOR]]))
        return

    if qadam == "yosh":
        yosh = son(text)
        if yosh is None or not 5 <= yosh <= 100:
            send(chat, "Yoshingizni raqam bilan yozing (masalan: <i>24</i>).")
            return
        q["yosh"] = yosh
        u["qadam"] = "qiziqish"
        send(chat, "Qaysi kitoblarni yoqtirasiz? Tanlang yoki o'zingiz yozing:",
             kb(ustunlar(JANRLAR) + [[BTN_BEKOR]]))
        return

    if qadam == "qiziqish":
        if not text or len(text) > 60 or text.startswith("/"):
            send(chat, "Janrni tanlang yoki qisqacha yozing.")
            return
        q["qiziqish"] = text
        yangi = not u.get("royxat")
        u.update(q)
        u["royxat"] = u.get("royxat") or int(time.time())
        u.pop("vaqtincha", None)
        u.pop("qadam", None)
        send(chat, "✅ <b>Ro'yxatdan o'tdingiz!</b>\n\n%s\n\n"
                   "Juma aksiyasini bir hafta oldin shu yerga yozamiz. "
                   "Botni o'chirib qo'ymang 🙂" % profil(u), menyu(chat, db))
        if yangi:
            for a in ADMINS:
                send(a, "🆕 Yangi mijoz (%d-chi):\n%s" % (
                    sum(1 for x in db["users"].values() if x.get("royxat")), profil(u)))
        keyin = u.pop("keyin", None)
        p = next((p for p in db["promos"] if p["id"] == keyin), None)
        if p and korinadi(p):
            aksiya_yubor(db, chat, p, u)
        return


def profil(u):
    return ("👤 %s %s\n📱 %s\n🎂 %s yosh\n📚 %s" % (
        escape(u.get("ism", "")), escape(u.get("familiya", "")),
        escape(u.get("telefon", "")), u.get("yosh", "?"),
        escape(u.get("qiziqish", ""))))


# ---------------------------------------------------------------- aksiya qo'shish (do'kon egasi)
def bosh_jumalar(db):
    band = {p["sana"] for p in db["promos"]}
    return [d for d in jumalar(10) if d.isoformat() not in band]


def aksiya_qadam(chat, u, msg, text, db):
    qadam = u["qadam"]
    q = u.setdefault("vaqtincha", {})

    if qadam == "a_sana":
        d = sana_oqi(text.split(" ")[0].replace("📅", "").strip()) if text else None
        if not d:
            m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", text or "")
            d = date.fromisoformat(m.group(1)) if m else None
        if not d:
            send(chat, "Sanani tugmadan tanlang yoki yozing: <i>2026-10-02</i> yoki <i>02.10.2026</i>.")
            return
        if d.weekday() != 4:
            send(chat, "%s — juma emas. Juma kunini tanlang." % sana_matn(d))
            return
        if d < bugun():
            send(chat, "Bu sana o'tib ketgan.")
            return
        if any(p["sana"] == d.isoformat() for p in db["promos"]):
            send(chat, "Bu jumaga aksiya bor. Avval uni o'chiring (📋 Aksiyalar).")
            return
        q["sana"] = d.isoformat()
        u["qadam"] = "a_kitob"
        qoldi = (d - bugun()).days
        ogoh = ""
        if qoldi < EGA_OLDIN:
            ogoh = ("\n⚠️ Aksiyagacha %d kun qoldi — odatda 4 hafta oldin "
                    "rejalashtirgan ma'qul." % qoldi)
        send(chat, "📅 %s, juma.%s\n\nKitob nomini yozing (masalan: <i>Muqaddima</i>):"
             % (sana_matn(d), ogoh), kb([[BTN_BEKOR]]))
        return

    if qadam == "a_kitob":
        if not text or len(text) > 120 or text.startswith("/"):
            send(chat, "Kitob nomini yozing.")
            return
        q["kitob"] = text
        u["qadam"] = "a_rasm"
        send(chat, "Kitob muqovasining rasmini yuboring — mijozlar e'londa ko'radi:",
             kb([[BTN_RASMSIZ], [BTN_BEKOR]]))
        return

    if qadam == "a_rasm":
        if msg.get("photo"):
            q["rasm"] = msg["photo"][-1]["file_id"]
        elif text != BTN_RASMSIZ:
            send(chat, "Rasm yuboring yoki «%s» tugmasini bosing." % BTN_RASMSIZ)
            return
        u["qadam"] = "a_janr"
        send(chat, "Kitob janri? (shu janrni yoqtirganlarga alohida belgi qo'yamiz)",
             kb([[HAMMA]] + ustunlar(JANRLAR) + [[BTN_BEKOR]]))
        return

    if qadam == "a_janr":
        if not text:
            return
        q["janr"] = text
        u["qadam"] = "a_odatiy"
        send(chat, "Kitobning <b>odatiy</b> (do'kondagi) narxi qancha? "
                   "Masalan: <i>150000</i>.", kb([[BTN_BEKOR]]))
        return

    if qadam == "a_odatiy":
        n = son(text)
        if not n:
            send(chat, "Narxni raqam bilan yozing, masalan: <i>150000</i>.")
            return
        q["odatiy"] = n
        u["qadam"] = "a_tannarx"
        send(chat, "Kitobning <b>tannarxi</b> (o'zingizga necha pulga tushadi)? "
                   "Buni mijozlar ko'rmaydi.")
        return

    if qadam == "a_tannarx":
        n = son(text)
        if not n:
            send(chat, "Tannarxni raqam bilan yozing, masalan: <i>120000</i>.")
            return
        if n >= q["odatiy"]:
            send(chat, "Tannarx (%s) odatiy narxdan (%s) kam emas — bu kitobni "
                       "zararsiz arzonlashtirib bo'lmaydi. Boshqa kitob tanlang yoki "
                       "tannarxni qayta yozing:" % (som(n), som(q["odatiy"])))
            return
        q["tannarx"] = n
        u["qadam"] = "a_narx"
        # Odatiy narxdan ~10% arzon, mingga yaxlitlab; tannarxdan past emas.
        tavsiya = max(n, q["odatiy"] * (100 - CHEGIRMA_TAVSIYA) // 100 // 1000 * 1000)
        send(chat, "Juma kuni qanchaga sotamiz? Odatiy narxdan (%s) <b>arzon</b>, "
                   "lekin tannarxdan (%s) <b>arzon emas</b> — tugmani bosing yoki "
                   "o'zingiz yozing:" % (som(q["odatiy"]), som(n)),
             kb([["%s" % som(tavsiya)], [BTN_BEKOR]]))
        return

    if qadam == "a_narx":
        n = son(text)
        if not n:
            send(chat, "Narxni raqam bilan yozing.")
            return
        if n < q["tannarx"]:
            send(chat, "Bu narx tannarxdan (%s) past — zarar bo'ladi. Aksiya narxi "
                       "tannarxdan arzon bo'lmasligi kerak. Qaytadan yozing:"
                 % som(q["tannarx"]))
            return
        if n >= q["odatiy"]:
            send(chat, "Bu narx odatiy narxdan (%s) arzon emas — aksiya bo'lmaydi. "
                       "Qaytadan yozing:" % som(q["odatiy"]))
            return
        q["narx"] = n
        q["soni"] = AKSIYA_SONI
        u["qadam"] = "a_tasdiq"
        n = q["narx"]
        f = n - q["tannarx"]
        foiz = chegirma_foiz(q)
        ogoh = ("\n⚠️ Chegirma %.0f%% — katta. Ishonchingiz komilmi?" % foiz
                if foiz > CHEGIRMA_OGOH else "")
        jami = ("\nHammasi sotilsa, jami foyda: %s" % som(f * q["soni"])) if q["soni"] else ""
        send(chat, "Tekshiring:\n\n📅 %s, juma\n📖 %s\n📚 %s\n🖼 %s\n"
                   "Odatiy narx: %s\nTannarx: %s\nAksiya narxi: <b>%s</b> (−%.0f%%)\n"
                   "Soni: %s\nBitta kitobdan foyda: %s%s%s\n\nSaqlaymizmi?"
             % (sana_matn(date.fromisoformat(q["sana"])), escape(q["kitob"]),
                escape(q["janr"]), "rasm bor" if q.get("rasm") else "rasmsiz",
                som(q["odatiy"]), som(q["tannarx"]), som(n), foiz,
                q["soni"] or "cheklanmagan", som(f), jami, ogoh),
             kb([[BTN_HA, BTN_YOQ]]))
        return

    if qadam == "a_tasdiq":
        u.pop("qadam", None)
        if text != BTN_HA:
            u.pop("vaqtincha", None)
            send(chat, "Bekor qilindi.", menyu(chat, db))
            return
        db["seq"] += 1
        p = dict(q, id=db["seq"], qoshgan=chat, vaqt=int(time.time()))
        db["promos"].append(p)
        u.pop("vaqtincha", None)
        qoldi = (date.fromisoformat(p["sana"]) - bugun()).days
        if qoldi <= EGA_OLDIN:
            db["sent"]["%d:ega" % p["id"]] = int(time.time())
        mijoz_kuni = date.fromisoformat(p["sana"]) - timedelta(days=MIJOZ_OLDIN)
        if qoldi <= MIJOZ_OLDIN:
            keyin = "Mijozlarga e'lon keyingi tekshiruvda (bir necha daqiqada) yuboriladi."
        else:
            keyin = "Mijozlarga %s kuni e'lon qilinadi." % sana_matn(mijoz_kuni)
        send(chat, "✅ Aksiya #%d saqlandi.\n%s" % (p["id"], keyin), menyu(chat, db))
        return


def aksiyalar_royxati(chat, db):
    ps = kelgusi(db)
    if not ps:
        send(chat, "Rejalashtirilgan aksiya yo'q. «%s» tugmasini bosing." % BTN_QOSH,
             menyu(chat, db))
        return
    lines = ["<b>Rejalashtirilgan aksiyalar</b>\n"]
    for p in ps:
        d = date.fromisoformat(p["sana"])
        qoldi = (d - bugun()).days
        holat = ("mijozlar biladi" if qoldi <= MIJOZ_OLDIN
                 else "mijozlarga %d kundan keyin e'lon" % (qoldi - MIJOZ_OLDIN))
        soni = "%d/%s buyurtma" % (band_soni(db, p), p.get("soni") or "∞")
        lines.append("#%d · 📅 %s (%d kun) — <b>%s</b>\n   %s → %s (−%.0f%%), foyda %s/dona · %s · %s"
                     % (p["id"], sana_matn(d), qoldi, escape(p["kitob"]),
                        som(p["odatiy"]), som(p["narx"]), chegirma_foiz(p),
                        som(foyda(p)), soni, holat))
    bosh = [d for d in bosh_jumalar(db) if 0 < (d - bugun()).days <= EGA_OLDIN + 7]
    if bosh:
        lines.append("\n⚠️ Aksiyasiz jumalar: " + ", ".join(sana_matn(d) for d in bosh))
    lines.append("\nO'chirish: <code>/ochir 3</code>")
    send_long(chat, lines, menyu(chat, db))


def mijozlar(chat, db):
    us = [u for u in db["users"].values() if u.get("royxat")]
    if not us:
        send(chat, "Hali hech kim ro'yxatdan o'tmagan.", menyu(chat, db))
        return
    janr = {}
    for u in us:
        janr[u.get("qiziqish", "?")] = janr.get(u.get("qiziqish", "?"), 0) + 1
    lines = ["<b>Mijozlar: %d ta</b>" % len(us)]
    bloklagan = sum(1 for u in us if u.get("bloklagan"))
    if bloklagan:
        lines.append("(botni o'chirganlar: %d)" % bloklagan)
    lines.append("\n<b>Qiziqishlar:</b>")
    for k, v in sorted(janr.items(), key=lambda x: -x[1]):
        lines.append("  %s — %d" % (escape(k), v))
    lines.append("\n<b>Ro'yxat:</b>")
    for i, u in enumerate(sorted(us, key=lambda x: x["royxat"]), 1):
        lines.append("%d. %s %s, %s yosh, %s — %s" % (
            i, escape(u.get("ism", "")), escape(u.get("familiya", "")), u.get("yosh", "?"),
            escape(u.get("telefon", "")), escape(u.get("qiziqish", ""))))
    send_long(chat, lines, menyu(chat, db))


def hammaga(db, yubor):
    """Ro'yxatdan o'tgan har bir mijozga yubor(chat, u) orqali xabar yuboradi."""
    yuborildi = 0
    for chat, u in db["users"].items():
        if not u.get("royxat") or u.get("bloklagan"):
            continue
        r = yubor(chat, u)
        if r.get("ok"):
            yuborildi += 1
        elif r.get("error_code") == 403:          # botni o'chirib qo'ygan
            u["bloklagan"] = int(time.time())
        time.sleep(0.05)                           # Telegram cheklovi: ~30 xabar/soniya
    return yuborildi


# ---------------------------------------------------------------- buyurtma (mijoz)
def oldindan_tolov(jami):
    """Jami narxning yarmi, mingga yuqoriga yaxlitlangan (180 500 → 181 000)."""
    return min(jami, -(-(jami // 2) // 1000) * 1000)


def buyurtma_boshla(chat, u, pid, db):
    p = next((p for p in db["promos"] if p["id"] == pid), None)
    if not p or not korinadi(p):
        send(chat, "Bu aksiya tugagan.", menyu(chat, db))
        return
    if not royxatda(db, chat):
        u["keyin"] = pid
        u["qadam"] = "ism"
        u["vaqtincha"] = {}
        send(chat, "Kitobni band qilish uchun avval ro'yxatdan o'ting.\n\nIsmingizni yozing:",
             kb([[BTN_BEKOR]]))
        return
    q = qolgan(db, p)
    if q == 0:
        send(chat, tugadi_matn(p), menyu(chat, db))
        return
    eng_kop = min(BIR_KISHIGA, q) if q is not None else BIR_KISHIGA
    u["qadam"] = "b_soni"
    u["vaqtincha"] = {"promo": pid}
    send(chat, "📖 <b>%s</b> — %s\n📦 Qoldi: %s ta\n\nNechta kitob band qilasiz?\n"
               "Band qilish uchun kitob pulining <b>yarmini</b> oldindan to'laysiz, "
               "qolgan yarmini — juma kuni kitobni olganda."
         % (escape(p["kitob"]), som(p["narx"]), q if q is not None else "ko'p"),
         kb([[str(i) for i in range(1, eng_kop + 1)], [BTN_BEKOR]]))


def buyurtma_qadam(chat, u, msg, text, db):
    qadam = u["qadam"]
    q = u.setdefault("vaqtincha", {})
    p = next((p for p in db["promos"] if p["id"] == q.get("promo")), None)
    if not p or not korinadi(p):
        u.pop("qadam", None)
        u.pop("vaqtincha", None)
        send(chat, "Bu aksiya tugagan.", menyu(chat, db))
        return

    if qadam == "b_soni":
        n = son(text)
        qol = qolgan(db, p)
        eng_kop = min(BIR_KISHIGA, qol) if qol is not None else BIR_KISHIGA
        if not n or n > eng_kop:
            send(chat, "1 dan %d gacha son tanlang." % eng_kop)
            return
        q["soni"] = n
        q["jami"] = n * p["narx"]
        q["oldindan"] = oldindan_tolov(q["jami"])
        if TOLOV_KARTA:
            u["qadam"] = "b_chek"
            send(chat, "Jami: %s\nOldindan to'lov (yarmi): <b>%s</b>\n\n"
                       "💳 <code>%s</code> kartasiga <b>%s</b> o'tkazing va "
                       "<b>chek rasmini</b> (skrinshot) shu yerga yuboring:"
                 % (som(q["jami"]), som(q["oldindan"]), escape(TOLOV_KARTA),
                    som(q["oldindan"])),
                 kb([[BTN_BEKOR]]))
            return
        u["qadam"] = "b_tasdiq"
        buyurtma_korsat(chat, u, p)
        return

    if qadam == "b_chek":
        if not msg.get("photo"):
            send(chat, "To'lov chekining <b>rasmini</b> yuboring (skrinshot). "
                       "Chek bo'lmasa, kitob band qilinmaydi.")
            return
        q["chek"] = msg["photo"][-1]["file_id"]
        u["qadam"] = "b_tasdiq"
        buyurtma_korsat(chat, u, p)
        return

    if qadam == "b_tasdiq":
        if text != BTN_TASDIQ:
            send(chat, "«%s» tugmasini bosing yoki bekor qiling." % BTN_TASDIQ)
            return
        u.pop("qadam", None)
        u.pop("vaqtincha", None)
        qol = qolgan(db, p)
        if qol is not None and q["soni"] > qol:
            send(chat, ("😔 Kechirasiz, shu orada %d ta kitob qoldi, siz %d ta so'radingiz. "
                        "Kamroq band qiling." % (qol, q["soni"])) if qol else tugadi_matn(p),
                 menyu(chat, db))
            return
        db["oseq"] += 1
        o = {"id": db["oseq"], "chat": chat, "promo": p["id"], "soni": q["soni"],
             "narx": p["narx"], "tannarx": p["tannarx"], "odatiy": p["odatiy"],
             "jami": q["jami"], "oldindan": q["oldindan"], "chek": q.get("chek"),
             "holat": "kutilmoqda", "vaqt": int(time.time())}
        db["orders"].append(o)
        if o["chek"]:
            keyin = "Do'kon chekni tekshirib, bronni tasdiqlagach xabar beramiz."
        else:
            keyin = ("Oldindan to'lovni (%s) do'konga kelib to'lang — shundan keyin "
                     "bron tasdiqlanadi." % som(o["oldindan"]))
        send(chat, "📌 <b>Bron #%d qabul qilindi!</b>\n\n📖 %s × %d = %s\n"
                   "💳 Oldindan: %s · juma kuni: %s\n📅 %s, juma kuni do'kondan olasiz.\n\n%s"
             % (o["id"], escape(p["kitob"]), o["soni"], som(o["jami"]),
                som(o["oldindan"]), som(o["jami"] - o["oldindan"]),
                sana_matn(date.fromisoformat(p["sana"])), keyin), menyu(chat, db))
        for a in ADMINS:
            buyurtma_adminga(a, o, db)
        return


def buyurtma_korsat(chat, u, p):
    q = u["vaqtincha"]
    send(chat, "Tekshiring:\n\n👤 %s %s\n📱 %s\n📖 %s × %d\n💰 Jami: <b>%s</b>\n"
               "💳 Oldindan (yarmi): <b>%s</b> — %s\n💵 Juma kuni to'lanadi: %s\n"
               "📅 Olish: %s, juma"
         % (escape(u.get("ism", "")), escape(u.get("familiya", "")),
            escape(u.get("telefon", "")), escape(p["kitob"]), q["soni"],
            som(q["jami"]), som(q["oldindan"]),
            "chek yuborildi" if q.get("chek") else "do'konga kelib to'lanadi",
            som(q["jami"] - q["oldindan"]), sana_matn(date.fromisoformat(p["sana"]))),
         kb([[BTN_TASDIQ], [BTN_BEKOR]]))


def buyurtma_matn(o, db):
    u = db["users"].get(o["chat"], {})
    p = next((p for p in db["promos"] if p["id"] == o["promo"]), {"kitob": "?"})
    jami = o.get("jami", o["soni"] * o["narx"])
    oldindan = o.get("oldindan", 0)
    return ("📌 <b>Bron #%d</b> · %s\n👤 %s %s · %s\n📖 %s × %d = %s\n"
            "💳 Oldindan: %s (%s) · juma kuni: %s"
            % (o["id"], HOLAT[o["holat"]], escape(u.get("ism", "")),
               escape(u.get("familiya", "")), escape(u.get("telefon", "")),
               escape(p["kitob"]), o["soni"], som(jami), som(oldindan),
               "chek bor" if o.get("chek") else "do'konda to'laydi", som(jami - oldindan)))


def buyurtma_adminga(a, o, db):
    tugma = (inline([[("✅ To'lov keldi", "ok:%d" % o["id"]), ("❌ Rad", "no:%d" % o["id"])]])
             if o["holat"] == "kutilmoqda" else None)
    if o.get("chek"):
        send_photo(a, o["chek"], buyurtma_matn(o, db), tugma)
    else:
        send(a, buyurtma_matn(o, db), tugma)


def buyurtmalarim(chat, db):
    os_ = [o for o in db["orders"] if o["chat"] == chat][-10:]
    if not os_:
        send(chat, "Sizda hali bron yo'q. «%s» tugmasini bosing." % BTN_AKSIYA,
             menyu(chat, db))
        return
    send_long(chat, [buyurtma_matn(o, db) + "\n" for o in reversed(os_)], menyu(chat, db))


def buyurtmalar(chat, db):
    kut = [o for o in db["orders"] if o["holat"] == "kutilmoqda"]
    tas = [o for o in db["orders"] if o["holat"] == "tasdiqlandi"]
    send(chat, "📦 Bronlar: ⏳ %d ta to'lovi tekshirilmoqda, ✅ %d ta band qilingan."
         % (len(kut), len(tas)), menyu(chat, db))
    for o in kut[:20]:
        buyurtma_adminga(chat, o, db)
    if len(kut) > 20:
        send(chat, "…yana %d ta. Bularni ko'rib chiqqach, qayta bosing." % (len(kut) - 20))


def callback(cq, db):
    chat = str(cq["from"]["id"])
    data = cq.get("data") or ""
    javob = None
    turi, _, raqam = data.partition(":")
    n = son(raqam)

    if turi == "buy":
        u = db["users"].setdefault(chat, {"id": chat, "since": int(time.time())})
        buyurtma_boshla(chat, u, n, db)

    elif turi in ("ok", "no") and chat in ADMINS:
        o = next((o for o in db["orders"] if o["id"] == n), None)
        if not o:
            javob = "Bron topilmadi"
        elif o["holat"] != "kutilmoqda":
            javob = "Allaqachon: " + HOLAT[o["holat"]]
        else:
            o["holat"] = "tasdiqlandi" if turi == "ok" else "rad"
            o["kim"] = chat
            o["hal"] = int(time.time())
            p = next((p for p in db["promos"] if p["id"] == o["promo"]), {"kitob": "?", "sana": ""})
            jami = o.get("jami", o["soni"] * o["narx"])
            if turi == "ok":
                send(o["chat"], "✅ <b>Bron #%d tasdiqlandi!</b> Kitob siz uchun band.\n"
                                "📖 %s × %d\n💳 Oldindan to'lov qabul qilindi: %s\n"
                                "💵 Juma kuni to'laysiz: %s\n📅 %s, juma kuni do'konga keling."
                     % (o["id"], escape(p["kitob"]), o["soni"], som(o.get("oldindan", 0)),
                        som(jami - o.get("oldindan", 0)),
                        sana_matn(date.fromisoformat(p["sana"])) if p["sana"] else "juma"))
            else:
                send(o["chat"], "❌ Bron #%d tasdiqlanmadi (to'lov topilmadi). Savol "
                                "bo'lsa, do'kon bilan bog'laning." % o["id"])
            javob = HOLAT[o["holat"]]
            msg = cq.get("message") or {}
            if msg:
                call("editMessageReplyMarkup", chat_id=msg["chat"]["id"],
                     message_id=msg["message_id"], reply_markup={"inline_keyboard": []})
                send(chat, "#%d → %s" % (o["id"], HOLAT[o["holat"]]))

    call("answerCallbackQuery", callback_query_id=cq["id"], text=javob)


def bron_eslatma(p, os_, bosqich, db):
    qachon = "ertaga" if bosqich == 1 else "bugun"
    soni = sum(o["soni"] for o in os_)
    jami = sum(o.get("jami", o["soni"] * o["narx"]) for o in os_)
    oldindan = sum(o.get("oldindan", 0) for o in os_ if o["holat"] == "tasdiqlandi")
    lines = ["⏰ <b>Eslatma: %s — juma!</b>" % qachon.capitalize(), "",
             "📌 Siz band qilgan kitob: <b>%s</b> × %d" % (escape(p["kitob"]), soni),
             "💳 Oldindan to'langan: %s" % som(oldindan),
             "💵 Kitobni olganda to'laysiz: <b>%s</b>" % som(jami - oldindan)]
    if any(o["holat"] == "kutilmoqda" for o in os_):
        lines.append("\n⏳ Oldindan to'lovingiz hali tasdiqlanmagan — do'kon tekshirmoqda.")
    lines.append("\nKitobingiz siz uchun ajratib qo'yilgan. %s do'konga keling! 📚"
                 % qachon.capitalize())
    return "\n".join(lines)


# ---------------------------------------------------------------- marketing tahlili
def hafta_boshi(d):
    return d - timedelta(days=d.weekday())


def ustun(n, eng, eni=10):
    if not eng:
        return ""
    return "▇" * max(1 if n else 0, round(eni * n / eng))


def marketing(chat, db):
    b = bugun()
    us = [u for u in db["users"].values() if u.get("royxat")]
    tas = [o for o in db["orders"] if o["holat"] == "tasdiqlandi"]
    kut = [o for o in db["orders"] if o["holat"] == "kutilmoqda"]
    sotildi = sum(o["soni"] for o in tas)
    tushum = sum(o["soni"] * o["narx"] for o in tas)
    sof = sum(o["soni"] * (o["narx"] - o["tannarx"]) for o in tas)
    chegirma = sum(o["soni"] * (o.get("odatiy", o["narx"]) - o["narx"]) for o in tas)
    haftada = hafta_boshi(b)
    yangi = sum(1 for u in us
                if datetime.fromtimestamp(u["royxat"], TOSHKENT).date() >= haftada)
    olganlar = {o["chat"] for o in tas}
    konv = 100.0 * len(olganlar) / len(us) if us else 0
    qaytgan = sum(1 for c in olganlar
                  if len({o["promo"] for o in tas if o["chat"] == c}) > 1)

    lines = [
        "📊 <b>Marketing tahlili</b>\n",
        "👥 Mijozlar: <b>%d</b> (bu hafta +%d)" % (len(us), yangi),
        "🧾 Buyurtmalar: <b>%d</b> tasdiqlangan, %d kutilmoqda" % (len(tas), len(kut)),
        "📚 Sotilgan kitoblar: <b>%d</b>" % sotildi,
        "💰 Tushum: <b>%s</b>" % som(tushum),
        "📈 Foyda (tannarxdan tashqari): <b>%s</b>" % som(sof),
        "🏷 Mijozlarga berilgan chegirma: <b>%s</b>" % som(chegirma),
        "🎯 Buyurtma bergan mijozlar: %d (%.0f%%), qayta kelganlar: %d"
        % (len(olganlar), konv, qaytgan),
    ]

    # Haftalik grafik: yangi mijozlar va sotilgan kitoblar (8 hafta).
    haftalar = [haftada - timedelta(weeks=i) for i in range(7, -1, -1)]
    mij = {h: 0 for h in haftalar}
    sot = {h: 0 for h in haftalar}
    for u in us:
        h = hafta_boshi(datetime.fromtimestamp(u["royxat"], TOSHKENT).date())
        if h in mij:
            mij[h] += 1
    for o in tas:
        h = hafta_boshi(datetime.fromtimestamp(o["vaqt"], TOSHKENT).date())
        if h in sot:
            sot[h] += o["soni"]
    em, es = max(mij.values()), max(sot.values())
    grafik = ["Hafta    Mijoz          Sotuv"]
    for h in haftalar:
        grafik.append("%-8s %-10s%3d  %-10s%3d" % (
            "%d.%02d" % (h.day, h.month), ustun(mij[h], em), mij[h],
            ustun(sot[h], es), sot[h]))
    lines.append("\n<b>Haftalik (8 hafta)</b>\n<pre>%s</pre>" % escape("\n".join(grafik)))

    otgan = sorted((p for p in db["promos"] if p["sana"] <= b.isoformat()),
                   key=lambda p: p["sana"])[-6:]
    if otgan:
        lines.append("<b>Oxirgi aksiyalar</b>")
        for p in otgan:
            n = sum(o["soni"] for o in tas if o["promo"] == p["id"])
            lines.append("📅 %s — %s: %d ta sotildi, foyda %s"
                         % (sana_matn(date.fromisoformat(p["sana"])), escape(p["kitob"]),
                            n, som(n * foyda(p))))

    janr = {}
    for u in us:
        janr[u.get("qiziqish", "?")] = janr.get(u.get("qiziqish", "?"), 0) + 1
    if janr:
        lines.append("\n<b>Mijozlar nimani yoqtiradi</b>")
        for k, v in sorted(janr.items(), key=lambda x: -x[1])[:5]:
            lines.append("%s — %d" % (escape(k), v))
    send_long(chat, lines, menyu(chat, db))


# ---------------------------------------------------------------- eslatmalar
def eslatmalar(db):
    """Har ishga tushganda chaqiriladi; har eslatma faqat bir marta ketadi."""
    if datetime.now(TOSHKENT).hour < ESLATMA_SOAT:
        return
    b = bugun()
    sent = db["sent"]

    for p in kelgusi(db):
        d = date.fromisoformat(p["sana"])
        qoldi = (d - b).days
        pid = p["id"]

        # Do'kon egasi — 4 hafta oldin: kitobni tayyorlash vaqti.
        if qoldi <= EGA_OLDIN and "%d:ega" % pid not in sent:
            for a in ADMINS:
                send(a, "📦 <b>Aksiyaga %d kun qoldi</b> (%s, juma)\n\n📖 %s\n"
                        "Aksiya narxi: %s, tannarx: %s\n\n"
                        "Kitobni yetarlicha buyurtma qilib qo'ying. Mijozlarga "
                        "%s kuni e'lon qilinadi."
                     % (qoldi, sana_matn(d), escape(p["kitob"]), som(p["narx"]),
                        som(p["tannarx"]), sana_matn(d - timedelta(days=MIJOZ_OLDIN))))
            sent["%d:ega" % pid] = int(time.time())

        # Do'kon egasi — mijozlarga e'lon ketishidan bir kun oldin.
        if qoldi == MIJOZ_OLDIN + 1 and "%d:ega8" % pid not in sent:
            for a in ADMINS:
                send(a, "🔔 Ertaga mijozlarga «%s» aksiyasi e'lon qilinadi. "
                        "Kitob omborda yetarlimi?" % escape(p["kitob"]))
            sent["%d:ega8" % pid] = int(time.time())

        # Mijozlar — 7 kun, 1 kun oldin va juma kuni. Kech qo'shilgan aksiyada
        # faqat eng yaqin eslatma ketadi, oldingilari o'tkazib yuboriladi.
        if qoldi <= MIJOZ_OLDIN:
            bosqich = 0 if qoldi == 0 else 1 if qoldi == 1 else MIJOZ_OLDIN
            kalit = "%d:m%d" % (pid, bosqich)
            if kalit not in sent:
                for k in (MIJOZ_OLDIN, 1, 0):
                    if k >= bosqich:
                        sent.setdefault("%d:m%d" % (pid, k), int(time.time()))
                # Band qilganlarga — shaxsiy eslatma (1 kun oldin va juma kuni).
                bronlar = {}
                if bosqich < MIJOZ_OLDIN:
                    for o in db["orders"]:
                        if o["promo"] == pid and o["holat"] != "rad":
                            bronlar.setdefault(o["chat"], []).append(o)
                    for c, os_ in bronlar.items():
                        if not db["users"].get(c, {}).get("bloklagan"):
                            send(c, bron_eslatma(p, os_, bosqich, db))
                if bosqich < MIJOZ_OLDIN and qolgan(db, p) == 0:
                    continue                     # kitob tugagan — qayta eslatmaymiz
                n = hammaga(db, lambda c, u, p=p, b=bronlar:
                            {"ok": False} if c in b else aksiya_yubor(db, c, p, u))
                for a in ADMINS:
                    send(a, "📨 «%s» eslatmasi %d ta mijozga yuborildi." % (escape(p["kitob"]), n))

    # 4 hafta keyingi juma aksiyasiz bo'lsa — do'kon egasiga aytamiz.
    band = {p["sana"] for p in db["promos"]}
    for d in jumalar(6):
        qoldi = (d - b).days
        kalit = "bosh:" + d.isoformat()
        if 0 < qoldi <= EGA_OLDIN and d.isoformat() not in band and kalit not in sent:
            for a in ADMINS:
                send(a, "📅 <b>%s, juma</b> uchun aksiya hali yo'q (%d kun qoldi).\n"
                        "«%s» tugmasi bilan kitob tanlang." % (sana_matn(d), qoldi, BTN_QOSH))
            sent[kalit] = int(time.time())


# ---------------------------------------------------------------- xabarlarni qayta ishlash
def handle(msg, db):
    if msg["chat"].get("type") != "private":
        return
    chat = str(msg["chat"]["id"])
    text = (msg.get("text") or "").strip()
    user = msg.get("from", {})
    u = db["users"].setdefault(chat, {"id": chat, "since": int(time.time())})
    u["username"] = user.get("username", "")
    u.pop("bloklagan", None)               # yozdi — demak botni o'chirmagan

    if text == BTN_BEKOR or text.startswith("/start") or text == "/bekor":
        u.pop("qadam", None)
        u.pop("vaqtincha", None)
        if text.startswith("/start") and royxatda(db, chat):
            send(chat, "Assalomu alaykum, %s! <b>Kitoblar olamiga xush kelibsiz</b> 📚\n\n"
                       "Juma aksiyasini bir hafta oldin shu yerga yozamiz."
                 % escape(u.get("ism", "")), menyu(chat, db))
        elif text.startswith("/start"):
            send(chat, SALOM, menyu(chat, db))
        else:
            send(chat, "Bekor qilindi.", menyu(chat, db))
        return

    if text == "/men":
        send(chat, "Sizning Telegram ID: <code>%s</code>" % chat)
        return

    if text == "/ochir_meni":
        u.clear()
        u.update(id=chat, since=int(time.time()), ochirgan=int(time.time()))
        for o in db["orders"]:
            if o["chat"] == chat:
                o["chek"] = None
        send(chat, "🗑 Ma'lumotlaringiz (ism, familiya, telefon, yosh, qiziqish, "
                   "chek rasmlari) o'chirildi. Endi sizga eslatma kelmaydi.\n\n"
                   "Qaytmoqchi bo'lsangiz — /start.", menyu(chat, db))
        return

    qadam = u.get("qadam")
    if qadam and qadam.startswith("a_"):
        if chat in ADMINS:
            aksiya_qadam(chat, u, msg, text, db)
            return
        qadam = u.pop("qadam", None)
    if qadam and qadam.startswith("b_"):
        buyurtma_qadam(chat, u, msg, text, db)
        return
    if qadam:
        royxat_qadam(chat, u, msg, text, db)
        return

    if text in (BTN_ROYXAT, BTN_QAYTA) or text == "/royxat":
        u["qadam"] = "ism"
        u["vaqtincha"] = {}
        send(chat, "Ismingizni yozing:", kb([[BTN_BEKOR]]))
        return

    if text == BTN_MEN:
        if royxatda(db, chat):
            send(chat, profil(u), menyu(chat, db))
        else:
            send(chat, "Siz hali ro'yxatdan o'tmagansiz.", menyu(chat, db))
        return

    if text == BTN_BUYURTMALARIM or text == "/buyurtmalarim":
        buyurtmalarim(chat, db)
        return

    if text == BTN_AKSIYA or text == "/aksiya":
        yaqin = [p for p in kelgusi(db) if korinadi(p)]
        if yaqin:
            aksiya_yubor(db, chat, yaqin[0], u)
        else:
            send(chat, "Keyingi juma aksiyasi haqida bir hafta oldin xabar beramiz."
                       + ("" if royxatda(db, chat) else " Buning uchun ro'yxatdan o'ting 👇"),
                 menyu(chat, db))
        return

    # ---- do'kon egasi
    if chat in ADMINS:
        if text == BTN_QOSH or text == "/qosh":
            u["qadam"] = "a_sana"
            u["vaqtincha"] = {}
            tugmalar = ["📅 %s (%s)" % (sana_matn(d), d.isoformat()) for d in bosh_jumalar(db)[:8]]
            send(chat, "Qaysi juma? Tanlang yoki yozing (<i>2026-10-02</i>):",
                 kb(ustunlar(tugmalar) + [[BTN_BEKOR]]))
            return
        if text == BTN_ROYXAT_AKSIYA or text == "/aksiyalar":
            aksiyalar_royxati(chat, db)
            return
        if text == BTN_MIJOZLAR or text == "/mijozlar":
            mijozlar(chat, db)
            return
        if text == BTN_BUYURTMALAR or text == "/buyurtmalar":
            buyurtmalar(chat, db)
            return
        if text == BTN_MARKETING or text == "/marketing":
            marketing(chat, db)
            return
        if text.startswith("/ochir"):
            n = son(text)
            p = next((p for p in db["promos"] if p["id"] == n), None)
            if not p:
                send(chat, "Aksiya topilmadi. Raqamini «📋 Aksiyalar»dan oling: "
                           "<code>/ochir 3</code>")
                return
            if band_soni(db, p):
                send(chat, "Bu aksiyadan %d ta kitobga buyurtma bor — avval ularni rad eting "
                           "(«%s»)." % (band_soni(db, p), BTN_BUYURTMALAR))
                return
            db["promos"].remove(p)
            send(chat, "🗑 #%d «%s» o'chirildi." % (p["id"], escape(p["kitob"])),
                 menyu(chat, db))
            return
        if text.startswith("/xabar"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                send(chat, "Foydalanish: <code>/xabar Yangi kitoblar keldi!</code>")
                return
            body = escape(parts[1])
            send(chat, "Yuborildi: %d ta" % hammaga(
                db, lambda c, u: send(c, body, menyu(c, db))))
            return

    send(chat, "Pastdagi tugmalardan foydalaning 👇", menyu(chat, db))


def process(updates, db):
    last = None
    for upd in updates:
        last = upd["update_id"]
        msg = upd.get("message")
        try:                                            # bitta xato botni to'xtatmasin
            if msg:
                handle(msg, db)
            elif upd.get("callback_query"):
                callback(upd["callback_query"], db)
        except Exception as e:
            print("xato:", repr(e), file=sys.stderr)
    return last


def setup():
    r1 = call("setMyCommands", commands=[
        {"command": "start", "description": "Boshlash"},
        {"command": "royxat", "description": "Ro'yxatdan o'tish"},
        {"command": "aksiya", "description": "Juma aksiyasi"},
        {"command": "buyurtmalarim", "description": "Mening buyurtmalarim"},
        {"command": "men", "description": "Mening Telegram ID im"},
        {"command": "ochir_meni", "description": "Ma'lumotlarimni o'chirish"},
    ])
    r2 = call("setMyDescription", description=TAVSIF)
    r3 = call("setMyShortDescription", short_description="Har juma bitta kitob aksiya narxida 📚")
    r4 = call("setChatMenuButton", menu_button={"type": "commands"})
    me = call("getMe").get("result", {})
    print("bot: @%s" % me.get("username", "?"))
    print("buyruqlar:", r1.get("ok"), "| tavsif:", r2.get("ok"), r3.get("ok"),
          "| menyu:", r4.get("ok"))
    if not ADMINS:
        print("ogohlantirish: ADMIN_IDS bo'sh — do'kon egasi eslatma olmaydi.")
    return all(x.get("ok") for x in (r1, r2, r3, r4))


def main(argv):
    if not TOKEN:
        sys.exit("BOT_TOKEN o'zgaruvchisini kiriting.")
    db = load()

    if "--setup" in argv:
        sys.exit(0 if setup() else 1)

    if "--once" in argv:
        r = call("getUpdates", timeout=0, allowed_updates=["message", "callback_query"])
        last = process(r.get("result", []), db)
        if last is not None:
            call("getUpdates", offset=last + 1, timeout=0)
        eslatmalar(db)
        save(db)
        print("qayta ishlandi: %d ta, mijozlar: %d, aksiyalar: %d" % (
            len(r.get("result", [])),
            sum(1 for u in db["users"].values() if u.get("royxat")), len(kelgusi(db))))
        return

    setup()
    offset = 0
    print("Kitob olami boti ishga tushdi.")
    while True:
        r = call("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
        last = process(r.get("result", []), db)
        if last is not None:
            offset = last + 1
        eslatmalar(db)
        save(db)


if __name__ == "__main__":
    main(sys.argv[1:])
  
