import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.rules import BoundingBox
from app.schemas.verification import ExtractedData, ExtractedField

Item = Dict[str, Any]

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000,
          "crore": 10_000_000, "crores": 10_000_000}


def _words_value(tokens: List[str]) -> Tuple[int, bool]:
    total, current, found = 0, 0, False
    for tok in tokens:
        if tok in NUMBER_WORDS:
            current += NUMBER_WORDS[tok]
            found = True
        elif tok == "hundred":
            current = max(1, current) * 100
            found = True
        elif tok in SCALES:
            total += max(1, current) * SCALES[tok]
            current = 0
            found = True
    return total + current, found


_VOCAB = sorted(set(NUMBER_WORDS) | set(SCALES) | {"hundred", "rupees", "rupee", "only", "and", "paise"},
                key=len, reverse=True)


def _split_merged(token: str) -> List[str]:
    """OCR often drops spaces: 'rupeesfourhundredfifty' -> ['rupees', 'four', 'hundred', 'fifty']."""
    out, i = [], 0
    while i < len(token):
        word = next((w for w in _VOCAB if token.startswith(w, i)), None)
        if not word:
            return [token]  # not made of number words; leave untouched
        out.append(word)
        i += len(word)
    return out


def words_to_number(text: str) -> Optional[float]:
    """'Rupees One Thousand Two Hundred Fifty and Fifty Paise Only' -> 1250.5 (Indian numbering)."""
    cleaned = re.sub(r"[^a-z\s]", " ", text.lower())
    tokens = [w for t in cleaned.split() for w in _split_merged(t)]
    tokens = [t for t in tokens if t not in ("rupees", "rupee", "rs", "inr", "only")]
    paise = 0
    if "paise" in tokens:
        idx = tokens.index("paise")
        head = tokens[:idx]
        if "and" in head:
            cut = len(head) - 1 - head[::-1].index("and")
            paise, _ = _words_value(head[cut + 1:])
            tokens = head[:cut]
        else:
            tokens = head
    tokens = [t for t in tokens if t != "and"]
    rupees, found = _words_value(tokens)
    if not found or rupees + paise == 0:
        return None
    return float(rupees) + paise / 100.0


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _fix_month(tok: str) -> str:
    # OCR often reads "Oct" as "0ct" and "Sep" as "5ep".
    return tok.lower().replace("0", "o").replace("5", "s").replace("1", "l")[:3]


_TIME = r"(?P<hh>[0-2]?\d)[:.](?P<mm>[0-5]\d)(?::[0-5]\d)?\s*(?P<ampm>[ap]\.?m\.?)?"
_DT_PATTERNS = [
    # 23 Oct 2026, 02:32 PM  |  230ct2026,02:32AM
    re.compile(r"(?P<d>[0-3]?\d)\s*(?P<mon>[A-Za-z015]{3})[a-z]*\.?\s*,?\s*(?P<y>20\d{2})\s*[,|\s-]*\s*(?:at\s*)?" + _TIME, re.I),
    # Oct 23, 2026 2:32 PM
    re.compile(r"(?P<mon>[A-Za-z015]{3})[a-z]*\.?\s*(?P<d>[0-3]?\d)\s*,?\s*(?P<y>20\d{2})\s*[,|\s-]*\s*(?:at\s*)?" + _TIME, re.I),
    # 2:32 PM on 23 Oct 2026
    re.compile(_TIME + r"\s*(?:on|,)?\s*(?P<d>[0-3]?\d)\s*(?P<mon>[A-Za-z015]{3})[a-z]*\.?\s*,?\s*(?P<y>20\d{2})", re.I),
    # 23/10/2026 14:32  |  23-10-26 2:32 pm
    re.compile(r"(?P<d>[0-3]?\d)[/\-.](?P<mo>[01]?\d)[/\-.](?P<y>(?:20)?\d{2})\s*[,|\s]*\s*" + _TIME, re.I),
]


