"""공식 OCR 모델을 필요할 때만 다운로드하고 검증된 파일을 재사용한다."""

from functools import lru_cache
from hashlib import sha256
from http.client import HTTPException
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from time import monotonic
from urllib.request import Request, urlopen

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


# 두 릴리스의 네 파일은 공식 레지스트리에서 동일한 SHA-256을 확인했다.
DOWNLOAD_RELEASES = (RELEASE, "v3.9.2")
PREPARE_SECONDS = 180.0
SOCKET_SECONDS = 20.0
_DOWNLOAD_LOCK = Lock()
logger = logging.getLogger(__name__)


def model_digest(path):
    digest = sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=32)
def _verified_digest(path, fingerprint, expected):
    # 파일 크기나 수정 시각 등이 바뀌면 SHA-256을 다시 검사한다.
    return model_digest(path) == expected


def valid_model(path, expected):
    path = Path(path)
    try:
        stat = path.stat()
        if not path.is_file() or not 0 < stat.st_size <= MAX_MODEL_BYTES:
            return False
        fingerprint = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
        return _verified_digest(path.resolve(), fingerprint, expected)
    except OSError:
        return False


def model_paths(directory=MODEL_DIR, *, verify=True):
    """기존 파일만 확인한다. 다운로드는 ensure_models에서만 수행한다."""
    paths = {name: Path(directory) / name for name in MODEL_SPECS}
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise RuntimeError("RapidOCR 모델 누락: " + ", ".join(missing)
                           + ". OCR 실행 시 자동으로 준비하거나 scripts/setup_rapidocr.py를 실행하세요.")
    if verify:
        invalid = [name for name, path in paths.items()
                   if not valid_model(path, MODEL_SPECS[name][1])]
        if invalid:
            raise RuntimeError("RapidOCR 모델 손상 또는 Git LFS 포인터: " + ", ".join(invalid))
    return paths


def _download_model(path, route, expected, deadline):
    """임시 파일에서 검증을 완료한 뒤 원자적으로 모델 경로에 반영한다."""
    errors = []
    for release in DOWNLOAD_RELEASES:
        remaining = deadline - monotonic()
        if remaining <= 0:
            errors.append("모델 준비 시간 예산 소진")
            break
        url = f"{BASE_URL}/{release}/onnx/PP-OCRv5/{route}"
        temporary = None
        try:
            request = Request(url, headers={"User-Agent": "BusinessCardManager/RapidOCR"})
            digest = sha256()
            total = 0
            with NamedTemporaryFile(dir=path.parent, prefix=path.name + ".",
                                    suffix=".part", delete=False) as file:
                temporary = Path(file.name)
                with urlopen(request, timeout=min(SOCKET_SECONDS, remaining)) as response:
                    while True:
                        if monotonic() >= deadline:
                            raise RuntimeError("모델 다운로드 시간 초과")
                        block = response.read(64 * 1024)
                        if not block:
                            break
                        total += len(block)
                        if total > MAX_MODEL_BYTES:
                            raise RuntimeError("모델 파일 크기 제한 초과")
                        digest.update(block)
                        file.write(block)
            if monotonic() >= deadline:
                raise RuntimeError("모델 다운로드 시간 초과")
            if not total or digest.hexdigest() != expected:
                raise RuntimeError("SHA-256 불일치")
            temporary.replace(path)
            logger.info("RapidOCR model ready: %s (%d bytes)", path.name, total)
            return
        except (OSError, ValueError, RuntimeError, HTTPException) as error:
            # 명함이나 사용자 데이터는 이 다운로드 요청에 포함되지 않는다.
            errors.append(f"{release}: {type(error).__name__} ({error})")
            logger.warning("RapidOCR model download attempt failed: %s, %s", path.name, release)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    detail = "; ".join(errors)
    raise RuntimeError(f"RapidOCR 모델 자동 준비 실패: {path.name}. "
                       f"ModelScope 네트워크 연결과 디스크 권한을 확인한 뒤 다시 시도하세요. ({detail})")


def ensure_models(directory=MODEL_DIR, *, timeout=PREPARE_SECONDS):
    """네 모델을 최초 한 번 준비한다. 동일 프로세스의 여러 세션은 다운로드를 공유한다."""
    directory = Path(directory).resolve()
    deadline = monotonic() + timeout
    if timeout <= 0 or not _DOWNLOAD_LOCK.acquire(timeout=timeout):
        raise RuntimeError("다른 OCR 모델 준비가 끝나지 않았습니다. 잠시 후 다시 시도하세요.")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for name, (route, expected) in MODEL_SPECS.items():
            path = directory / name
            if valid_model(path, expected):
                continue
            if monotonic() >= deadline:
                raise RuntimeError("OCR 모델 준비 시간이 초과되었습니다. 다시 시도하세요.")
            logger.info("Downloading RapidOCR model: %s", name)
            _download_model(path, route, expected, deadline)
        return model_paths(directory)
    except OSError as error:
        raise RuntimeError(f"OCR 모델 캐시 폴더에 접근할 수 없습니다: {directory} ({error})") from error
    finally:
        _DOWNLOAD_LOCK.release()
