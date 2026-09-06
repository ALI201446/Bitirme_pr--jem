"""
Google'ın resmi google-genai Python kütüphanesini kullanarak kullanıcının
serbest metinle verdiği cevapları analiz eder ve careers.json'daki meslek
listesinden en uygun olanları seçer.
API tamamen ücretsizdir: https://aistudio.google.com/apikey adresinden key alınır.
Resmi kütüphane kullanıyoruz çünkü yeni "AQ." formatındaki key'leri doğru
şekilde yönetiyor (ham HTTP isteklerinde bu key'ler sorun çıkarabiliyor).
"""
import os
import json
import time

from google import genai
from google.genai import types

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.6-flash"

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5

_client = None


def _get_client():
    global _client
    if _client is None and GEMINI_API_KEY:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def get_ai_recommendation(qa_pairs, careers):
    """
    qa_pairs: [(soru, cevap), ...] formatında kullanıcının sohbet cevapları.
    careers: careers.json içeriği (name, description, tags, skills alanlarıyla).

    Döner: {"recommended": ["Meslek Adı", ...], "reasons": {"Meslek Adı": "kısa gerekçe"},
            "comment": "genel yorum"} ya da hata durumunda None.
    """
    client = _get_client()
    if client is None:
        print("⚠️ GEMINI_API_KEY .env dosyasında bulunamadı.")
        return None

    career_list_text = "\n".join(
        f"- {c['name']}: {c['description']} (Beceriler: {', '.join(c['skills'])})"
        for c in careers
    )
    qa_text = "\n".join(f"Soru: {q}\nCevap: {a}" for q, a in qa_pairs)

    prompt = f"""Sen bir kariyer danışmanısın. Aşağıda bir kullanıcının kariyer keşif
sohbetindeki soru-cevapları var. Bu cevapları DİKKATLE ve TEK TEK analiz et.

ÖNEMLİ KURALLAR:
- Cevaplardaki KENDİNE ÖZGÜ, SPESİFİK detaylara odaklan (genel geçer kelimelere değil).
  Örneğin "insanlarla konuşmayı severim" gibi genel bir ifadeyle "insanlarla empati kurup
  onların duygusal sorunlarını çözmek isterim" arasındaki farkı ayırt et; ikincisi psikolog
  veya sosyal hizmet uzmanına, birincisi pazarlama veya satışa daha yakın olabilir.
- Her kullanıcı farklıdır. "Yazılım Geliştirici" veya "Girişimci" gibi genel/popüler
  meslekleri SADECE cevaplar gerçekten teknik/girişimcilik odaklıysa öner; varsayılan
  veya güvenli seçim olarak kullanma.
- 55 mesleklik listenin TAMAMINI göz önünde bulundur, sadece ilk aklına gelenleri değil.
- Kullanıcının cevaplarında öne çıkan EN AZ 2-3 farklı temayı (ör. yaratıcılık, bilim,
  insanlarla çalışma, el becerisi, risk alma vb.) tespit et ve önerilerini bu temaların
  KESİŞİMİNE göre seç, sadece tek bir temaya göre değil.

MESLEK LİSTESİ (55 meslek):
{career_list_text}

KULLANICI SOHBETİ:
{qa_text}

Kullanıcıya EN UYGUN 3 mesleği, SADECE yukarıdaki listeden seçerek öner. Listede
olmayan bir meslek uydurma. Yanıtını SADECE şu JSON formatında ver, başka hiçbir
metin ekleme:
{{
  "recommended": ["Meslek Adı 1", "Meslek Adı 2", "Meslek Adı 3"],
  "reasons": {{
    "Meslek Adı 1": "Bu kullanıcının hangi spesifik cevabına dayandığını belirten 1 cümlelik gerekçe",
    "Meslek Adı 2": "...",
    "Meslek Adı 3": "..."
  }},
  "comment": "Kullanıcıya hitaben 2-3 cümlelik samimi, motive edici genel bir yorum"
}}
"""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=1.1,
                    top_p=0.95,
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"⚠️ Gemini API hatası (deneme {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
            else:
                return None
    return None


def get_followup_answer(matched_careers, qa_pairs, user_question):
    """
    Kullanıcının önerilen meslekler hakkında sorduğu serbest metin soruya yanıt üretir.
    matched_careers: [(career_dict, reason_str), ...]
    qa_pairs: kullanıcının keşif sohbetindeki soru-cevapları (bağlam için)
    user_question: kullanıcının yazdığı takip sorusu

    Döner: yanıt metni (str) ya da hata durumunda None.
    """
    client = _get_client()
    if client is None:
        print("⚠️ GEMINI_API_KEY .env dosyasında bulunamadı.")
        return None

    careers_text = "\n".join(
        f"- {c['name']}: {c['description']} (Beceriler: {', '.join(c['skills'])}) — Gerekçe: {reason}"
        for c, reason in matched_careers
    )
    qa_text = "\n".join(f"Soru: {q}\nCevap: {a}" for q, a in qa_pairs)

    prompt = f"""Sen bir kariyer danışmanısın. Bir kullanıcıya daha önce aşağıdaki
mesleklerin önerildiği bir sohbet oldu. Şimdi kullanıcı bu meslekler hakkında
ek bir soru soruyor. Sorusuna doğal, samimi, bilgilendirici bir Türkçe yanıt ver.
Yanıtın 4-6 cümleyi geçmesin, gereksiz uzatma.

DAHA ÖNCE ÖNERİLEN MESLEKLER:
{careers_text}

KULLANICININ KEŞİF SOHBETİ (bağlam için):
{qa_text}

KULLANICININ ŞİMDİKİ SORUSU:
{user_question}
"""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.8),
            )
            return response.text.strip()
        except Exception as e:
            print(f"⚠️ Gemini API hatası - takip sorusu (deneme {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
            else:
                return None
    return None