def parse_datetime(text: str) -> Optional[datetime]:
    """Parse the transaction date/time formats used by Indian UPI apps. Returns a naive local datetime."""
    if not text:
        return None
    for pat in _DT_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        g = m.groupdict()
        try:
            month = int(g["mo"]) if g.get("mo") else MONTHS.get(_fix_month(g["mon"]))
            if not month:
                continue
            year = int(g["y"])
            year = year + 2000 if year < 100 else year
            hh, mm = int(g["hh"]), int(g["mm"])
            ampm = (g.get("ampm") or "").lower().replace(".", "")
            if ampm == "pm" and hh < 12:
                hh += 12
            elif ampm == "am" and hh == 12:
                hh = 0
            return datetime(year, month, int(g["d"]), hh, mm)
        except (ValueError, TypeError):
            continue
    return None


def parse_clock(text: str) -> Optional[Tuple[int, int]]:
    m = re.search(r"\b([0-2]?\d)[:.]([0-5]\d)\s*([ap]m)?\b", text or "", re.I)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hh < 12:
        hh += 12
    elif ampm == "am" and hh == 12:
        hh = 0
    return (hh, mm) if hh < 24 else None


VPA_RE = re.compile(r"([a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9]{1,63})")
TRAILING_AMOUNT_RE = re.compile(r"[A-Za-z)]\s*(?:₹|rs\.?|\?)\s*(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?)$", re.I)
APP_TXN_RE = re.compile(r"(?<![0-9A-Za-z])(T\d{20,23})(?!\d)")
AMOUNT_RE = re.compile(r"^(?P<cur>₹|rs\.?|inr|[^\w\s,.]{1,2}|[A-Za-z一-鿿]{1})?\s*"
                       r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d{1,6}(?:\.\d{1,2})?)\s*(?:/-)?$", re.I)
UTR_LABELS = ("utr", "upi ref", "ref no", "ref. no", "reference", "transaction id", "txn id", "rrn",
              "upi transaction id", "transactionid", "refno", "upi ref id", "bank reference")
TO_LABELS = ("paid to", "sent to", "paying", "transfer to", "to:", "payee", "received by")
FROM_LABELS = ("from", "debited from", "paid by", "sender")
NOTE_LABELS = ("note", "message", "remarks", "description")
SUCCESS_WORDS = ("successful", "success", "completed", "paid", "credited", "received")
FAIL_WORDS = ("failed", "failure", "pending", "declined", "processing", "cancelled", "reversed", "unsuccessful")

