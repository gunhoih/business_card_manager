"""PP-OCRv5 한국어·영어 ONNX 추론. 검출/방향 모델을 공유하고 순차 실행한다."""

from functools import lru_cache
from math import ceil, floor, isfinite
from threading import Lock
from time import monotonic

from PIL import Image
import numpy as np

from backend.ocr.model_store import MODEL_DIR, ensure_models
from backend.ocr.service import OCRLine, OCRResult

_INFERENCE_LOCK = Lock()


def _verified_paths():
    # 파일 검증 결과는 model_store에서 캐시하고, 누락되면 자동으로 복구한다.
    return ensure_models()


@lru_cache(maxsize=2)
def _load_engine(model="korean"):
    if model not in ("korean", "english"):
        raise ValueError("지원하지 않는 OCR 인식 모델입니다.")
    paths = _verified_paths()
    try:
        import onnxruntime as ort
        from rapidocr import EngineType, LangRec, ModelType, OCRVersion, RapidOCR
    except ImportError as error:
        raise RuntimeError("RapidOCR 실행 환경이 없습니다. setup_rapidocr.cmd를 실행하세요.") from error

    # 공식 ONNX 모델 내장 사전을 확인하여 실행 중 외부 사전 다운로드를 막는다.
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    try:
        recognition_file = f"{model}_recognition.onnx"
        session = ort.InferenceSession(str(paths[recognition_file]),
                                       sess_options=options, providers=["CPUExecutionProvider"])
        characters = session.get_modelmeta().custom_metadata_map.get("character", "")
        if not characters or not all(char in characters for char in "aA09@."):
            raise RuntimeError("영문·숫자·이메일용 내장 문자 사전을 확인하지 못했습니다.")
        if model == "korean" and not any("가" <= char <= "힣" for char in characters):
            raise RuntimeError("한국어 내장 문자 사전을 확인하지 못했습니다.")
        del session
        params = {
            "Global.model_root_dir": str(MODEL_DIR),
            "Global.max_side_len": 1800,
            "Global.text_score": 0.25,
            "Global.log_level": "warning",
            "Global.return_word_box": False,
            "Global.use_det": model == "korean",
            "Global.use_cls": model == "korean",
            "EngineConfig.onnxruntime.intra_op_num_threads": 1,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "EngineConfig.onnxruntime.enable_cpu_mem_arena": False,
            "EngineConfig.onnxruntime.use_cuda": False,
            "Det.limit_side_len": 1600,
            "Det.limit_type": "max",
            "Det.box_thresh": 0.45,
            "Det.max_candidates": 200,
            "Rec.lang_type": LangRec.KOREAN if model == "korean" else LangRec.EN,
            "Rec.rec_batch_num": 2,
            "Cls.cls_batch_num": 4,
            "Cls.cls_image_shape": [3, 80, 160],
        }
        for section, name in (("Det", "detection.onnx"), ("Rec", recognition_file),
                              ("Cls", "orientation.onnx")):
            params[f"{section}.engine_type"] = EngineType.ONNXRUNTIME
            params[f"{section}.ocr_version"] = OCRVersion.PPOCRV5
            params[f"{section}.model_type"] = ModelType.MOBILE
            params[f"{section}.model_path"] = str(paths[name])
        return RapidOCR(params=params)
    except RuntimeError:
        raise
    except Exception as error:
        raise RuntimeError(f"RapidOCR {model} 모델 초기화 실패 ({type(error).__name__}). 모델과 설치 환경을 확인하세요.") from error


def check_rapidocr():
    """라이브러리와 모델을 준비한다. 실제 추론 엔진은 필요한 시점에만 로드한다."""
    from importlib.util import find_spec
    if find_spec("rapidocr") is None or find_spec("onnxruntime") is None:
        raise RuntimeError("RapidOCR 또는 ONNX Runtime이 설치되지 않았습니다. uv sync를 실행하세요.")
    _verified_paths()
    return "RapidOCR · PP-OCRv5 Korean + English Mobile · CPU"


