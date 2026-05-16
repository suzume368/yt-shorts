"""
YouTube Shorts Otomasyonu
=========================
Tek komutla:
  - Gemini ile psikoloji/davranis bilimi script'i üretir
  - ElevenLabs ile İngilizce seslendirme yapar
  - Pexels'tan portre stok video çeker
  - FFmpeg ile 9:16 dikey video render eder (kelime kelime altyazılı)
  - YouTube'a Short olarak yükler

Kullanım:
  python shorts_automation.py             # tüm pipeline
  python shorts_automation.py --auth      # ilk seferki YouTube OAuth (sadece bir kez)
  python shorts_automation.py --no-upload # üretip yükleme (sandbox testleri için)
"""

import os
import sys
import json
import time
import random
import argparse
import subprocess
import base64
from pathlib import Path
from datetime import datetime, timedelta

# --------- 3rd-party imports (try-except for friendlier errors) ---------
try:
    import requests
    from dotenv import load_dotenv
    import google.generativeai as genai
    from elevenlabs.client import ElevenLabs as ElevenLabsClient
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError as e:
    print(f"[hata] Eksik paket: {e.name}")
    print("Kurulum: pip install google-generativeai elevenlabs google-auth google-auth-oauthlib "
          "google-api-python-client python-dotenv requests Pillow")
    sys.exit(1)


# --------- Config ---------
ROOT = Path(__file__).parent
ENV_PATH = ROOT / ".env"
CREDENTIALS_JSON = ROOT / "credentials.json"
TOKEN_JSON = ROOT / "token.json"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)
BRAND_DIR = ROOT / "brand"
FONTS_DIR = ROOT / "fonts"
ASSETS_DIR = ROOT / "assets"
MUSIC_PATH = ASSETS_DIR / "bg_music.mp3"  # Kevin MacLeod - Darkest Child (CC BY 3.0)

load_dotenv(ENV_PATH)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

VIDEO_W, VIDEO_H = 1080, 1920  # 9:16
TARGET_DURATION_RANGE = (28, 55)  # seconds
ELEVENLABS_VOICE_ID = "pqHfZKP75CvOlQylNhV4"  # Bill — deep male, Hindi-compatible (eleven_multilingual_v2)
# Alternative Hindi voices to try in ElevenLabs:
#   "nPczCjzI2devNBz1zQrb" — Brian (clear neutral male)
#   "onwK4e9ZLuTAKqWW03F9" — Daniel (authoritative)
#   "TX3LPaxmHKxFdv7VOQHJ" — Liam (energetic, hooks ke liye)
ELEVENLABS_MODEL = "eleven_multilingual_v2"  # Hindi natively support karta hai

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