APP_KEYWORDS = [
    ("phonepe", ("phonepe", "phone pe")),
    ("gpay", ("google pay", "gpay", "g pay")),
    ("paytm", ("paytm",)),
    ("bhim", ("bhim",)),
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


def _has_label(text: str, labels) -> bool:
    t = _norm(text)
    return any(_norm(lbl) in t for lbl in labels)


class UPIExtractor:
    @staticmethod
    def identify_payment_app(items: List[Item]) -> str:
        # UPI handles such as name@paytm or name@ybl say nothing about which app produced the screenshot.
        full = " ".join(VPA_RE.sub(" ", i["text"]).lower() for i in items)
        nospace = _norm(full)
        for app, keys in APP_KEYWORDS:
            if any(_norm(k) in nospace for k in keys):
                return app
        return "generic"

    @staticmethod
    def _field(item: Optional[Item], value: Optional[str] = None, conf: Optional[float] = None) -> ExtractedField:
        if not item:
            return ExtractedField(value=None, confidence=0.0, bbox=None, is_valid=False)
        return ExtractedField(value=value if value is not None else item["text"],
                              confidence=round(conf if conf is not None else item["confidence"], 4),
                              bbox=BoundingBox(**item["bbox"]), is_valid=True)

    @staticmethod
    def _after_label(items: List[Item], labels, predicate, max_ahead: int = 2) -> Optional[Tuple[Item, str]]:
        for i, it in enumerate(items):
            if not _has_label(it["text"], labels):
                continue
            # Value on the same line after the label, e.g. "UPI Ref No: 4291...".
            res = predicate(it, True)
            if res:
                return it, res
            for nxt in items[i + 1:i + 1 + max_ahead]:
                res = predicate(nxt, False)
                if res:
                    return nxt, res
        return None

    def extract_all(self, items: List[Item], img_height: int, img_width: int) -> ExtractedData:
        app = self.identify_payment_app(items)
        status_bar_cut = img_height * 0.05
        # Only a clock-like line up there is the phone's status bar; a cropped screenshot starts with content.
        body = [i for i in items if i["bbox"]["y"] > status_bar_cut or not parse_clock(i["text"])
                or parse_datetime(i["text"])]

        # Status bar clock
        sb = None
        for it in items:
            if it["bbox"]["y"] <= status_bar_cut and parse_clock(it["text"]):
                sb = self._field(it, it["text"])
                break

        # Amount: the largest money-looking text in the upper half of the screen.
        best = None
        for it in body:
            if it["bbox"]["y"] > img_height * 0.55 or ":" in it["text"] or "%" in it["text"]:
                continue
            m = AMOUNT_RE.match(it["text"].replace(" ", ""))
            if not m:
                continue
            num = m.group("num").replace(",", "")
            if len(num.split(".")[0]) > 7:
                continue
            val = float(num)
            if not (1 <= val <= 1_000_000):
                continue
            score = it["bbox"]["height"] * it["confidence"] * (1.4 if m.group("cur") else 1.0)
            if not best or score > best[0]:
                best = (score, it, f"{val:.2f}")
        if not best:
            # Amount printed on the payee's line ("COMMON SERVICE CENTRE ₹8,375", OCR may read ₹ as ?), or
            # lower down next to the debit account, as PhonePe does.
            for it in body:
                text = it["text"].replace(" ", "")
                m = TRAILING_AMOUNT_RE.search(text) if it["bbox"]["y"] <= img_height * 0.55 else None
                standalone = AMOUNT_RE.match(text) if ":" not in text and "%" not in text else None
                cand = m.group("num") if m else (standalone.group("num") if standalone and "," in text else None)
                if not cand:
                    continue
                val = float(cand.replace(",", ""))
                if 1 <= val <= 1_000_000:
                    score = it["bbox"]["height"] * it["confidence"]
                    if not best or score > best[0]:
                        best = (score, it, f"{val:.2f}")
        amount = self._field(best[1], best[2]) if best else self._field(None)

        words = None
        for it in body:
            t = it["text"].lower()
            if ("rupee" in t or "only" in t) and words_to_number(it["text"]) is not None:
                words = self._field(it, it["text"])
                break

        # UTR / reference: digits near a reference label; fall back to any 12-digit number.
        def utr_pred(it: Item, same_line: bool) -> Optional[str]:
            text = it["text"]
            if same_line:
                text = re.split(r"(?i)(?:utr|ref(?:erence)?\.?\s*no\.?|transaction\s*id|txn\s*id|rrn|:)", text)[-1]
            # Lookarounds, not \b: OCR glues buttons onto the number ("440995361349Copy").
            m = re.search(r"(?<![0-9A-Za-z])(T\d{20,23}|\d{6,22})(?!\d)", text.replace(" ", ""))
            return m.group(1) if m else None

        # An explicit "UTR" line wins: it is the number bank SMS quote. App IDs (PhonePe's T...) come next.
        found = self._after_label(body, ("utr",), utr_pred) or self._after_label(body, UTR_LABELS, utr_pred)
        if found:
            utr = self._field(found[0], found[1], min(1.0, found[0]["confidence"] + 0.05))
        else:
            fallback = None
            for i in body:
                m = re.search(r"(?<!\d)(\d{12})(?!\d)", i["text"].replace(" ", ""))
                if m and not VPA_RE.search(i["text"]):
                    fallback = (i, m.group(1))
                    break
            utr = self._field(fallback[0], fallback[1]) if fallback else self._field(None)

        # Timestamp
        ts = self._field(None)
        for idx, it in enumerate(body):
            if not re.search(r"\d", it["text"]):
                continue  # labels such as "Date & time" carry no value
            dt = parse_datetime(it["text"])
            if not dt and idx + 1 < len(body):
                # Date and time split over two OCR lines ("23 Oct 2026" / "2:32 PM").
                dt = parse_datetime(it["text"] + " " + body[idx + 1]["text"])
            if dt:
                ts = self._field(it, dt.strftime("%d %b %Y, %I:%M %p"))
                break

        # Receiver: name and VPA below a "Paid to" label, before any "From" label.
        # Paytm and PhonePe print a bare "To" line above the payee.
        to_idx = next((i for i, it in enumerate(body)
                       if _has_label(it["text"], TO_LABELS) or _norm(it["text"]) in ("to", "to:")), None)
        from_idx = next((i for i, it in enumerate(body)
                         if _norm(it["text"]) in ("from", "debitedfrom", "paidby", "sender")
                         or _norm(it["text"]).startswith("from")), None)
        receiver = receiver_vpa = sender = self._field(None)
        if to_idx is not None:
            end = from_idx if from_idx is not None and from_idx > to_idx else min(len(body), to_idx + 4)
            window = body[to_idx:end]
            for j, it in enumerate(window):
                m = VPA_RE.search(it["text"].replace(" ", ""))
                if m and not receiver_vpa.value:
                    receiver_vpa = self._field(it, m.group(1).lower())
                elif j > 0 and not receiver.value and not m and not AMOUNT_RE.match(it["text"].replace(" ", "")):
                    receiver = self._field(it, it["text"])
            label_rest = re.sub(r"(?i)^(paid to|sent to|paying|transfer to|to:?)\s*", "", body[to_idx]["text"]).strip()
            if _norm(body[to_idx]["text"]) in ("to", "to:"):
                label_rest = ""
            if not receiver.value and len(label_rest) > 2 and not VPA_RE.search(label_rest):
                receiver = self._field(body[to_idx], label_rest)
        if not receiver_vpa.value:
            for i, it in enumerate(body):
                if from_idx is not None and i > from_idx:
                    break
                m = VPA_RE.search(it["text"].replace(" ", ""))
                if m:
                    receiver_vpa = self._field(it, m.group(1).lower())
                    break
        if receiver.value:
            trimmed = re.sub(r"\s*(?:₹|rs\.?|\?)\s*\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?$", "", receiver.value, flags=re.I)
            receiver.value = trimmed or receiver.value
        if from_idx is not None and from_idx + 1 < len(body):
            nxt = body[from_idx + 1]
            if not VPA_RE.search(nxt["text"]):
                sender = self._field(nxt, nxt["text"])

        # Status: failure words win over success words.
        status = self._field(None)
        for words_set in (FAIL_WORDS, SUCCESS_WORDS):
            hit = next((it for it in body if it["bbox"]["y"] < img_height * 0.5
                        and any(w in it["text"].lower() for w in words_set)
                        and not _has_label(it["text"], TO_LABELS + ("rupees",))), None)
            if hit:
                status = self._field(hit, hit["text"])
                break

        note_found = self._after_label(body, NOTE_LABELS,
                                       lambda it, same: None if same else (it["text"] if len(it["text"]) > 1 else None),
                                       max_ahead=1)
        note = self._field(note_found[0], note_found[1]) if note_found else self._field(None)

        txn = next(((it, m.group(1)) for it in body for m in [APP_TXN_RE.search(it["text"].replace(" ", ""))] if m), None)
        app_txn_id = self._field(txn[0], txn[1]) if txn else self._field(None)

        return ExtractedData(
            payment_app=app, app_txn_id=app_txn_id, amount=amount, utr=utr, timestamp=ts, sender=sender, receiver=receiver,
            receiver_upi_id=receiver_vpa, status=status, amount_in_words=words or self._field(None),
            status_bar_time=sb or self._field(None), note=note,
        )


upi_extractor = UPIExtractor()
