#!/usr/bin/env bash
# Ubuntu/Debian self-hosted Streamlit 서버용 (Community Cloud에서는 실행하지 않음)
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v apt-get >/dev/null 2>&1; then
    echo '이 스크립트는 Ubuntu/Debian apt 환경 전용입니다.' >&2
    exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
    apt-get update
    apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-kor tesseract-ocr-chi-tra
elif command -v sudo >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-kor tesseract-ocr-chi-tra
else
    echo '시스템 패키지 설치에는 root 또는 sudo 권한이 필요합니다.' >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo 'uv를 설치한 뒤 다시 실행하세요: https://docs.astral.sh/uv/' >&2
    exit 1
fi

uv sync
uv run python scripts/setup_ocr.py --check-only --languages eng kor chi_tra

echo '서버 OCR 설치 완료. uv run streamlit run app.py'
