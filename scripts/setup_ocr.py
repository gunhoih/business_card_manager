"""로컬 OCR 언어 모델 설치 및 환경 검사.

Windows 초기 설치: setup.cmd
엔진 확인: uv run python scripts/setup_ocr.py --locate-engine
모델 설치: uv run python scripts/setup_ocr.py
검사만: uv run python scripts/setup_ocr.py --check-only

Streamlit Community Cloud에서는 이 스크립트를 배포 과정에 실행하지 않는다.
packages.txt를 통해 Tesseract와 언어 데이터를 설치한다.
"""

import argparse
import hashlib
from pathlib import Path
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MODEL_DIR = ROOT / "data" / "ocr" / "tessdata"
# 공식 tessdata_fast main을 따라가지 않고 특정 Git commit에 고정한다.
MODEL_REVISION = "87416418657359cb625c412a48b6e1d6d41c29bd"
MODEL_BASE = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{MODEL_REVISION}"
# 크기 + Git blob SHA-1: 공식 GitHub 커밋 트리의 값. 손상/미완료 파일을 탐지한다.
MODEL_INFO = {
    "eng": (4113088, "bbef4675053b5b468cdb477053e28b1c698ba08e"),
    "kor": (1677415, "60986d44497689f3abace0b148199476d93292e1"),
    "chi_tra": (2366642, "1955cd8b8d076b898616e9c2c1ace65b43105356"),
    "chi_sim": (2469156, "388bac276d033d06e5ed5ba7a7ad14ae58f97dab"),
}
SUPPORTED = tuple(MODEL_INFO)
MAX_MODEL_BYTES = 50 * 1024 * 1024