# --------- 1. Generate script with Gemini ---------
def generate_fun_fact():
    """Returns dict: {script, title, description, tags, keyword}.

    Niche: Psychology / mind games / behavioral science. Curiosity-driven
    educational shorts about how the human mind actually works.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY .env'de yok")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash-lite")  # ücretsiz, hızlı

    topics = [
        # === Cognitive Biases — Dimag ke dhoke (12) ===
        "Zeigarnik effect: adhuri baatein raat ko neend kyun uda deti hain",
        "Dunning-Kruger: jo jitna kam jaanta hai wo utna zyada confident kyun hota hai",
        "Spotlight effect: log tumhare baare mein utna nahi sochte jitna tum samajhte ho",
        "Sunk cost fallacy: galat rishton aur galat kaamon mein log phansa kyun rehte hain",
        "Frequency illusion: nai cheez seekhne ke baad wo har jagah kyun dikhne lagti hai",
        "Affective forecasting: hamara dimag future khushi ke baare mein hamesha kyun jhooth bolta hai",
        "Peak-end rule: takleef deh experience accha yaad kyun rehta hai",
        "IKEA effect: khud banai cheez bekar hone par bhi itni pyaari kyun lagti hai",
        "False consensus effect: dimag kyun maanta hai ke sab tumse agree karte hain",
        "Hindsight bias: kuch hone ke baad kyun lagta hai ke yeh to hona hi tha",
        "Anchoring bias: pehla number sunne ke baad hum usse alag sochna kyun band kar dete hain",
        "Choice blindness: log apne hi liye gaye faisle ko defend kyun karte hain jo unhone liya hi nahi",

        # === Yadasht aur Perception — Memory ke raaz (8) ===
        "Jhoothi yadein: dimag aise waqiyat kaise bana leta hai jo hue hi nahi",
        "Google effect: internet hone se hamari yadasht kamzor kyun ho rahi hai",
        "Misinformation effect: ek lafz badalne se poora gawah ka bayan kyun badal jaata hai",
        "Change blindness: aankhon ke saamne kuch badal jaaye aur dikhta hi nahi",
        "Inattentional blindness: focus mein hone par saamne ka gorillla bhi kyun nazar nahi aata",
        "Illusory truth effect: baar baar suni baat jhooth hone par bhi sach kyun lagti hai",
        "Serial position effect: shuru aur aakhir ki baatein beech ki baatein se zyada yaad kyun rehti hain",
        "Memory reconsolidation: yaad karne se purani yaadein kaise badal jaati hain",

        # === Neend aur Sapne — Sleep psychology (6) ===
        "Sleep paralysis: raat ko andheri figure kamre mein kyun dikhti hai",
        "Lucid dreaming: sapne mein jaag jaana — science kya kehti hai",
        "Tetris effect: ek kaam baar baar karne ke baad sapnon mein kyun aane lagta hai",
        "REM rebound: neend rokne ke baad sapne zyada intense kyun ho jaate hain",
        "Dream-lag effect: purani emotional yadein din baad sapnon mein kyun aati hain",
        "Neend mein awaaz se seekhna: kya sona seekhne mein madad karta hai",

        # === Manipulation aur Persuasion — Log kaise uthate hain faayda (8) ===
        "Door-in-the-face: pehle badi cheez maango taake choti asaan lage — yeh kaise kaam karta hai",
        "Foot-in-the-door: choti request se shuru karo aur phir badi karo — manipulation trick",
        "Ben Franklin effect: kisi ki madad karne se tum use pasand karne lagte ho",
        "Reciprocity: ek choti gift lene ke baad hum zyada kyun dete hain",
        "Scarcity heuristic: limited offer sunke samajhdar log bhi kyun panic karte hain",
        "Dark patterns: apps kaisa design karte hain ke tum galti se kuch buy kar lo",
        "Social proof: bheed jahan jaaye hum kyun wahi jaana chahte hain",
        "Anchoring in negotiation: pehla number sunne wala negotiation mein kyun jeetta hai",

        # === Social Psychology — Insani fitrat (6) ===
        "Asch conformity: sach jaante hue bhi log bheed ke saath jhooth kyun bol dete hain",
        "Bystander effect: zyada log hone par help karne ki zimmedaari kyun kam ho jaati hai",
        "Pluralistic ignorance: sab andar se disagree karte hain par koi bolata kyun nahi",
        "Groupthink: aqalmand logon ka group milkar bewa qoof faisla kyun karta hai",
        "Milgram obedience: authority bolne par log dusron ko takleef dene ko kyun tayyar ho jaate hain",
        "Robbers Cave: do groups kuch dino mein dushman kyun ban jaate hain",

        # === Motivation aur Anxiety (8) ===
        "Learned helplessness: baar baar haarne ke baad koshish karna kyun band ho jaati hai",
        "Ironic process theory: kuch na sochne ki koshish karne par wo aur kyun aata hai",
        "Rumination trap: baar baar ek hi baat sochna depression ko kyun zinda rakhta hai",
        "Attentional residue: ek kaam chhod ke doosra karne par pehla dimag mein kyun rehta hai",
        "Parkinson's law: kaam hamesha diye gaye waqt tak kyun khench jaata hai",
        "Implementation intentions: sirf plan banana kaam kyun nahi karta — sahi tarika",
        "Dopamine aur anticipation: intezaar reward se zyada achha kyun lagta hai",
        "Uncertainty anxiety: na jaanne ka darr — dimag isko naqarar kyun nahi kar sakta",

        # === Aadat aur Laat — Habit science (6) ===
        "Variable rewards: instagram scroll karna cigarette jitna addictive kyun hai",
        "Dopamine prediction error: bekhabar reward dimag par zyada asar kyun karta hai",
        "Extinction burst: buri aadat todne se pehle wo aur buri kyun ho jaati hai",
        "Habit stacking: willpower ke bina nai aadat kaise daali jaaye",
        "Cue-reactivity: jagah dekhte hi craving kyun shuru ho jaati hai",
        "Streak psychology: apps mein streak todne ka itna darr kyun hota hai",

        # === Attraction aur Rishte (8) ===
        "Mere exposure effect: baar baar dikh ne wala insaan attractive kyun lagne lagta hai",
        "Misattribution of arousal: darr aur mohabbat ka dimag ek jaisa feel kyun karta hai",
        "Pratfall effect: kamyab log galti karne ke baad aur popular kyun ho jaate hain",
        "Halo effect: ek achai dekh kar baki sab bhi accha kyun lagte hain",
        "Reciprocity of liking: koi tumhe pasand kare to tum usse kyun pasand karne lagte ho",
        "Laal rang aur attraction: yeh rang first impression kyun badal deta hai",
        "Voice aur confidence: awaaz ki sirf pitch se log character kyun judge karte hain",
        "Hard-to-get paradox: door rehne se attraction badhta hai ya kam hota hai",

        # === Bachpan aur Parwarish (6) ===
        "Still-face experiment: maa ka chehra band karne par baby 60 second mein kyun ro deta hai",
        "Marshmallow test ki sach: willpower tha ya trust — research ne kya bataya",
        "Strange situation: 60 second ka test jo adult attachment predict karta hai",
        "Theory of mind: bacche kab samajhte hain ke dusron ka dimag alag hai",
        "Attachment styles: bachpan ka pyaar bada hoke rishton ko kaise affect karta hai",
        "Linguistic relativity: jo language bolte hain wo soch ko kaise shape karta hai",

        # === Personality aur Dark Traits (6) ===
        "Dark Triad: narcissism, manipulation aur psychopathy ek saath kaise kaam karte hain",
        "Narcissistic supply cycle: taarif ek drug ki tarah kyun kaam karti hai",
        "Imposter syndrome: kamyab log apni mehnat ko luck kyun samajhte hain",
        "Big Five: personality ke 5 traits jo zindagi ka sab kuch predict karte hain",
        "Gaslighting psychology: koi tumhari reality kyun aur kaise badal deta hai",
        "Empathy gap: theek hone ke baad bimari ka dard yaad kyun nahi rehta",

        # === Weird Neuroscience — Dimag ke ajeeb raaz (6) ===
        "Phantom limb: kaata hua haath dard kyun karta hai",
        "Capgras delusion: apne hi ghar walon ko copy samajhna — yeh bimari kya hai",
        "Synesthesia: kuch log awaaz sunne par rang kyun dekhte hain",
        "Blindsight: aandhon ki aankhein bhi kuch dekhti hain — science kya kehti hai",
        "Split-brain: do hisson mein bata hua dimag — ek haath doosre ko kyun nahi jaanta",
        "Mirror touch synesthesia: kisi aur ko chhua jaaye to yeh log feel kyun karte hain",
    ]
    topic_seed = os.getenv("TOPIC_SEED_OVERRIDE") or random.choice(topics)

    prompt = f"""Tum ek viral Hindi YouTube Shorts scriptwriter ho jo psychology aur dimag ki science ka channel chalate ho.
