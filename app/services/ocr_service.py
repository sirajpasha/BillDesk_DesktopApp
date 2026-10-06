from __future__ import annotations
import os
import re
import sys
import shutil
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract


# Indian script numeral mapping
INDIC_DIGITS = {
    # Tamil: ௦ ௧ ௨ ௩ ௪ ௫ ௬ ௭ ௮ ௯
    '௦': '0', '௧': '1', '௨': '2', '௩': '3', '௪': '4',
    '௫': '5', '௬': '6', '௭': '7', '௮': '8', '௯': '9',
    # Devanagari / Hindi: ० १ २ ३ ४ ५ ६ ७ ८ ९
    '०': '0', '१': '1', '२': '2', '३': '3', '४': '4',
    '५': '5', '६': '6', '७': '7', '८': '8', '९': '9',
    # Telugu: ౦ ౧ ౨ ౩ ౪ ౫ ౬ ౭ ౮ ౯
    '౦': '0', '౧': '1', '౨': '2', '౩': '3', '౪': '4',
    '౫': '5', '౬': '6', '౭': '7', '౮': '8', '౯': '9',
    # Kannada: ೦ ೧ ೨ ೩ ೪ ೫ ೬ ೭ ೮ ೯
    '೦': '0', '೧': '1', '೨': '2', '೩': '3', '೪': '4',
    '೫': '5', '೬': '6', '೭': '7', '೮': '8', '೯': '9',
    # Malayalam: ൦ ൧ ൨ ൩ ൪ ൫ ൬ ൭ ൮ ൯
    '൦': '0', '൧': '1', '൨': '2', '൩': '3', '൪': '4',
    '൫': '5', '൬': '6', '൭': '7', '൮': '8', '൯': '9',
}

# Multi-lingual unit synonyms
INDIC_UNITS = {
    # Kg
    "kg": "Kg", "kgs": "Kg", "kilo": "Kg", "kilos": "Kg", "kilogram": "Kg",
    "கிலோ": "Kg", "கிகி": "Kg", "கி.கி": "Kg", "கி": "Kg",
    "കി.ഗ്രാം": "Kg", "കിലോഗ്രാം": "Kg", "കിലോ": "Kg",
    "కిలో": "Kg", "కిలోలు": "Kg", "కి.గ్రా": "Kg",
    "ಕಿಲೋ": "Kg", "ಕಿಲೋಗ್ರಾಂ": "Kg", "ಕಿ.ಗ್ರಾಂ": "Kg",
    "किलो": "Kg", "किग्रा": "Kg", "किलोग्राम": "Kg",

    # Gm
    "g": "Gm", "gm": "Gm", "gms": "Gm", "gram": "Gm", "grams": "Gm",
    "கிராம்": "Gm", "கி.ரா": "Gm", "ഗ്രാം": "Gm",
    "గ్రాములు": "Gm", "గ్రామ్": "Gm", "ಗ್ರಾಂ": "Gm", "ग्राम": "Gm",

    # Nos
    "nos": "Nos", "no": "Nos", "piece": "Nos", "pieces": "Nos", "pcs": "Nos", "pc": "Nos",
    "எண்": "Nos", "எண்ணிக்கை": "Nos", "பீஸ்": "Nos",
    "എണ്ണം": "Nos", "പീസ്": "Nos",
    "సంఖ్య": "Nos", "పీస్": "Nos", "నగ": "Nos",
    "ಸಂಖ್ಯೆ": "Nos", "ಪೀಸ್": "Nos",
    "नग": "Nos", "पीस": "Nos",

    # Bunch
    "bunch": "Bunch", "bunches": "Bunch",
    "கட்டு": "Bunch", "கட்டுகள்": "Bunch", "கத்த": "Bunch",
    "കെട്ട്": "Bunch", "కట్ట": "Bunch", "కట్టలు": "Bunch",
    "ಕಟ್ಟು": "Bunch", "गड्डी": "Bunch",

    # Pkt
    "pkt": "Pkt", "pkts": "Pkt", "packet": "Pkt", "packets": "Pkt", "pack": "Pkt",
    "பாக்கெட்": "Pkt", "பாக்கெட்ஸ்": "Pkt", "പാക്കറ്റ്": "Pkt",
    "ప్యాకెట్": "Pkt", "ಪ್ಯಾಕೆಟ್": "Pkt", "पैकेट": "Pkt",

    # Box
    "box": "Box", "boxes": "Box",
    "பெட்டி": "Box", "பெட்டிகள்": "Box", "ബോക്സ്": "Box",
    "బాక్స్": "Box", "ಬಾಕ್ಸ್": "Box", "डिब्बा": "Box", "पेटी": "Box",

    # Bag
    "bag": "Bag", "bags": "Bag", "sack": "Bag", "sacks": "Bag",
    "மூட்டை": "Bag", "பை": "Bag", "ബാഗ്": "Bag",
    "సంచి": "Bag", "చీల": "Bag", "बोरी": "Bag",

    # Dz
    "dz": "Dz", "dozen": "Dz", "dozens": "Dz",
    "டஜன்": "Dz", "ഡസൻ": "Dz", "డజను": "Dz", "ಡಜನ್": "Dz", "दर्जन": "Dz",

    # Crate
    "crate": "Crate", "crates": "Crate",
    "கூடை": "Crate", "கிரேட்": "Crate", "ക്രേറ്റ്": "Crate",
    "క్రేట్": "Crate", "ಕ್ರೇಟ್": "Crate", "क्रेट": "Crate",
}

