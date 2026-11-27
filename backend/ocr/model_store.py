"""공식 ONNX 모델의 경로, 버전 및 무결성을 관리한다. 앱 실행 중 다운로드하지 않는다."""

from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = ROOT / "models" / "ocr"
RELEASE = "v3.10.0"
BASE_URL = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve"
MODEL_SPECS = {
    "detection.onnx": (
        "det/ch_PP-OCRv5_det_mobile.onnx",
        "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae",
    ),
    "korean_recognition.onnx": (
        "rec/korean_PP-OCRv5_rec_mobile.onnx",
        "cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b",
    ),
    "english_recognition.onnx": (
        "rec/en_PP-OCRv5_rec_mobile.onnx",
        "c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8",
    ),
    "orientation.onnx": (
        "cls/ch_PP-LCNet_x0_25_textline_ori_cls_mobile.onnx",
        "54379ae5174d026780215fc748a7f31910dee36818e63d49e17dc598ecc82df7",
    ),
}
MAX_MODEL_BYTES = 25 * 1024 * 1024


def model_digest(path):
    digest = sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_model(path, expected):
    path = Path(path)
    return (path.is_file() and 0 < path.stat().st_size <= MAX_MODEL_BYTES
            and model_digest(path) == expected)


def model_paths(directory=MODEL_DIR, *, verify=True):
    paths = {name: Path(directory) / name for name in MODEL_SPECS}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise RuntimeError("RapidOCR 모델 누락: " + ", ".join(missing)
                           + ". 로컬에서 setup_rapidocr.cmd를 실행한 뒤 models/ocr를 Git에 포함하세요.")
    if verify:
        invalid = [name for name, path in paths.items()
                   if not valid_model(path, MODEL_SPECS[name][1])]
        if invalid:
            raise RuntimeError("RapidOCR 모델 손상 또는 Git LFS 포인터: " + ", ".join(invalid)
                               + ". scripts/setup_rapidocr.py로 다시 준비하세요.")
    return paths