Channel ka naam: "Dimag Ki Baat" (ya isi tarah ka Hindi psychology channel).
Tone: exciting, mysterious, fast-paced, addictive. Viewer ko pehle 2 second mein rok lo.
Language: PURE HINDI — Hinglish allowed (English words jo Hindi mein common hain, jaise 'brain', 'experiment', 'stress').
Lekin script ki basa aur flow Hindi honi chahiye — English mein mat likho.

Topic seed: {topic_seed}

Script rules (MANDATORY):
- Opening hook MAXIMUM 8 words, ek sentence. Seedha, shocking, expectation todne wala.
  KABHI mat shuru karo "Kya aap jaante hain" se. Examples:
  "Aapka dimag abhi aapse jhooth bol raha hai.",
  "Yeh experiment ne psychology badal di.",
  "Aapki yadein asli nahi hain."
- Hook "!" ya "?" se khatam hona CHAHIYE.
- SIRF EK cliffhanger allowed hai poori script mein ("aur yahan se sab badal gaya...", "lekin twist yeh hai...").
- Bekar words bilkul nahi: "basically", "asliyat mein", "matlab", "toh", "waise" — sirf kaam ki baat.
- Sentences CHHOTE, SHARP, PUNCHY raho.
- Jo words ZYADA ZOR se bolne hain unhe CAPS mein likho (TTS narrator caps ko emphasis cue maanta hai —
  1-2 words per sentence, poora sentence caps mein mat karo).
- Koi slow intro nahi, koi "is video mein", koi "chaliye shuru karte hain" nahi. Seedha action se shuru.
- Real research ya named psychological effect use karo jab mumkin ho.
- Concrete examples abstractions se behtar hain. Delivery mein drama ho, facts galat mat karo.
- End karo punchline ke saath + yeh exact CTA: "Follow karo aur apne dimag ke aur raaz jaano."

Return ONLY valid JSON with these keys:
- "script": bolne wali Hindi script. STRICT length: MINIMUM 90 words, MAXIMUM 115 words.
  Yeh non-negotiable hai — count karke return karo. Hook-first, EK cliffhanger, zero filler.
  NO emojis, NO markdown, NO brackets mein sound effects, sirf plain Hindi text.
