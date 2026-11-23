"""폴더로 가져온 명함을 자동 스캔하고, 수동 보정 대상을 구분한다.

Streamlit과 분리된 로직이다. 원본 바이트는 수정하지 않으며 명함별 실패를 격리한다.
"""

import csv
import hashlib
import io
import json
import re
from math import sqrt
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.contact.csv_service import CONTACT_FIELDS, safe_csv_value
from backend.image.scan_service import scan_auto_image, scan_manual_image


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
MAX_FILES = 80
MAX_TOTAL_BYTES = 120 * 1024 * 1024
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 12_000_000


def normalize_name(name: str) -> str:
    """업로드 경로는 UI 표시용으로만 정리하고, 서버 파일 경로로 사용하지 않는다."""
    name = str(name or "").replace("\\", "/")
    parts = [part for part in name.split("/") if part not in ("", ".", "..")]
    return "/".join(parts) or "unnamed"


def image_from_bytes(raw: bytes) -> Image.Image:
    """명함 크기 제한을 확인한 뒤 EXIF 방향을 반영한 RGB 이미지를 반환한다."""
    if not raw or len(raw) > MAX_FILE_BYTES:
        raise ValueError("이미지 1개는 12MB 이하만 처리할 수 있습니다.")

    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ValueError("이미지는 1,200만 픽셀 이하만 처리할 수 있습니다.")
            return ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError("이미지 파일이 손상되었거나 지원하지 않는 형식입니다.") from error


def _normalize_scan_result(raw: bytes) -> tuple[bytes, Image.Image]:
    """호모그래피 결과가 지나치게 클 때 OCR 제한에 맞게 축소한다."""
    with Image.open(io.BytesIO(raw)) as source:
        width, height = source.size
        if len(raw) <= MAX_FILE_BYTES and width * height <= MAX_PIXELS:
            return raw, source.copy()
        scale = min(1.0, 2400 / max(width, height), sqrt(3_000_000 / (width * height)))
        reduced = source.convert("RGB").resize(
            (max(2, round(width * scale)), max(2, round(height * scale))),
            Image.Resampling.LANCZOS,
        )
        output = io.BytesIO()
        reduced.save(output, format="PNG", optimize=True)
        return output.getvalue(), reduced