# Multi-lingual produce name synonyms mapped to canonical search queries / aliases
PRODUCE_SYNONYMS = {
    # Tomato (162 / 163)
    "tomato": "Tomatto", "tomatoes": "Tomatto", "tomatto": "Tomatto", "tamatar": "Tomatto",
    "thakkali": "Tomatto", "takkali": "Tomatto", "tamata": "Tomatto", "tamate": "Tomatto",
    "தக்காளி": "Tomatto", "தக்காளிப்": "Tomatto",
    "തക്കാളി": "Tomatto",
    "టమోటా": "Tomatto", "టమాట": "Tomatto",
    "ಟೊಮೆಟೊ": "Tomatto", "ಟೊಮ್ಯಾಟೊ": "Tomatto",
    "टमाटर": "Tomatto",

    # Cucumber (125)
    "cucumber": "Cucumber", "cucumbers": "Cucumber", "kheera": "Cucumber", "kakdi": "Cucumber",
    "vellarikkai": "Cucumber", "vellari": "Cucumber", "vellarikka": "Cucumber",
    "dosakaya": "Cucumber", "keeradosa": "Cucumber", "southekayi": "Cucumber", "sauthekayi": "Cucumber",
    "வெள்ளரிக்காய்": "Cucumber", "வெள்ளரி": "Cucumber",
    "വെള്ളരിക്ക": "Cucumber", "വെള്ളരി": "Cucumber",
    "దోసకాయ": "Cucumber", "కీరదోస": "Cucumber",
    "ಸೌತೆಕಾಯಿ": "Cucumber",
    "खीरा": "Cucumber", "ककड़ी": "Cucumber",

    # Onion (145 / 157 / 158 / 160)
    "onion": "Onion", "onions": "Onion", "pyaaz": "Onion", "pyaz": "Onion", "kanda": "Onion",
    "vengayam": "Onion", "periya vengayam": "Onion", "ulli": "Onion", "savala": "Onion",
    "ullipaya": "Onion", "erragadda": "Onion", "eerulli": "Onion", "ullagaddi": "Onion",
    "வெங்காயம்": "Onion", "பெரிய வெங்காயம்": "Onion", "சாம்பார் வெங்காயம்": "Sambar Onion",
    "ഉള്ളി": "Onion", "സവാള": "Onion",
    "ఉల్లిపాయ": "Onion", "ఎర్రగడ్డ": "Onion",
    "ಈರುಳ್ಳಿ": "Onion", "ಉಳ್ಳಾಗಡ್ಡಿ": "Onion",
    "प्याज": "Onion", "कांदा": "Onion",

    # Potato (148 / 166)
    "potato": "Potato", "potatoes": "Potato", "aloo": "Potato", "alu": "Potato",
    "urulaikilangu": "Potato", "urulai": "Potato", "urulakkizhangu": "Potato",
    "bangaladumpa": "Potato", "aaloogadde": "Potato",
    "உருளைக்கிழங்கு": "Potato", "உருளை": "Potato",
    "ഉരുളക്കിഴങ്ങ്": "Potato",
    "బంగాళాదుంప": "Potato", "ఆలూ": "Potato",
    "ಆಲೂಗಡ್ಡೆ": "Potato", "ಆಲೂ": "Potato",
    "आलू": "Potato",

    # Brinjal / Eggplant (111..115)
    "brinjal": "Brinjal", "eggplant": "Brinjal", "baingan": "Brinjal", "vangee": "Brinjal",
    "kathirikkai": "Brinjal", "kathari": "Brinjal", "vazhuthananga": "Brinjal",
    "vankaya": "Brinjal", "badanekayi": "Brinjal",
    "கத்தரிக்காய்": "Brinjal", "கத்தரி": "Brinjal",
    "വഴുതനങ്ങ": "Brinjal", "വഴുതന": "Brinjal",
    "వంకాయ": "Brinjal",
    "ಬದನೆಕಾಯಿ": "Brinjal",
    "बैंगन": "Brinjal",

    # Lady Finger / Bhendi
    "lady finger": "Lady Finger", "ladies finger": "Lady Finger", "bhendi": "Lady Finger", "bhindi": "Lady Finger", "okra": "Lady Finger",
    "vendaikkai": "Lady Finger", "vendai": "Lady Finger", "vendakka": "Lady Finger",
    "bendakaya": "Lady Finger", "bendekayi": "Lady Finger",
    "வெண்டைக்காய்": "Lady Finger", "வெண்டை": "Lady Finger",
    "വെണ്ടയ്ക്ക": "Lady Finger",
    "బెండకాయ": "Lady Finger",
    "ಬೆಂಡೆಕಾಯಿ": "Lady Finger",
    "भिंडी": "Lady Finger",

    # Carrot
    "carrot": "Carrot", "carrots": "Carrot", "gajar": "Carrot", "gajjari": "Carrot",
    "கேரட்": "Carrot", "ക്യാരറ്റ്": "Carrot", "క్యారెట్": "Carrot", "ಕ್ಯಾರೆಟ್": "Carrot", "गाजर": "Carrot",

    # Cabbage
    "cabbage": "Cabbage", "patta gobhi": "Cabbage", "band gobhi": "Cabbage",
    "muttaikose": "Cabbage", "kose": "Cabbage", "elekosu": "Cabbage",
    "முட்டைக்கோஸ்": "Cabbage", "கோஸ்": "Cabbage", "കാബേജ്": "Cabbage",
    "క్యాబేజీ": "Cabbage", "ಎಲೆಕೋಸು": "Cabbage", "पत्तागोभी": "Cabbage",

    # Cauliflower
    "cauliflower": "Cauliflower", "phool gobhi": "Cauliflower", "pookose": "Cauliflower", "hookosu": "Cauliflower",
    "காலிஃபிளவர்": "Cauliflower", "பூக்கோஸ்": "Cauliflower",
    "കോളിഫ്ലവർ": "Cauliflower", "కాలీఫ్లవర్": "Cauliflower", "ಹೂಕೋಸು": "Cauliflower", "फूलगोभी": "Cauliflower",

    # Beans
    "beans": "Beans", "sem": "Beans", "chikkudu": "Beans", "hurulikayi": "Beans",
    "avaraikkai": "Avaraikkai", "avarai": "Avaraikkai",
    "பீன்ஸ்": "Beans", "அவரைக்காய்": "Avaraikkai", "அவரை": "Avaraikkai",
    "ബീൻസ്": "Beans", "చిక్కుడు": "Beans", "ಹುರುಳಿಕಾಯಿ": "Beans", "सेम": "Beans",

    # Ginger
    "ginger": "Ginger", "adrak": "Ginger", "inji": "Ginger", "allam": "Ginger", "shunti": "Ginger",
    "இஞ்சி": "Ginger", "ഇഞ്ചി": "Ginger", "అల్లం": "Ginger", "ಶುಂಠಿ": "Ginger", "अदरक": "Ginger",

    # Garlic
    "garlic": "Garlic", "lahsun": "Garlic", "poondu": "Garlic", "veluthulli": "Garlic", "vellulli": "Garlic", "bellulli": "Garlic",
    "பூண்டு": "Garlic", "വെളുത്തുള്ളി": "Garlic", "వెల్లుల్లి": "Garlic", "ಬೆಳ್ಳುಳ್ಳಿ": "Garlic", "लहसुन": "Garlic",

    # Green Chilli
    "green chilli": "Green Chilli", "green chilly": "Green Chilli", "chilli": "Chilli", "chilly": "Chilli", "mirchi": "Chilli", "hari mirch": "Chilli",
    "pachai milagai": "Chilli", "milagai": "Chilli", "pachamulaku": "Chilli", "pachimirchi": "Chilli", "hasimenasinakayi": "Chilli",
    "பச்சை மிளகாய்": "Chilli", "மிளகாய்": "Chilli",
    "പച്ചമുളക്": "Chilli", "పచ్చిమిర్చి": "Chilli", "ಹಸಿಮೆಣಸಿನಕಾಯಿ": "Chilli", "हरी मिर्च": "Chilli",

    # Coriander
    "coriander": "Coriander", "cilantro": "Coriander", "dhaniya": "Coriander", "kothamalli": "Coriander", "malli": "Coriander",
    "malliyila": "Coriander", "kothimeera": "Coriander", "kothambari": "Coriander",
    "கொத்தமல்லி": "Coriander", "மல்லி": "Coriander", "മല്ലിയില": "Coriander",
    "కొత్తిమీర": "Coriander", "ಕೊತ್ತಂಬರಿ": "Coriander", "धनिया": "Coriander",

    # Mint
    "mint": "Mint", "pudina": "Mint", "pudhina": "Mint",
    "புதினா": "Mint", "പുതിന": "Mint", "పుదీనా": "Mint", "ಪುದೀನ": "Mint", "पुदीना": "Mint",

    # Curry Leaves
    "curry leaves": "Curry Leaves", "curry leaf": "Curry Leaves", "kariveppilai": "Curry Leaves", "karivepaku": "Curry Leaves", "karibevu": "Curry Leaves", "kadi patta": "Curry Leaves",
    "கறிவேப்பிலை": "Curry Leaves", "കറിവേപ്പില": "Curry Leaves", "కరివేపాకు": "Curry Leaves", "ಕರಿಬೇವು": "Curry Leaves", "कढ़ी पत्ता": "Curry Leaves",

    # Capsicum
    "capsicum": "Capsicum", "shimla mirch": "Capsicum", "kudaimilagai": "Capsicum",
    "குடைமிளகாய்": "Capsicum", "బెంగళూరు మిర్చి": "Capsicum", "शिमला मिर्च": "Capsicum",

    # Beetroot
    "beetroot": "Beetroot", "பீட்ரூட்": "Beetroot", "ബീറ്റ്റൂട്ട്": "Beetroot", "బీట్‌రూట్": "Beetroot", "ಬೀಟ್ರೂಟ್": "Beetroot",

    # Radish
    "radish": "Radish", "mooli": "Radish", "mullangi": "Radish", "moolangi": "Radish",
    "முள்ளங்கி": "Radish", "മുള്ളങ്കി": "Radish", "ముల్లంగి": "Radish", "ಮೂಲಂಗಿ": "Radish", "मूली": "Radish",

    # Banana Leaves (104, 105, 106)
    "banana leaves": "Banana Leaves", "banana leaf": "Banana Leaves", "vazhai ilai": "Banana Leaves", "vazhayila": "Banana Leaves",
    "வாழை இலை": "Banana Leaves", "வாழை": "Banana Leaves", "വാഴയില": "Banana Leaves",
    "అరిటాకు": "Banana Leaves", "ಬಾಳೆ ಎಲೆ": "Banana Leaves",
}