- "title": YouTube Shorts title, max 70 characters, curiosity-driven Hindi title, ends with #Shorts
- "description": 2 chhote Hindi sentences + 8 hashtags (#psychology #dimag #hindi in zaroor shamil karo)
- "tags": JSON array of 12 SEO tags (Hindi + English mix: psychology, dimag, brain, science, facts)
- "visual_keywords": JSON array of EXACTLY 4 specific, cinematic English stock-footage search
  terms tied to the script content. Each = alag scene, alag mood, topic se related.
  Use 2-4 word English phrases (Pexels English mein search karta hai).
  Example memory script ke liye: ["empty hospital corridor", "old photographs scattered",
  "rain on window at night", "elderly hand writing letter"]
- "keyword": fallback ONE English word for stock video search (e.g. "brain", "crowd", "mirror")
- "thumbnail_text": MAX 4 WORDS, ALL CAPS, hook ka sabse punchy version — Hindi ya Hinglish.
  Examples: "DIMAG KA DHOKA", "YEH EXPERIMENT DEKHLO", "YADEIN JHOOTHI HAIN".
  No emojis, no punctuation except hyphen. Thumbnail scale par readable hona chahiye.

Output JSON only, nothing else."""

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 1.1,
            "max_output_tokens": 800,
            "response_mime_type": "application/json",
        },
    )
    data = json.loads(response.text)
    print(f"[script] Topic: {data['keyword']}")
    print(f"[script] Title: {data['title']}")
    return data


# --------- 2. Generate TTS audio with subtitles ---------
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat Bold,80,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,5,0,2,40,40,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_time(s):
    """ASS time: H:MM:SS.cs (centiseconds, single-digit hour)."""
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s - h * 3600 - m * 60
    cs = int(round((sec - int(sec)) * 100))
    if cs == 100:
        cs = 0
        sec += 1
    return f"{h}:{m:02d}:{int(sec):02d}.{cs:02d}"


def _build_ass(cues, time_offset, ass_path):
    """Write libass-compatible .ass file. Every 3rd word (the 2nd in each group of 3)
    is yellow via inline {\\c} override; the rest inherit Default white. ffmpeg's
    subtitles= filter renders these overrides correctly (SRT swallows them)."""
    yellow = r"{\c&H0000D7FF&}"  # ASS BGR -> golden yellow
    reset = r"{\r}"
    lines = [ASS_HEADER]
    group_size = 3
    word_idx = 0
    for i in range(0, len(cues), group_size):
        group = cues[i:i + group_size]
        if not group:
            continue
        start_s = group[0].start.total_seconds() + time_offset
        end_s = group[-1].end.total_seconds() + time_offset
        parts = []
        for c in group:
            word = c.content.upper()
            if word_idx % 3 == 1:
                parts.append(f"{yellow}{word}{reset}")
            else:
                parts.append(word)
            word_idx += 1
        text_chunk = " ".join(parts)
        lines.append(
            f"Dialogue: 0,{_ass_time(start_s)},{_ass_time(end_s)},Default,,0,0,0,,{text_chunk}"
        )
    Path(ass_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


class _WordCue:
    def __init__(self, content, start_s, end_s):
        self.content = content
        self.start = timedelta(seconds=start_s)
        self.end = timedelta(seconds=end_s)


def _char_to_word_cues(characters, start_times, end_times):
    cues = []
    word_chars, word_start, word_end = [], 0.0, 0.0
    for char, start, end in zip(characters, start_times, end_times):
        if char in (" ", "\n", "\t"):
            if word_chars:
                cues.append(_WordCue("".join(word_chars), word_start, word_end))
                word_chars = []
        else:
            if not word_chars:
                word_start = start
            word_chars.append(char)
            word_end = end
    if word_chars:
        cues.append(_WordCue("".join(word_chars), word_start, word_end))
    return cues


def generate_voice(text, audio_path, ass_path, time_offset=0.0):
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY .env'de yok")
    client = ElevenLabsClient(api_key=ELEVENLABS_API_KEY)
    response = client.text_to_speech.convert_with_timestamps(
        voice_id=ELEVENLABS_VOICE_ID,
        text=text,
        model_id=ELEVENLABS_MODEL,
        output_format="mp3_44100_128",
    )
    Path(audio_path).write_bytes(base64.b64decode(response.audio_base_64))
    al = response.alignment
    cues = _char_to_word_cues(
        al.characters,
        al.character_start_times_seconds,
        al.character_end_times_seconds,
    )
    _build_ass(cues, time_offset, ass_path)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(out.stdout.strip())
    print(f"[voice] {duration:.1f}s ses uretildi -> {audio_path.name}")
    return duration


# --------- 3. Fetch portrait stock videos from Pexels ---------
def _pexels_search(headers, query, min_dur):
    """Returns (id, link, duration) tuple for the best portrait MP4 in `query`,
    or None if no usable result. sort=popular + size=large for cinematic clips."""
    params = {
        "query": query, "per_page": 15, "orientation": "portrait",
        "size": "large", "sort": "popular",
    }
    r = requests.get("https://api.pexels.com/videos/search",
                     headers=headers, params=params, timeout=30)
    r.raise_for_status()
    for v in r.json().get("videos", []):
        if v["duration"] < min_dur:
            continue
        for f in v["video_files"]:
            if f.get("file_type") == "video/mp4" and f.get("width", 0) >= 720:
                return v["id"], f["link"], v["duration"]
    return None


def fetch_pexels_clips(visual_keywords, fallback_keyword, n_clips=4,
                       min_duration_per_clip=5):
    """Returns list of (url, duration) tuples — one cinematic portrait clip per
    visual_keyword. Falls back to `fallback_keyword` for any query that returns
    nothing. De-duplicates by Pexels video id so no clip repeats."""
    if not PEXELS_API_KEY:
        raise RuntimeError("PEXELS_API_KEY .env'de yok")
    headers = {"Authorization": PEXELS_API_KEY}

    queries = list(visual_keywords)[:n_clips]
    while len(queries) < n_clips:
        queries.append(fallback_keyword)

    seen_ids = set()
    results = []
    for q in queries:
        attempts = [q, f"{q} cinematic", fallback_keyword,
                    f"{fallback_keyword} aesthetic cinematic", "aesthetic abstract"]
        chosen = None
        for attempt in attempts:
            hit = _pexels_search(headers, attempt, min_duration_per_clip)
            if hit and hit[0] not in seen_ids:
                chosen = hit
                break
        if chosen:
            seen_ids.add(chosen[0])
            results.append((chosen[1], chosen[2]))
            print(f"[pexels] '{q}' -> id={chosen[0]} ({chosen[2]}s)")
        else:
            print(f"[pexels] '{q}' icin uygun klip yok, atlaniyor")

    if not results:
        raise RuntimeError("Pexels'tan hicbir uygun klip alinamadi")
    return results


def download_file(url, dest):
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"[download] {dest.name}")


# --------- 4a. Generate thumbnail (1080x1920, branded) ---------
THUMB_FONT_CANDIDATES = [
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/ariblk.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Black.ttf",
]


def _pick_thumb_font(size):
    for path in THUMB_FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wrap_lines(text, font, max_width, draw):
    words = text.split()
    lines, current = [], ""
    for w in words:
        candidate = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def generate_thumbnail(bg_video_path, thumbnail_text, out_path, size=(1080, 1920)):
    """Branded thumbnail: blurred frame + chromatic aberration text + logo.
    Default 1080x1920 (in-video intro). Pass size=(1280, 720) for the YT custom
    thumbnail upload — YouTube's official spec is 16:9 1280x720, and the API
    silently rejects portrait thumbnails on some channels."""
    target_w, target_h = size
    workdir = Path(out_path).parent
    frame_path = workdir / f"_thumb_frame_{target_w}x{target_h}.png"
    cmd = ["ffmpeg", "-y", "-i", str(bg_video_path), "-vframes", "1",
           "-q:v", "2", str(frame_path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not frame_path.exists():
        print(res.stderr[-1000:])
        raise RuntimeError("Thumbnail icin frame cikarilamadi")

    img = Image.open(frame_path).convert("RGB")
    w, h = img.size
    target_ratio = target_w / target_h
    src_ratio = w / h
    if src_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    img = img.resize((target_w, target_h), Image.LANCZOS)
    img = img.filter(ImageFilter.GaussianBlur(radius=10))
    dark = Image.new("RGB", img.size, (0, 0, 0))
    img = Image.blend(img, dark, 0.45)
    img = img.convert("RGBA")

    text = (thumbnail_text or "").upper().strip() or "BRAIN STATIC"
    draw = ImageDraw.Draw(img)
    max_text_width = target_w - int(target_w * 0.15)
    font_size = max(80, min(220, target_h // 5))
    while font_size > 60:
        font = _pick_thumb_font(font_size)
        lines = _wrap_lines(text, font, max_text_width, draw)
        line_h = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
        total_h = len(lines) * (line_h + 24)
        widest = max((draw.textbbox((0, 0), ln, font=font)[2] for ln in lines), default=0)
        if widest <= max_text_width and total_h <= target_h * 0.55:
            break
        font_size -= 12
    font = _pick_thumb_font(font_size)
    lines = _wrap_lines(text, font, max_text_width, draw)
    line_h = font.getbbox("Ay")[3] - font.getbbox("Ay")[1]
    total_h = len(lines) * (line_h + 24)
    y = (target_h - total_h) // 2

    cyan = (0, 229, 255, 220)
    magenta = (255, 0, 128, 220)
    white = (255, 255, 255, 255)
    shift = max(4, font_size // 28)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (target_w - text_w) // 2
        draw.text((x - shift, y), line, font=font, fill=cyan)
        draw.text((x + shift, y), line, font=font, fill=magenta)
        draw.text((x, y + 4), line, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=font, fill=white)
        y += line_h + 24

    logo_path = BRAND_DIR / "profile.png"
    if logo_path.exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo_max = min(150, target_h // 8)
            logo.thumbnail((logo_max, logo_max), Image.LANCZOS)
            img.paste(logo, (60, target_h - logo.size[1] - 60), logo)
        except Exception as e:
            print(f"[thumb] logo eklenemedi: {e}")

    img.convert("RGB").save(out_path, "PNG", optimize=True)
    try:
        frame_path.unlink()
    except OSError:
        pass
    print(f"[thumb] Hazir -> {out_path.name} {target_w}x{target_h} ({font_size}px, {len(lines)} line)")


# --------- 4. Render final video with ffmpeg ---------
def render_video(bg_clips, audio_path, ass_path, audio_duration, output_path,
                 intro_thumbnail=None, intro_duration=1.2, music_path=None):
    """Concat 1..N portrait clips with crossfade transitions, overlay subs, mux audio.
    Subs are a real .ass file (V4+ Styles + per-word color overrides) so the yellow
    accent words actually render — SRT swallows ASS override tags but .ass keeps them.
    Each scene runs for ~total/N seconds (clamped to 5..15). xfade chain produces
    bg-chain length = sum(per_clip) - (N-1)*xfade_dur ≈ audio_duration + 0.5.

    If `intro_thumbnail` is given, prepend it as a silent intro of `intro_duration`
    seconds: viewers see the hook text while scrolling. Audio is delayed by
    intro_duration via adelay; the caller must also have built the .ass with
    matching time_offset so subs stay synced with voice."""
    if isinstance(bg_clips, (str, Path)):
        bg_clips = [Path(bg_clips)]
    bg_clips = [Path(c) for c in bg_clips]
    n = len(bg_clips)
    if n == 0:
        raise RuntimeError("render_video: hicbir klip verilmedi")

    has_intro = intro_thumbnail is not None and Path(intro_thumbnail).exists()
    intro_dur = intro_duration if has_intro else 0.0

    xfade_dur = 0.4
    bg_chain_dur = audio_duration + 0.5
    while n > 1:
        per_clip = (bg_chain_dur + (n - 1) * xfade_dur) / n
        if per_clip >= 5.0:
            break
        n -= 1
    bg_clips = bg_clips[:n]
    per_clip = (bg_chain_dur + (n - 1) * xfade_dur) / n
    per_clip = min(per_clip, 15.0) if n > 1 else bg_chain_dur

    def _ffmpeg_path(p):
        s = str(p).replace("\\", "/")
        return s.replace(":", "\\:", 1) if ":" in s else s

    ass_str = _ffmpeg_path(ass_path)
    fonts_str = _ffmpeg_path(FONTS_DIR)

    inputs = []
    for clip in bg_clips:
        inputs.extend(["-stream_loop", "-1", "-i", str(clip)])
    if has_intro:
        inputs.extend(["-loop", "1", "-framerate", "30", "-t", f"{intro_dur:.3f}",
                       "-i", str(intro_thumbnail)])
        intro_input_idx = n
        audio_input_idx = n + 1
    else:
        audio_input_idx = n
    inputs.extend(["-i", str(audio_path)])

    music_input_idx = None
    if music_path and Path(music_path).exists():
        music_input_idx = audio_input_idx + 1
        inputs.extend(["-stream_loop", "-1", "-i", str(music_path)])

    fc_parts = []
    for i in range(n):
        fc_parts.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,trim=duration={per_clip:.3f},setpts=PTS-STARTPTS,"
            f"format=yuv420p,fps=30,setsar=1[v{i}]"
        )
    if n == 1:
        bg_label = "[v0]"
    else:
        prev = "[v0]"
        for i in range(1, n):
            offset = i * (per_clip - xfade_dur)
            label = f"[x{i}]"
            fc_parts.append(
                f"{prev}[v{i}]xfade=transition=fade:duration={xfade_dur:.3f}"
                f":offset={offset:.3f}{label}"
            )
            prev = label
        bg_label = prev

    if has_intro:
        fc_parts.append(
            f"[{intro_input_idx}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,trim=duration={intro_dur:.3f},setpts=PTS-STARTPTS,"
            f"format=yuv420p,fps=30,setsar=1[intro]"
        )
        fc_parts.append(f"[intro]{bg_label}concat=n=2:v=1:a=0[bgv]")
        fc_parts.append(f"[bgv]subtitles='{ass_str}':fontsdir='{fonts_str}'[outv]")
        fc_parts.append(
            f"[{audio_input_idx}:a]adelay={int(intro_dur * 1000)}|{int(intro_dur * 1000)}[outa]"
        )
        audio_map = "[outa]"
    else:
        fc_parts.append(f"{bg_label}subtitles='{ass_str}':fontsdir='{fonts_str}'[outv]")
        audio_map = f"{audio_input_idx}:a"

    if music_input_idx is not None:
        fc_parts.append(f"[{music_input_idx}:a]volume=0.10[bgm]")
        voice_in = audio_map if audio_map.startswith("[") else f"[{audio_map}]"
        fc_parts.append(f"{voice_in}[bgm]amix=inputs=2:duration=first:normalize=0[final_a]")
        audio_map = "[final_a]"

    fc = ";".join(fc_parts)

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", fc,
        "-map", "[outv]", "-map", audio_map,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        str(output_path),
    ]
    intro_msg = f", +{intro_dur}s thumbnail intro" if has_intro else ""
    print(f"[render] {n} klip xfade chain, per-clip={per_clip:.1f}s{intro_msg}, FFmpeg calisiyor...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr[-2000:])
        raise RuntimeError("FFmpeg render basarisiz")
    print(f"[render] Hazir -> {output_path.name}")


# --------- 5. YouTube OAuth + Upload ---------
def get_youtube_creds():
    """
    Iki mod:
      1) GitHub Actions / headless: env var'larda CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN
         varsa onlari kullan (interaktif degil).
      2) Local gelistirme: credentials.json + token.json kullan, gerekirse browser ac.
    """
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    if refresh_token and client_id and client_secret:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=YOUTUBE_SCOPES,
        )
        creds.refresh(Request())
        return creds

    creds = None
    if TOKEN_JSON.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_JSON), YOUTUBE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_JSON.exists():
                raise RuntimeError(f"credentials.json yok: {CREDENTIALS_JSON}")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_JSON), YOUTUBE_SCOPES
            )
            creds = flow.run_local_server(port=0, open_browser=True)
        TOKEN_JSON.write_text(creds.to_json())
    return creds


def upload_to_youtube(video_path, title, description, tags, privacy="private",
                      publish_at=None, thumbnail_path=None):
    creds = get_youtube_creds()
    youtube = build("youtube", "v3", credentials=creds)
    status = {
        "privacyStatus": "private" if publish_at else privacy,
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        status["publishAt"] = publish_at
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": "27",  # Education category — Hindi psychology/science content ke liye
        },
        "status": status,
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        s, response = request.next_chunk()
    video_id = response["id"]
    print(f"[upload] Yuklendi: https://youtube.com/watch?v={video_id}")
    if publish_at:
        print(f"[upload] Public olacak: {publish_at}")

    if thumbnail_path and Path(thumbnail_path).exists():
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
        ).execute()
        print(f"[upload] Thumbnail set")

    return video_id


def _next_publish_tr_slot(slots_str, now_utc=None):
    """Given comma-separated TR times like '19:00,01:00', return the next
    upcoming occurrence as ISO UTC string for YouTube publishAt.
    `now_utc` is injectable for testing."""
    from datetime import datetime, timedelta, timezone
    tr_offset = timedelta(hours=3)  # TR is UTC+3 fixed (no DST)
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    now_tr = (now_utc + tr_offset).replace(tzinfo=None)
    candidates = []
    for s in slots_str.split(","):
        hh, mm = (int(x) for x in s.strip().split(":"))
        for day_off in (-1, 0, 1):
            cand_tr = now_tr.replace(hour=hh, minute=mm, second=0, microsecond=0) \
                      + timedelta(days=day_off)
            candidates.append(cand_tr)
    future = [c for c in candidates if c > now_tr + timedelta(seconds=60)]
    target_tr = min(future)
    target_utc = target_tr - tr_offset
    return target_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")


# --------- Main pipeline ---------
INTRO_DURATION = 1.2  # thumbnail held as silent intro frame at the start of the short


def run_pipeline(skip_upload=False, privacy="private", auto_public_after=0,
                 publish_at_tr_slots=None, publish_at_utc=None, upload_thumbnail=False):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    workdir = OUTPUT_DIR / ts
    workdir.mkdir(exist_ok=True)
    print(f"[main] Calisma klasoru: {workdir}")

    meta = generate_fun_fact()
    (workdir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    audio_path = workdir / "voice.mp3"
    subs_path = workdir / "subs.ass"
    # Subs are shifted by the intro duration so they stay in sync with the
    # voice (which is also delayed by INTRO_DURATION via adelay in render).
    duration = generate_voice(meta["script"], audio_path, subs_path,
                              time_offset=INTRO_DURATION)

    visual_keywords = meta.get("visual_keywords") or [meta["keyword"]]
    clips_meta = fetch_pexels_clips(
        visual_keywords, meta["keyword"],
        n_clips=4, min_duration_per_clip=5,
    )
    clip_paths = []
    for i, (clip_url, _dur) in enumerate(clips_meta):
        p = workdir / f"bg_{i}.mp4"
        download_file(clip_url, p)
        clip_paths.append(p)

    thumb_path = workdir / "thumbnail.png"
    yt_thumb_path = workdir / "thumbnail_yt.png"
    try:
        generate_thumbnail(clip_paths[0], meta.get("thumbnail_text", ""), thumb_path)
    except Exception as e:
        print(f"[thumb] uretilemedi, atlanacak: {e}")
        thumb_path = None
    try:
        generate_thumbnail(clip_paths[0], meta.get("thumbnail_text", ""),
                           yt_thumb_path, size=(1280, 720))
    except Exception as e:
        print(f"[thumb] 16:9 uretilemedi, atlanacak: {e}")
        yt_thumb_path = None

    out_path = workdir / "short.mp4"
    render_video(clip_paths, audio_path, subs_path, duration, out_path,
                 intro_thumbnail=thumb_path, intro_duration=INTRO_DURATION,
                 music_path=MUSIC_PATH if MUSIC_PATH.exists() else None)

    if skip_upload:
        print(f"[main] Yukleme atlandi. Video: {out_path}")
        return out_path
    publish_at = None
    if publish_at_utc and privacy != "public":
        publish_at = publish_at_utc
        print(f"[main] publishAt (explicit): {publish_at}")
    elif publish_at_tr_slots and privacy != "public":
        publish_at = _next_publish_tr_slot(publish_at_tr_slots)
        print(f"[main] publishAt (next TR slot): {publish_at}")
    elif auto_public_after > 0 and privacy != "public":
        from datetime import timedelta, timezone
        dt = datetime.now(timezone.utc) + timedelta(seconds=auto_public_after)
        publish_at = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    description = meta["description"]
    if MUSIC_PATH.exists():
        description += "\n\nMusic: Darkest Child by Kevin MacLeod (incompetech.com) | CC BY 3.0"
    video_id = upload_to_youtube(
        out_path,
        meta["title"],
        description,
        meta["tags"],
        privacy=privacy,
        publish_at=publish_at,
        thumbnail_path=yt_thumb_path if upload_thumbnail else None,
    )
    print(f"[main] Tamam. Video ID: {video_id}")
    return out_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--auth", action="store_true", help="Sadece YouTube OAuth (ilk kez)")
    p.add_argument("--no-upload", action="store_true", help="Uret ama yukleme")
    p.add_argument("--public", action="store_true", help="(deprecated) --privacy public ile ayni")
    p.add_argument("--privacy", choices=["private", "public", "unlisted"], default=None)
    p.add_argument("--auto-public-after", type=int, default=0,
                   help="Saniye sonra video private->public'e cevrilir (privacy public degilse)")
    p.add_argument("--publish-at-tr", default=None,
                   help="Virgulle ayrilmis TR saatleri (orn: '19:00,01:00'). "
                        "En yakin gelecek slotu publishAt olarak kullanir, GitHub gecikmesinden bagimsiz.")
    # Custom thumbnail YT upload is OFF by default — Shorts ignores the custom thumbnail
    # in feed/grid, so the 1.2s in-video intro frame from thumbnail.png does the job.
    # Pass --upload-thumbnail to opt in (e.g. for non-Shorts uploads).
    p.add_argument("--publish-at-utc", default=None,
                   help="Explicit publishAt UTC ISO datetime (orn: '2026-05-12T16:00:00.000Z'). "
                        "--publish-at-tr yerine kullan bulk upload icin.")
    p.add_argument("--upload-thumbnail", action="store_true",
                   help="YT'ye custom thumbnail yukle (varsayilan: kapali, video icindeki "
                        "1.2sn intro yetiyor cunku Shorts custom thumbnail'i feed'de gostermiyor)")
    args = p.parse_args()

    if args.auth:
        creds = get_youtube_creds()
        print("[auth] Token kaydedildi:", TOKEN_JSON)
        return

    if args.privacy:
        privacy = args.privacy
    elif args.public:
        privacy = "public"
    else:
        privacy = "private"
    run_pipeline(
        skip_upload=args.no_upload,
        privacy=privacy,
        auto_public_after=args.auto_public_after,
        publish_at_tr_slots=args.publish_at_tr,
        publish_at_utc=args.publish_at_utc,
        upload_thumbnail=args.upload_thumbnail,
    )


if __name__ == "__main__":
    main()
