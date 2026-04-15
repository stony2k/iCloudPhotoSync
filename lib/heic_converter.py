"""
HEIC Converter — converts HEIC/HEIF images to JPG.

Uses ImageMagick's `convert` command which is pre-installed on Synology DSM
and supports HEIC via the system libheif library. Falls back to Pillow +
pillow-heif if available. No C-extension compilation needed for the package.
"""
import logging
import os
import shutil
import subprocess

LOGGER = logging.getLogger("heic_converter")

# Detect available conversion backend
_BACKEND = None  # "imagemagick", "pillow", or None

# Check ImageMagick first (preferred — no Python dependencies)
_CONVERT_BIN = shutil.which("convert")
if _CONVERT_BIN:
    _BACKEND = "imagemagick"

# Fallback: Pillow + pillow-heif
if not _BACKEND:
    try:
        from PIL import Image
        import pillow_heif
        pillow_heif.register_heif_opener()
        _BACKEND = "pillow"
    except ImportError:
        pass

LOGGER.debug("HEIC converter backend: %s", _BACKEND or "none")


def is_heic(filename):
    """Check if a file is HEIC format."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in (".heic", ".heif")


def can_convert():
    """Check if HEIC conversion is available."""
    return _BACKEND is not None


def convert_to_jpg(heic_path, jpg_path=None, quality=92):
    """
    Convert a HEIC file to JPG.

    Args:
        heic_path: Path to the HEIC source file
        jpg_path: Output path (default: same name with .jpg extension)
        quality: JPEG quality 1-100

    Returns:
        Path to the converted JPG, or None if conversion failed/unavailable.
    """
    if not _BACKEND:
        LOGGER.debug("HEIC conversion not available")
        return None

    if jpg_path is None:
        base = os.path.splitext(heic_path)[0]
        jpg_path = base + ".jpg"

    if _BACKEND == "imagemagick":
        return _convert_imagemagick(heic_path, jpg_path, quality)
    elif _BACKEND == "pillow":
        return _convert_pillow(heic_path, jpg_path, quality)
    return None


def _convert_imagemagick(heic_path, jpg_path, quality):
    """Convert using ImageMagick's convert command."""
    try:
        result = subprocess.run(
            [_CONVERT_BIN, heic_path, "-quality", str(quality), jpg_path],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and os.path.isfile(jpg_path):
            # Match permissions of original file
            try:
                os.chmod(jpg_path, 0o644)
            except OSError:
                pass
            LOGGER.info("Converted %s -> %s (ImageMagick)", heic_path, jpg_path)
            return jpg_path
        else:
            LOGGER.error("ImageMagick convert failed for %s: %s", heic_path, result.stderr)
            return None
    except subprocess.TimeoutExpired:
        LOGGER.error("ImageMagick convert timed out for %s", heic_path)
        return None
    except Exception as e:
        LOGGER.error("ImageMagick convert error for %s: %s", heic_path, e)
        return None


def _convert_pillow(heic_path, jpg_path, quality):
    """Convert using Pillow + pillow-heif."""
    try:
        from PIL import Image
        img = Image.open(heic_path)
        exif = img.info.get("exif", b"")
        if exif:
            img.save(jpg_path, "JPEG", quality=quality, exif=exif)
        else:
            img.save(jpg_path, "JPEG", quality=quality)
        try:
            os.chmod(jpg_path, 0o644)
        except OSError:
            pass
        LOGGER.info("Converted %s -> %s (Pillow)", heic_path, jpg_path)
        return jpg_path
    except Exception as e:
        LOGGER.error("Pillow conversion failed for %s: %s", heic_path, e)
        return None