class SmartOcrService:
    """
    Multi-Lingual OCR & Intelligent Produce Order Parser Engine.
    Handles images of handwritten / printed orders in English, Tamil, Malayalam,
    Telugu, Kannada, Hindi and translates them into matching Item Master records.
    """

    def __init__(self, root_dir: Optional[str] = None):
        if root_dir is None:
            root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.root_dir = root_dir
        self.tesseract_exe = self._resolve_tesseract_binary()
        self.tessdata_dir = self._resolve_tessdata_dir()
        self._configure_pytesseract()

    def _resolve_tesseract_binary(self) -> Optional[str]:
        # 1. Check local project resources
        candidates = [
            os.path.join(self.root_dir, "resources", "tesseract", "win32-x64", "tesseract.exe"),
            shutil.which("tesseract"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
        ]
        for c in candidates:
            if c and os.path.isfile(c):
                return os.path.abspath(c)
        return None

    def _resolve_tessdata_dir(self) -> Optional[str]:
        if self.tesseract_exe:
            cand = os.path.join(os.path.dirname(self.tesseract_exe), "tessdata")
            if os.path.isdir(cand):
                return os.path.abspath(cand)
        res_cand = os.path.join(self.root_dir, "resources", "tesseract", "win32-x64", "tessdata")
        if os.path.isdir(res_cand):
            return os.path.abspath(res_cand)
        return None

    def _configure_pytesseract(self):
        if self.tesseract_exe:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_exe
        if self.tessdata_dir:
            os.environ["TESSDATA_PREFIX"] = self.tessdata_dir

    def get_available_languages(self) -> List[str]:
        """Returns list of installed Tesseract language codes."""
        if not self.tessdata_dir or not os.path.isdir(self.tessdata_dir):
            return ["eng"]
        langs = []
        for f in os.listdir(self.tessdata_dir):
            if f.endswith(".traineddata") and not f.startswith("osd"):
                langs.append(f.replace(".traineddata", ""))
        return sorted(langs) if langs else ["eng"]

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocesses raw photo / handwritten document to maximize OCR accuracy:
        1. RGB conversion
        2. Upscaling for small images
        3. Grayscale conversion
        4. Contrast boosting & edge sharpening
        """
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Upscale if dimensions are small
        w, h = image.size
        if w < 1200 or h < 1200:
            factor = max(1200 / max(w, 1), 1200 / max(h, 1))
            new_size = (int(w * factor), int(h * factor))
            image = image.resize(new_size, Image.Resampling.BICUBIC)

        # Grayscale
        gray = image.convert("L")

        # Contrast enhancement
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(1.8)

        # Sharpening
        sharpened = enhanced.filter(ImageFilter.SHARPEN)
        return sharpened

    def extract_text_from_image(
        self,
        image_input: Any,
        lang: Optional[str] = None
    ) -> str:
        """
        Runs OCR on given image (path, bytes, or PIL Image) with multi-lingual support.
        Supports English, Tamil, Malayalam, Telugu, Kannada, Hindi.
        """
        if isinstance(image_input, str):
            image = Image.open(image_input)
        elif hasattr(image_input, "read"):
            image = Image.open(image_input)
        elif isinstance(image_input, Image.Image):
            image = image_input
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        processed = self.preprocess_image(image)

        # Determine language string
        available = self.get_available_languages()
        if not lang or lang == "auto":
            # Combine all available indic languages + eng
            desired = ["eng", "tam", "mal", "tel", "kan", "hin"]
            active = [l for l in desired if l in available]
            lang_str = "+".join(active) if active else "eng"
        else:
            lang_str = lang

        try:
            # PSM 6: Assume a single uniform block of text
            text = pytesseract.image_to_string(
                processed,
                lang=lang_str,
                config="--psm 6"
            )
            if not text.strip():
                # Fallback to PSM 3 (fully automatic)
                text = pytesseract.image_to_string(
                    processed,
                    lang=lang_str,
                    config="--psm 3"
                )
        except Exception as ex:
            # Fallback to standard eng if indic failed
            try:
                text = pytesseract.image_to_string(processed, lang="eng")
            except Exception:
                raise RuntimeError(f"OCR execution failed: {ex}")

        return text.strip()

    @staticmethod
    def normalize_indic_digits(text: str) -> str:
        """Converts Indian script numerals to standard ASCII digits."""
        res = []
        for char in text:
            if char in INDIC_DIGITS:
                res.append(INDIC_DIGITS[char])
            else:
                res.append(char)
        return "".join(res)

    def parse_order_lines(
        self,
        raw_text: str,
        items_cache: List[Dict[str, Any]],
        default_unit: str = "Kg"
    ) -> List[Dict[str, Any]]:
        """
        Intelligently parses OCR or pasted text lines into matched items:
        - Extracts item name / code in English or Indian languages (Tamil, Telugu, etc.)
        - Resolves to Item Master records via aliases and synonym dictionaries
        - Extracts Quantity and Unit
        """
        clean_text = self.normalize_indic_digits(raw_text)
        lines = [l.strip() for l in clean_text.splitlines() if l.strip()]
        results = []

        for line in lines:
            # Replace common separators with spaces
            norm_line = re.sub(r"[,;:\-–—\t]+", " ", line)

            # Match quantity and unit
            tokens = norm_line.split()
            if not tokens:
                continue

            qty = 0.0
            unit = default_unit
            name_parts = []

            for tok in tokens:
                clean_tok = tok.strip("()[]{}#.*")
                if not clean_tok:
                    continue

                # Check if token is a pure float / int
                try:
                    val = float(clean_tok)
                    if qty == 0.0 and val > 0:
                        qty = val
                        continue
                except ValueError:
                    pass

                # Check fraction e.g. 1/2, 1/4, 3/4
                if clean_tok in ("1/2", "½"):
                    qty = 0.5
                    continue
                elif clean_tok in ("1/4", "¼"):
                    qty = 0.25
                    continue
                elif clean_tok in ("3/4", "¾"):
                    qty = 0.75
                    continue

                # Check concatenated qty + unit, e.g. '5kg', '10nos', '2.5kgs', '5கிலோ'
                m_num_unit = re.match(r"^(\d+(?:\.\d+)?)\s*([a-zA-Z\u0B80-\u0D7F\u0C00-\u0C7F\u0C80-\u0CFF\u0900-\u097F]+)$", clean_tok)
                if m_num_unit:
                    num_val = float(m_num_unit.group(1))
                    unit_str = m_num_unit.group(2).lower()
                    if qty == 0.0:
                        qty = num_val
                    if unit_str in INDIC_UNITS:
                        unit = INDIC_UNITS[unit_str]
                    continue

                # Check standalone unit token
                lower_tok = clean_tok.lower()
                if lower_tok in INDIC_UNITS:
                    unit = INDIC_UNITS[lower_tok]
                    continue

                name_parts.append(clean_tok)

            raw_item_query = " ".join(name_parts).strip()
            if not raw_item_query and qty == 0.0:
                continue

            # Resolve item in items_cache
            matched_item = self._match_produce_item(raw_item_query, items_cache)

            if matched_item:
                results.append({
                    "item_id": matched_item.get("item_id"),
                    "code": matched_item.get("item_alias") or matched_item.get("item_id"),
                    "name": matched_item.get("name"),
                    "qty": qty if qty > 0.0 else 1.0,
                    "unit": matched_item.get("unit") or unit,
                    "standard_rate": float(matched_item.get("standard_rate") or 0.0),
                    "matched": True,
                    "raw_query": raw_item_query,
                })
            else:
                # Fallback: keep query as code & name
                results.append({
                    "item_id": raw_item_query,
                    "code": raw_item_query,
                    "name": raw_item_query,
                    "qty": qty if qty > 0.0 else 1.0,
                    "unit": unit,
                    "standard_rate": 0.0,
                    "matched": False,
                    "raw_query": raw_item_query,
                })

        return results

    def _match_produce_item(
        self,
        query: str,
        items_cache: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Resolves query string against:
        1. Item alias (e.g. '125', '162', '101')
        2. Exact or substring match in item master name
        3. Multi-lingual produce dictionary (Tamil, Malayalam, Telugu, Kannada, Hindi)
        """
        q = query.strip()
        if not q:
            return None

        q_lower = q.lower()

        # 1. Direct alias match
        for it in items_cache:
            if str(it.get("item_alias", "")).lower() == q_lower:
                return it
            if str(it.get("item_id", "")).lower() == q_lower:
                return it

        # 2. Check multi-lingual synonym dictionary
        canonical_search = None
        for syn, canonical in PRODUCE_SYNONYMS.items():
            if syn in q_lower or q_lower in syn:
                canonical_search = canonical.lower()
                break

        # 3. Search in item master names
        search_terms = [canonical_search, q_lower] if canonical_search else [q_lower]

        # Exact name match
        for st in search_terms:
            if not st:
                continue
            for it in items_cache:
                it_name = it.get("name", "").lower()
                if it_name == st:
                    return it

        # Starts with match
        for st in search_terms:
            if not st:
                continue
            for it in items_cache:
                it_name = it.get("name", "").lower()
                if it_name.startswith(st):
                    return it

        # Substring match
        for st in search_terms:
            if not st:
                continue
            for it in items_cache:
                it_name = it.get("name", "").lower()
                if st in it_name:
                    return it

        # Word-level overlap
        q_words = set(re.findall(r"\w+", q_lower))
        for it in items_cache:
            it_words = set(re.findall(r"\w+", it.get("name", "").lower()))
            if q_words and q_words.issubset(it_words):
                return it

        return None