def input_signature(images: list[tuple[str, bytes]]) -> str:
    """입력 폴더가 바뀔 때에만 자동 스캔을 다시 실행하기 위한 식별값."""
    digest = hashlib.sha256()
    for name, data in sorted(images, key=lambda row: normalize_name(row[0])):
        digest.update(normalize_name(name).encode("utf-8", errors="replace"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def _reasonable_card(points, scanned_image: Image.Image, original_image: Image.Image) -> bool:
    """비정상적인 사각형을 자동 성공으로 확정하지 않는다.

    비표준 명함은 수동 보정으로 진행할 수 있다. 이 검사는 정확도 보증이 아니다.
    """
    if points is None:
        return False
    corners = np.asarray(points, dtype=np.float32)
    if corners.shape != (4, 2) or not np.isfinite(corners).all():
        return False
    area_ratio = cv2.contourArea(corners) / (original_image.width * original_image.height)
    if area_ratio < 0.08 or area_ratio > 1.05:
        return False
    if scanned_image.width < 80 or scanned_image.height < 45:
        return False
    ratio = scanned_image.width / scanned_image.height
    return 1.2 <= ratio <= 2.6 or 1 / 2.6 <= ratio <= 1 / 1.2


def scan_one(name: str, raw: bytes) -> dict:
    """이미지 한 장을 독립적으로 스캔한다. 실패한 이미지만 수동 대상으로 남긴다."""
    clean_name = normalize_name(name)
    digest = hashlib.sha256(clean_name.encode("utf-8") + b"\0" + raw).hexdigest()[:24]
    record = {
        "id": digest,
        "name": clean_name,
        "original_bytes": raw,
        "scanned_bytes": None,
        "status": "needs_manual",
        "message": "",
        "manual_points": [],
        "last_click": None,
        "click_version": 0,
        "manual_mode": False,
        "ocr": None,
    }

    try:
        image = image_from_bytes(raw)
        result, corners = scan_auto_image(image)
        if result is None:
            record["message"] = "자동으로 명함 모서리를 찾지 못했습니다. 네 모서리를 직접 지정해 주세요."
        else:
            output_bytes, scanned = _normalize_scan_result(result)
            if _reasonable_card(corners, scanned, image):
                record["scanned_bytes"] = output_bytes
                record["status"] = "auto"
                record["message"] = "자동 원근 보정 완료 (잘린 영역이 정확한지 확인하세요)."
            else:
                record["message"] = "명함으로 보기 어려운 사각형이 검출됐습니다. 수동 보정이 필요합니다."
    except (ValueError, cv2.error) as error:
        # 업로드 자체가 열리지 않는 파일과 자동 탐지 실패를 구분한다.
        try:
            image_from_bytes(raw)
        except ValueError as invalid:
            record["status"] = "error"
            record["message"] = str(invalid)
        else:
            record["message"] = f"자동 스캔 실패: {error}. 수동으로 보정할 수 있습니다."

    return record


def process_folder(images: list[tuple[str, bytes]], on_progress=None) -> list[dict]:
    """폴더 전체를 일괄 자동 스캔한다. UI 재실행과 파일 업로드는 호출자가 관리한다."""
    if not images:
        return []
    if len(images) > MAX_FILES:
        raise ValueError(f"한 번에 최대 {MAX_FILES}장의 이미지를 처리할 수 있습니다.")
    if sum(len(data) for _, data in images) > MAX_TOTAL_BYTES:
        raise ValueError("폴더 전체 용량은 120MB 이하로 제한됩니다.")

    # 동일한 상대 경로/파일 내용은 추가 업로드되어도 중복 처리하지 않는다.
    seen = set()
    records = []
    for name, data in sorted(images, key=lambda item: normalize_name(item[0]).casefold()):
        clean_name = normalize_name(name)
        if PurePosixPath(clean_name).suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        key = (clean_name, hashlib.sha256(data).digest())
        if key in seen:
            continue
        seen.add(key)
        records.append(scan_one(clean_name, data))
        if on_progress:
            on_progress(len(records), len(images), clean_name)
    return records


def apply_manual_scan(record: dict, points: list[tuple[int, int]]) -> None:
    """해당 명함만 수동 호모그래피로 교체하고, 이전 OCR 결과는 무효화한다."""
    if record.get("status") == "error":
        raise ValueError("이미지 자체를 열 수 없어 수동 보정을 진행할 수 없습니다.")
    if len(points) != 4:
        raise ValueError("네 모서리를 모두 선택해야 합니다.")
    image = image_from_bytes(record["original_bytes"])
    result = scan_manual_image(image, points)
    output_bytes, _ = _normalize_scan_result(result)
    record["scanned_bytes"] = output_bytes
    record["status"] = "manual"
    record["message"] = "수동 원근 보정 완료"
    record["manual_mode"] = False
    record["ocr"] = None
    record["ocr_error"] = None


def status_counts(records: list[dict]) -> dict[str, int]:
    return {
        "auto": sum(item["status"] == "auto" for item in records),
        "manual": sum(item["status"] == "manual" for item in records),
        "needs_manual": sum(item["status"] == "needs_manual" for item in records),
        "error": sum(item["status"] == "error" for item in records),
    }


def _archive_base_name(record: dict, index: int) -> str:
    base = PurePosixPath(record["name"]).stem
    base = re.sub(r"[^0-9A-Za-z가-힣._-]", "_", base).strip("._-")[:48] or "card"
    return f"{index:03d}_{base}"


def export_scans_zip(records: list[dict]) -> bytes:
    """보정된 이미지를 ZIP으로 묶는다. 파일명은 서버 경로와 무관하게 안전하게 생성한다."""
    output = io.BytesIO()
    manifest = []
    ocr_rows = []
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for index, item in enumerate(records, start=1):
            prefix = _archive_base_name(item, index)
            output_name = f"scanned/{prefix}.png" if item.get("scanned_bytes") else None
            if output_name:
                archive.writestr(output_name, item["scanned_bytes"])
            if item.get("ocr"):
                archive.writestr(f"ocr/{prefix}.txt", str(item["ocr"].get("text") or ""))
                ocr_rows.append({"source_file": item["name"], **item["ocr"].get("fields", {})})
            manifest.append({
                "source_file": item["name"],
                "status": item["status"],
                "message": item["message"],
                "scanned_file": output_name,
                "ocr_completed": bool(item.get("ocr")),
            })
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        if ocr_rows:
            csv_buffer = io.StringIO(newline="")
            columns = ["source_file", *CONTACT_FIELDS]
            writer = csv.DictWriter(csv_buffer, fieldnames=columns)
            writer.writeheader()
            for row in ocr_rows:
                writer.writerow({column: safe_csv_value(row.get(column, "")) for column in columns})
            archive.writestr("ocr_candidates.csv", csv_buffer.getvalue().encode("utf-8-sig"))
    return output.getvalue()
