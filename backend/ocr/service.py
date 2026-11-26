"""Tesseract OCR 실행 파일 탐지와 명함 텍스트 인식.

Windows에서는 PATH가 설치 직후 갱신되지 않아도 실행 파일을 찾도록 하고,
Linux(Streamlit Cloud)에서는 시스템 패키지로 설치한 tesseract를 사용한다.
"""

from collections import defaultdict
from dataclasses import dataclass
from threading import RLock
from time import monotonic
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytesseract
from PIL import Image
from pytesseract import Output, TesseractError, TesseractNotFoundError


ROOT = Path(__file__).resolve().parents[2]
LOCAL_TESSDATA = ROOT / "data" / "ocr" / "tessdata"
SUPPORTED_LANGUAGES = {"eng", "kor", "chi_tra", "chi_sim"}
_ENGINE_LOCK = RLock()
_ENGINE_CACHE = {}
_LANGUAGE_CACHE = {}
CACHE_SECONDS = 30
# 사용자별 데이터는 캐싱하지 않는다. 서버의 엔진 경로와 설치 언어만 캐싱한다.
_INITIAL_TESSDATA_PREFIX = os.environ.get("TESSDATA_PREFIX")
_MANAGED_TESSDATA_PREFIX = None


@dataclass(frozen=True)
class OCRLine:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float


@dataclass(frozen=True)
class OCRResult:
    text: str
    lines: list[OCRLine]
    languages: str


def _windows_registry_paths():
    """설치 관리자가 기록한 Tesseract 위치를 조회한다 (Windows 전용)."""
    try:
        import winreg
    except ImportError:
        return

    branches = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    )
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for branch in branches:
            try:
                root = winreg.OpenKey(hive, branch)
            except OSError:
                continue
            with root:
                try:
                    count = winreg.QueryInfoKey(root)[0]
                except OSError:
                    continue
                for index in range(count):
                    try:
                        key_name = winreg.EnumKey(root, index)
                        entry = winreg.OpenKey(root, key_name)
                    except OSError:
                        continue
                    with entry:
                        try:
                            name = str(winreg.QueryValueEx(entry, "DisplayName")[0])
                        except OSError:
                            continue
                        if "tesseract" not in name.casefold():
                            continue
                        try:
                            location = str(winreg.QueryValueEx(entry, "InstallLocation")[0]).strip().strip('"')
                            if location:
                                yield Path(os.path.expandvars(location)) / "tesseract.exe"
                        except OSError:
                            pass
                        try:
                            icon = str(winreg.QueryValueEx(entry, "DisplayIcon")[0]).strip()
                            # 예: '"C:\\...\\tesseract.exe",0'
                            matched = re.match(r'^\s*"?(.+?\.exe)"?(?:,\d+)?\s*$', icon, re.IGNORECASE)
                            if matched and Path(matched.group(1)).name.lower() == "tesseract.exe":
                                yield Path(os.path.expandvars(matched.group(1)))
                        except OSError:
                            pass

    # 일부 설치기는 App Paths를 등록한다.
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\tesseract.exe") as key:
                value = winreg.QueryValue(key, "")
                if value:
                    yield Path(os.path.expandvars(value))
        except OSError:
            pass


def _windows_candidate_paths(environ=None):
    """관리자/사용자 설치 및 패키지 매니저에서 사용하는 대표 위치."""
    env = os.environ if environ is None else environ
    candidates = []
    for name, suffix in (
        ("ProgramFiles", "Tesseract-OCR/tesseract.exe"),
        ("ProgramFiles(x86)", "Tesseract-OCR/tesseract.exe"),
        ("LOCALAPPDATA", "Programs/Tesseract-OCR/tesseract.exe"),
        ("LOCALAPPDATA", "Tesseract-OCR/tesseract.exe"),
        ("LOCALAPPDATA", "Microsoft/WinGet/Links/tesseract.exe"),
        ("USERPROFILE", "scoop/apps/tesseract/current/tesseract.exe"),
    ):
        base = env.get(name, "")
        if base:
            candidates.append(Path(base) / suffix)

    # Scoop/WinGet의 사용자별 패키지 설치 경로는 임의의 폴더명을 포함한다.
    for name, suffix in (
        ("LOCALAPPDATA", "Microsoft/WinGet/Packages"),
        ("USERPROFILE", "scoop/apps/tesseract"),
    ):
        base = env.get(name)
        if not base:
            continue
        parent = Path(base) / suffix
        if not parent.is_dir():
            continue
        try:
            for match in parent.iterdir():
                if "tesseract" not in match.name.casefold() or not match.is_dir():
                    continue
                candidates.append(match / "tesseract.exe")
                candidates.append(match / "Tesseract-OCR" / "tesseract.exe")
                candidates.append(match / "current" / "tesseract.exe")
        except OSError:
            continue
    return candidates


