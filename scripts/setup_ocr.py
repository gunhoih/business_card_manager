"""Tesseract 공식 tessdata_fast 언어 모델을 로컬에 다운로드한다.

사용: uv run python scripts/setup_ocr.py
Tesseract 실행 프로그램 자체는 OS별로 별도 설치해야 한다.
"""

import argparse
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "data" / "ocr" / "tessdata"
MODEL_BASE = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main"
SUPPORTED = ("eng", "kor", "chi_tra", "chi_sim")
MAX_MODEL_BYTES = 50 * 1024 * 1024
MIN_MODEL_BYTES = 100 * 1024


def download_language(language, directory=MODEL_DIR, force=False):
    if language not in SUPPORTED:
        raise ValueError(f"지원하지 않는 언어: {language}")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{language}.traineddata"

    if destination.is_file() and destination.stat().st_size >= MIN_MODEL_BYTES and not force:
        print(f"[건너뜀] {language}: 이미 존재 ({destination.stat().st_size:,}B)")
        return destination

    url = f"{MODEL_BASE}/{language}.traineddata"
    print(f"[다운로드] {language}: {url}")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=directory, prefix=f".{language}_", suffix=".tmp", delete=False) as handle:
            tmp = Path(handle.name)
            with urlopen(url, timeout=35) as response:
                total = 0
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_MODEL_BYTES:
                        raise ValueError(f"{language}: 언어 모델 파일이 예상보다 큽니다.")
                    handle.write(chunk)
        if total < MIN_MODEL_BYTES:
            raise ValueError(f"{language}: 받은 언어 모델 파일이 예상보다 작습니다.")
        tmp.replace(destination)
        print(f"[완료] {destination} ({total:,}B)")
        return destination
    finally:
        if tmp and tmp.exists():
            tmp.unlink()


def main():
    parser = argparse.ArgumentParser(description="Tesseract 언어 모델 설치")
    parser.add_argument("--languages", nargs="+", choices=SUPPORTED, default=["eng", "kor", "chi_tra"])
    parser.add_argument("--force", action="store_true", help="모델 다시 받기")
    args = parser.parse_args()

    try:
        for language in dict.fromkeys(args.languages):
            download_language(language, force=args.force)
    except (URLError, HTTPError, TimeoutError, ValueError, OSError) as error:
        print(f"[실패] OCR 모델 다운로드 중 오류: {error}", file=sys.stderr)
        print("네트워크 접근이 되는지 확인하고 다시 실행해 주세요.", file=sys.stderr)
        return 1

    sys.path.insert(0, str(ROOT))
    from backend.ocr.service import available_languages
    try:
        installed = set(available_languages())
    except RuntimeError as error:
        print(f"[주의] 모델은 준비했지만 실행 엔진 확인에 실패했습니다: {error}", file=sys.stderr)
        return 1

    missing = set(args.languages) - installed
    if missing:
        print(f"[실패] Tesseract에 보이지 않는 언어: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1

    print(f"[정상] 사용할 수 있는 언어: {', '.join(args.languages)}")
    print("이제 uv run streamlit run app.py 로 실행할 수 있습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