def git_blob_sha1(file_path):
    """Git이 blob을 식별할 때 사용하는 SHA-1 계산."""
    file_path = Path(file_path)
    size = file_path.stat().st_size
    digest = hashlib.sha1()
    digest.update(f"blob {size}\0".encode("ascii"))
    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(256 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def model_is_valid(language, destination):
    expected_size, expected_sha = MODEL_INFO[language]
    destination = Path(destination)
    return (
        destination.is_file()
        and destination.stat().st_size == expected_size
        and git_blob_sha1(destination) == expected_sha
    )


def download_language(language, directory=MODEL_DIR, force=False):
    """정확한 파일만 재사용하며, 검증 완료된 모델만 원자적으로 교체한다."""
    if language not in SUPPORTED:
        raise ValueError(f"지원하지 않는 언어: {language}")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{language}.traineddata"

    if not force and model_is_valid(language, destination):
        print(f"[유지] {language}: 검사 통과 ({destination})")
        return destination

    if destination.exists():
        print(f"[교체] {language}: 손상되었거나 다른 버전의 모델입니다.")

    url = f"{MODEL_BASE}/{language}.traineddata"
    last_error = None
    for attempt in (1, 2, 3):
        temp_path = None
        try:
            print(f"[다운로드 {attempt}/3] {language}: {url}")
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=directory, prefix=f".{language}-", suffix=".tmp", delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                with urlopen(url, timeout=30) as response:
                    total = 0
                    while True:
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_MODEL_BYTES:
                            raise ValueError("모델 파일이 예상보다 큽니다.")
                        handle.write(chunk)

            if not model_is_valid(language, temp_path):
                raise ValueError(f"{language} 모델 검증 실패: 크기 또는 Git blob 해시 불일치")
            temp_path.replace(destination)
            print(f"[완료] {destination} ({total:,}B, 내용 검사 통과)")
            return destination
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as error:
            last_error = error
            if attempt < 3:
                print(f"[재시도] {language}: {error}")
                time.sleep(attempt)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
    raise RuntimeError(f"{language} 모델 다운로드 실패: {last_error}")


def _check_engine_path():
    from backend.ocr.service import resolve_tesseract_cmd
    return resolve_tesseract_cmd()


def check_runtime(languages, smoke=True):
    from backend.ocr.service import available_languages, recognize_text

    installed = set(available_languages())
    missing = set(languages) - installed
    print("[엔진 확인] 언어 목록: " + ", ".join(sorted(installed)))
    if missing:
        raise RuntimeError(
            "Tesseract에 언어 모델이 표시되지 않습니다: " + ", ".join(sorted(missing))
            + ". 로컬은 setup.cmd, Streamlit Cloud는 packages.txt를 확인하세요."
        )

    if smoke:
        from PIL import Image, ImageDraw

        sample = Image.new("RGB", (600, 120), "white")
        ImageDraw.Draw(sample).text((16, 16), "TEST 12345", fill="black")
        # 모든 요청 언어를 실제로 로드하고 인식 호출까지 검사한다.
        # 인식 문구 자체는 운영체제 글꼴에 좌우되므로 검사하지 않는다.
        selected = "+".join(languages)
        recognize_text(sample, languages=selected, psm=6, timeout=30)
        print(f"[실행 검사] {selected} 모델을 사용한 샘플 OCR 호출 성공")


def main(argv=None):
    parser = argparse.ArgumentParser(description="OCR 엔진 검사와 모델 설치")
    parser.add_argument("--languages", nargs="+", choices=SUPPORTED, default=["eng", "kor", "chi_tra"])
    parser.add_argument("--force", action="store_true", help="언어 모델 강제 재설치")
    parser.add_argument("--locate-engine", action="store_true", help="엔진 위치만 출력하고 종료")
    parser.add_argument("--check-only", action="store_true", help="네트워크 없이 설치 상태만 검사")
    parser.add_argument("--skip-smoke", action="store_true", help="샘플 이미지 실행 검사 생략")
    args = parser.parse_args(argv)

    try:
        engine = _check_engine_path()
    except RuntimeError as error:
        print(f"[실패] {error}", file=sys.stderr)
        return 2

    if not engine:
        print(
            "[실패] Tesseract 실행 파일이 없거나 실행되지 않습니다. "
            "Windows에서는 winget 설치 위치와 사용자별 설치 폴더를 확인하세요.",
            file=sys.stderr,
        )
        return 1

    if args.locate_engine:
        print(engine)
        return 0

    print(f"[엔진 확인] {engine}")
    languages = tuple(dict.fromkeys(args.languages))
    try:
        if args.check_only:
            # 로컬 모델이 있으면 손상 여부를 반드시 확인한다.
            from backend.ocr.service import resolve_tessdata_dir
            model_dir = resolve_tessdata_dir()
            if model_dir and Path(model_dir).is_dir():
                for language in languages:
                    model = Path(model_dir) / f"{language}.traineddata"
                    if model.is_file() and Path(model_dir).resolve() == MODEL_DIR.resolve():
                        if not model_is_valid(language, model):
                            raise RuntimeError(f"{language} 로컬 모델이 손상되었습니다. setup.cmd를 다시 실행하세요.")
        else:
            from backend.ocr.service import resolve_tessdata_dir
            custom = resolve_tessdata_dir()
            # 명시적인 시스템 경로가 있으면 다운로드 대상과 실행 경로가 달라질 수 있다.
            # 이 경우 사용자 설정을 존중하고, 저장 위치 안내 후 검사 결과로 확인한다.
            for language in languages:
                download_language(language, force=args.force)
            if custom and Path(custom).resolve() != MODEL_DIR.resolve():
                print(f"[주의] OCR_TESSDATA_DIR이 지정되어 있어 별도 모델 경로를 사용합니다: {custom}")

        check_runtime(languages, smoke=not args.skip_smoke)
    except (RuntimeError, ValueError, OSError) as error:
        print(f"[실패] {error}", file=sys.stderr)
        return 1

    print("[정상] OCR 엔진과 요청한 언어 모델을 사용할 수 있습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