def output_to_lines(result, width, height):
    """RapidOCR 사각형 좌표와 0~1 인식 점수를 기존 OCRLine 규격으로 변환한다."""
    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None)
    scores = getattr(result, "scores", None)
    if boxes is None or texts is None or scores is None:
        return []
    lines = []
    for box, text, score in zip(boxes, texts, scores):
        text = str(text or "").strip()
        if not text:
            continue
        try:
            points = np.asarray(box, dtype=float).reshape(-1, 2)
            score = float(score)
            if len(points) < 4 or not np.isfinite(points).all() or not isfinite(score):
                continue
            x1 = max(0, min(width, floor(points[:, 0].min())))
            y1 = max(0, min(height, floor(points[:, 1].min())))
            x2 = max(0, min(width, ceil(points[:, 0].max())))
            y2 = max(0, min(height, ceil(points[:, 1].max())))
        except (TypeError, ValueError, OverflowError):
            continue
        if x2 <= x1 or y2 <= y1:
            continue
        lines.append(OCRLine(text, x1, y1, x2 - x1, y2 - y1,
                             round(max(0.0, min(1.0, score)) * 100, 1)))
    return sorted(lines, key=lambda line: (line.top, line.left))


def recognize_rapid(image, timeout=30, *, line_only=False, model="korean"):
    """한국어는 전체/줄 인식, 영어는 이미 검출한 줄만 인식한다.

    두 엔진은 잠금으로 보호된다. 영어 인식은 한국어 엔진의 방향 모델을 재사용하며
    검출 모델을 재실행하지 않는다. ONNX 추론 중 강제 취소는 지원하지 않는다.
    """
    if not isinstance(image, Image.Image):
        raise ValueError("Pillow 이미지가 필요합니다.")
    if model not in ("korean", "english") or (model == "english" and not line_only):
        raise ValueError("영어 보조 모델은 검출된 단일 줄에서만 사용할 수 있습니다.")
    if timeout <= 0:
        raise ValueError("OCR 처리 제한 시간은 양수여야 합니다.")
    # 최초 다운로드는 추론 시간 예산과 분리한다. 이후에는 파일 검증 캐시를 사용한다.
    check_rapidocr()
    deadline = monotonic() + float(timeout)
    if not _INFERENCE_LOCK.acquire(timeout=float(timeout)):
        raise RuntimeError("OCR 실행 대기 시간이 초과되었습니다. 다시 시도해 주세요.")
    try:
        engine = _load_engine(model)
        if monotonic() >= deadline:
            raise RuntimeError("OCR 모델 초기화 시간이 초과되었습니다. 다시 시도해 주세요.")
        source = image.convert("RGB")
        if model == "english":
            # 전체 이미지가 아닌 이미 검출된 줄의 0/180도 방향만 교정한다.
            orientation = _load_engine("korean")(source, use_det=False, use_cls=True,
                                                  use_rec=False, return_word_box=False)
            crops = getattr(orientation, "img_list", None)
            if crops is not None and len(crops) == 1:
                source = crops[0]  # RapidOCR이 반환한 BGR 배열
            if monotonic() >= deadline:
                raise RuntimeError("영문 보조 인식 시간 예산을 소진했습니다.")
            result = engine(source, use_det=False, use_cls=False, use_rec=True,
                            text_score=0.25, return_word_box=False)
        else:
            # RapidOCR __call__은 실행 옵션을 바꾸므로 매번 명시적으로 지정한다.
            result = engine(source, use_det=not line_only, use_cls=True,
                            use_rec=True, text_score=0.25, return_word_box=False)
        if line_only:
            texts = getattr(result, "txts", None)
            scores = getattr(result, "scores", None)
            lines = [] if texts is None or scores is None else [
                OCRLine(str(text).strip(), 0, 0, image.width, image.height, round(float(score) * 100, 1))
                for text, score in zip(texts, scores)
                if str(text).strip() and isfinite(float(score)) and 0 <= float(score) <= 1
            ]
        else:
            lines = output_to_lines(result, image.width, image.height)
        return OCRResult("\n".join(line.text for line in lines), lines, "eng" if model == "english" else "kor+eng")
    except (RuntimeError, ValueError):
        raise
    except Exception as error:
        raise RuntimeError(f"RapidOCR 인식 실패 ({type(error).__name__}).") from error
    finally:
        _INFERENCE_LOCK.release()