def _engine_version(command):
    """정상 확인된 실행 파일의 버전만 짧게 재사용한다."""
    key = str(command)
    with _ENGINE_LOCK:
        cached = _ENGINE_CACHE.get(key)
        if cached and monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        version = _read_engine_version(command)
        if version:
            _ENGINE_CACHE.clear()
            _ENGINE_CACHE[key] = (monotonic(), version)
        return version


def _read_engine_version(command):
    """실행 파일 존재 여부만 보지 않고 실제로 실행되는지 확인한다."""
    try:
        result = subprocess.run(
            [str(command), "--version"], capture_output=True, text=True, timeout=12, check=False,
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode == 0 and re.search(r"tesseract\s+v?[45]\.", output, re.IGNORECASE):
        return output.splitlines()[0]
    return None


def resolve_tesseract_cmd():
    """현재 OS에서 실행 가능한 Tesseract 4/5를 찾는다.

    OCR_TESSERACT_CMD가 지정되었지만 틀린 경우에는 다른 엔진을 조용히 쓰지 않는다.
    """
    custom = os.getenv("OCR_TESSERACT_CMD", "").strip().strip('"')
    if custom:
        path = shutil.which(custom) or custom
        if _engine_version(path):
            return str(path)
        raise RuntimeError(f"OCR_TESSERACT_CMD로 지정한 실행 파일을 사용할 수 없습니다: {custom}")

    candidates = []
    on_path = shutil.which("tesseract")
    if on_path:
        candidates.append(on_path)

    if os.name == "nt":
        candidates.extend(_windows_candidate_paths())
        candidates.extend(_windows_registry_paths())

    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        path = str(candidate)
        identity = path.casefold() if os.name == "nt" else path
        if identity in seen:
            continue
        seen.add(identity)
        if _engine_version(path):
            return path
    return None


def resolve_tessdata_dir():
    """명시 경로 > 프로젝트 모델 > 시스템 모델 순서로 선택한다.

    Streamlit Cloud는 data/ocr 아래 파일이 없으므로 Debian 패키지의 모델을 사용한다.
    """
    custom = os.getenv("OCR_TESSDATA_DIR", "").strip().strip('"')
    if custom:
        return Path(custom).expanduser().resolve()
    if LOCAL_TESSDATA.is_dir() and any(LOCAL_TESSDATA.glob("*.traineddata")):
        return LOCAL_TESSDATA
    return None


def _configure_engine():
    global _MANAGED_TESSDATA_PREFIX
    command = resolve_tesseract_cmd()
    if not command:
        raise RuntimeError(
            "Tesseract 4/5 실행 프로그램을 찾지 못했습니다. Windows에서는 setup.cmd를, "
            "Linux/Streamlit Cloud에서는 packages.txt를 확인하세요. "
            "직접 설치했다면 OCR_TESSERACT_CMD를 지정할 수 있습니다."
        )
    pytesseract.pytesseract.tesseract_cmd = command
    tessdata = resolve_tessdata_dir()
    if tessdata:
        if not tessdata.is_dir():
            raise RuntimeError(f"OCR 언어 모델 폴더를 찾지 못했습니다: {tessdata}")
        # pytesseract는 Windows에서 shlex.split(..., posix=False)을 사용한다.
        # --tessdata-dir "..." 형태를 넘기면 따옴표가 실제 경로에 남을 수 있다.
        # 모델 폴더를 Tesseract 공식 환경 변수로 전달하면 공백 경로도 안전하다.
        os.environ["TESSDATA_PREFIX"] = str(tessdata)
        _MANAGED_TESSDATA_PREFIX = str(tessdata)
    elif _MANAGED_TESSDATA_PREFIX is not None:
        # 이전에 앱이 적용한 프로젝트 경로를 시스템 모델로 돌아갈 때 제거한다.
        if os.environ.get("TESSDATA_PREFIX") == _MANAGED_TESSDATA_PREFIX:
            if _INITIAL_TESSDATA_PREFIX is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = _INITIAL_TESSDATA_PREFIX
        _MANAGED_TESSDATA_PREFIX = None
    return ""


def available_languages():
    """설치된 언어 확인도 시간 제한을 두고 성공한 결과만 짧게 재사용한다."""
    with _ENGINE_LOCK:
        _configure_engine()
        command = pytesseract.pytesseract.tesseract_cmd
        key = (command, os.environ.get("TESSDATA_PREFIX", ""))
        cached = _LANGUAGE_CACHE.get(key)
        if cached and monotonic() - cached[0] < CACHE_SECONDS:
            return list(cached[1])
        try:
            result = subprocess.run([command, "--list-langs"], capture_output=True,
                                    text=True, errors="replace", timeout=8, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError("Tesseract 언어 모델 목록을 읽지 못했습니다. 설치와 경로를 확인하세요.") from error
        if result.returncode != 0:
            raise RuntimeError("Tesseract 언어 모델 목록을 읽지 못했습니다. 설치와 경로를 확인하세요.")
        languages = sorted({line.strip() for line in result.stdout.splitlines()
                            if re.fullmatch(r"[A-Za-z0-9_/]+", line.strip())})
        if not languages:
            raise RuntimeError("사용 가능한 OCR 언어 모델을 찾지 못했습니다.")
        _LANGUAGE_CACHE.clear()
        _LANGUAGE_CACHE[key] = (monotonic(), tuple(languages))
        return languages


def group_ocr_lines(data):
    """Tesseract block/par/line 번호와 단어 좌표로 행을 구성한다."""
    groups = defaultdict(list)
    count = len(data.get("text", []))

    for i in range(count):
        word = str(data["text"][i] or "").strip()
        if not word:
            continue
        try:
            left = int(data["left"][i])
            top = int(data["top"][i])
            width = int(data["width"][i])
            height = int(data["height"][i])
            confidence = float(data["conf"][i])
            key = (int(data["block_num"][i]), int(data["par_num"][i]), int(data["line_num"][i]))
        except (ValueError, TypeError, IndexError, KeyError):
            continue
        if width <= 0 or height <= 0 or confidence < 0:
            continue
        groups[key].append((left, top, width, height, confidence, word))

    lines = []
    for words in groups.values():
        words.sort(key=lambda word: word[0])
        left = min(word[0] for word in words)
        top = min(word[1] for word in words)
        right = max(word[0] + word[2] for word in words)
        bottom = max(word[1] + word[3] for word in words)
        confidence = round(sum(word[4] for word in words) / len(words), 1)
        lines.append(OCRLine(" ".join(word[5] for word in words), left, top, right - left, bottom - top, confidence))

    lines.sort(key=lambda line: (line.top, line.left))
    return lines


def recognize_text(image: Image.Image, languages="kor+eng", psm=11, timeout=45):
    """Pillow 이미지에서 OCR 결과를 반환한다. 외부 AI API는 사용하지 않는다."""
    if not isinstance(image, Image.Image):
        raise ValueError("Pillow 이미지가 필요합니다.")

    selected = languages.split("+")
    if not selected or any(language not in SUPPORTED_LANGUAGES for language in selected):
        raise ValueError("지원하지 않는 OCR 언어입니다.")
    if psm not in (3, 6, 11):
        raise ValueError("지원하지 않는 페이지 분석 모드입니다.")

    deadline = monotonic() + timeout
    try:
        installed = set(available_languages())
        config = ""
        missing = set(selected) - installed
        if missing:
            raise RuntimeError(
                f"OCR 언어 모델이 부족합니다: {', '.join(sorted(missing))}. "
                "Windows에서는 setup.cmd, Streamlit Cloud에서는 packages.txt를 확인하세요."
            )
        remaining = deadline - monotonic()
        if remaining < 0.5:
            raise RuntimeError("OCR 처리 제한 시간에 도달했습니다.")
        data = pytesseract.image_to_data(
            image.convert("RGB"),
            lang=languages,
            config=f"--oem 1 --psm {psm} {config}".strip(),
            output_type=Output.DICT,
            timeout=remaining,
        )
    except (TesseractNotFoundError, TesseractError, RuntimeError, OSError) as error:
        if isinstance(error, RuntimeError):
            raise
        raise RuntimeError("Tesseract OCR 실행에 실패했습니다. 설치 상태와 이미지를 확인하세요.") from error

    lines = group_ocr_lines(data)
    return OCRResult("\n".join(line.text for line in lines), lines, languages)
