import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from app.config import settings

log = logging.getLogger("pramaan.ocr")

# OCR runs on a downscaled copy; phone screenshots stay legible at this width and it is several times faster.
OCR_WIDTH = 720


class OCREngine:
    """RapidOCR (PP-OCRv4 via onnxruntime) with a pytesseract fallback. Boxes are returned in original pixels."""

    def __init__(self) -> None:
        self._ocr = None
        self._name = "unavailable"
        self._lock = threading.Lock()
        self._initialized = False

    @property
    def name(self) -> str:
        return self._name

    def warm_up(self) -> None:
        engine = self._get()
        if engine is not None:
            try:
                engine(np.full((64, 256, 3), 255, np.uint8))
            except Exception:  # pragma: no cover - warm-up is best effort
                pass

    def _get(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    try:
                        from rapidocr_onnxruntime import RapidOCR
                        self._ocr = RapidOCR(det_limit_type="max", det_limit_side_len=960, use_cls=False,
                                             **({"intra_op_num_threads": settings.OCR_THREADS} if settings.OCR_THREADS else {}))
                        self._name = "rapidocr-onnxruntime"
                    except Exception as e:  # pragma: no cover
                        log.warning("RapidOCR unavailable (%s); falling back to tesseract", e)
                        self._ocr = None
                        self._name = "tesseract"
                    self._initialized = True
        return self._ocr

    @staticmethod
    def check_image_quality(img: Optional[np.ndarray]) -> Tuple[bool, Optional[str]]:
        if img is None or img.size == 0:
            return False, "The file could not be read as an image."
        h, w = img.shape[:2]
        if min(h, w) < settings.MIN_IMAGE_DIMENSION:
            return False, f"Image is too small ({w}x{h} px). Send the full phone screenshot, not a thumbnail."
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
        scale = OCR_WIDTH / w if w > OCR_WIDTH else 1.0
        if scale < 1:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        focus = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if focus < settings.MIN_FOCUS_SCORE:
            return False, (f"Image quality too low: the screenshot is too blurry to read reliably "
                           f"(focus score {focus:.0f}). Ask for the original screenshot instead of a photo.")
        return True, None

    def extract(self, img: np.ndarray) -> List[Dict[str, Any]]:
        """Returns [{text, confidence, bbox: {x, y, width, height}}] sorted top-to-bottom."""
        h, w = img.shape[:2]
        scale = OCR_WIDTH / w if w > OCR_WIDTH else 1.0
        small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img
        inv = 1.0 / scale

        items: List[Dict[str, Any]] = []
        engine = self._get()
        if engine is not None:
            try:
                with self._lock:
                    out, _ = engine(small)
                for pts, text, score in out or []:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    x0, y0 = int(min(xs) * inv), int(min(ys) * inv)
                    x1, y1 = int(max(xs) * inv), int(max(ys) * inv)
                    items.append({
                        "text": str(text).strip(),
                        "confidence": round(float(score), 4),
                        "bbox": {"x": max(0, x0), "y": max(0, y0), "width": max(1, x1 - x0), "height": max(1, y1 - y0)},
                    })
            except Exception as e:  # pragma: no cover
                log.error("RapidOCR failed: %s", e)
        else:
            items = self._tesseract(small, inv)

        items = [i for i in items if i["text"]]
        items.sort(key=lambda i: (i["bbox"]["y"], i["bbox"]["x"]))
        return items

    @staticmethod
    def _tesseract(img: np.ndarray, inv: float) -> List[Dict[str, Any]]:  # pragma: no cover - fallback path
        try:
            import pytesseract
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        except Exception as e:
            log.error("Tesseract unavailable: %s", e)
            return []
        lines: Dict[Tuple[int, int, int], Dict[str, Any]] = {}
        for i, txt in enumerate(data["text"]):
            conf = float(data["conf"][i])
            if not txt.strip() or conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x, y, bw, bh = (int(data[k][i] * inv) for k in ("left", "top", "width", "height"))
            ln = lines.setdefault(key, {"words": [], "confs": [], "x0": x, "y0": y, "x1": x + bw, "y1": y + bh})
            ln["words"].append(txt.strip())
            ln["confs"].append(conf / 100)
            ln["x0"], ln["y0"] = min(ln["x0"], x), min(ln["y0"], y)
            ln["x1"], ln["y1"] = max(ln["x1"], x + bw), max(ln["y1"], y + bh)
        return [{
            "text": " ".join(ln["words"]),
            "confidence": round(sum(ln["confs"]) / len(ln["confs"]), 4),
            "bbox": {"x": ln["x0"], "y": ln["y0"], "width": ln["x1"] - ln["x0"], "height": ln["y1"] - ln["y0"]},
        } for ln in lines.values()]


ocr_engine = OCREngine()
