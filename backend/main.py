from __future__ import annotations

import io
import re
import zipfile
from typing import List, Optional, Tuple

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from PIL import Image, ImageOps


APP_NAME = "Image Resizer & Compressor"
MAX_DIMENSION = 20000  # safety guard


def _clean_filename(name: str) -> str:
    name = (name or "").strip().replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "image"


def _split_name_ext(name: str) -> Tuple[str, str]:
    m = re.match(r"^(.*?)(\.[A-Za-z0-9]+)?$", name)
    if not m:
        return name, ""
    return m.group(1), (m.group(2) or "")


def _parse_int(v: Optional[str]) -> Optional[int]:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _validate_dims(w: Optional[int], h: Optional[int]) -> None:
    for n in (w, h):
        if n is None:
            continue
        if n <= 0:
            raise HTTPException(status_code=400, detail="Width/Height must be positive.")
        if n > MAX_DIMENSION:
            raise HTTPException(status_code=400, detail=f"Max dimension is {MAX_DIMENSION}px.")


def _normalize_format(fmt: str) -> str:
    fmt = (fmt or "").strip().lower()
    if fmt in ("jpg", "jpeg"):
        return "jpeg"
    if fmt == "png":
        return "png"
    if fmt == "webp":
        return "webp"
    return ""


def _format_ext(fmt: str) -> str:
    return ".jpg" if fmt == "jpeg" else f".{fmt}"


def _fit_size_keep_ratio(ow: int, oh: int, tw: Optional[int], th: Optional[int]) -> Tuple[int, int]:
    # Fit inside (tw, th) while keeping ratio
    if tw is None and th is None:
        return ow, oh
    if tw is not None and th is None:
        scale = tw / ow
        return max(1, int(round(ow * scale))), max(1, int(round(oh * scale)))
    if th is not None and tw is None:
        scale = th / oh
        return max(1, int(round(ow * scale))), max(1, int(round(oh * scale)))
    assert tw is not None and th is not None
    scale = min(tw / ow, th / oh)
    return max(1, int(round(ow * scale))), max(1, int(round(oh * scale)))


def _resize_image(img: Image.Image, tw: Optional[int], th: Optional[int], keep_ratio: bool) -> Image.Image:
    ow, oh = img.size
    if tw is None and th is None:
        return img

    if keep_ratio:
        nw, nh = _fit_size_keep_ratio(ow, oh, tw, th)
    else:
        nw, nh = (tw or ow), (th or oh)

    if (nw, nh) == (ow, oh):
        return img
    return img.resize((nw, nh), resample=Image.Resampling.LANCZOS)


def _prepare_for_format(img: Image.Image, out_fmt: str) -> Image.Image:
    # flatten transparency for JPEG
    if out_fmt == "jpeg":
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            rgba = img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[-1])
            return bg
        return img.convert("RGB") if img.mode != "RGB" else img

    if out_fmt in ("png", "webp"):
        if img.mode == "P":
            return img.convert("RGBA")
        return img

    return img


def _save_image(img: Image.Image, out_fmt: str, quality: int) -> bytes:
    buf = io.BytesIO()

    q = int(max(10, min(100, quality)))

    if out_fmt == "jpeg":
        img.save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
    elif out_fmt == "webp":
        img.save(buf, format="WEBP", quality=q, method=6)
    elif out_fmt == "png":
        # PNG is lossless; map quality (10..100) to compress_level (9..0)
        compress_level = int(round((100 - q) * 9 / 90))
        compress_level = max(0, min(9, compress_level))
        img.save(buf, format="PNG", optimize=True, compress_level=compress_level)
    else:
        raise HTTPException(status_code=400, detail="Unsupported output format.")

    return buf.getvalue()


def _process_bytes(
    data: bytes,
    *,
    width: Optional[int],
    height: Optional[int],
    keep_ratio: bool,
    quality: int,
    out_fmt: str,
) -> tuple[bytes, tuple[int, int]]:
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read image: {e}")

    _validate_dims(width, height)

    img = _resize_image(img, width, height, keep_ratio=keep_ratio)
    img = _prepare_for_format(img, out_fmt)
    out = _save_image(img, out_fmt, quality=quality)
    return out, img.size


app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "name": APP_NAME}


@app.post("/api/process")
async def process_single(
    file: UploadFile = File(...),
    width: Optional[str] = Form(None),
    height: Optional[str] = Form(None),
    keep_ratio: bool = Form(True),
    quality: int = Form(85),
    out_format: str = Form("jpeg"),
):
    out_fmt = _normalize_format(out_format)
    if not out_fmt:
        raise HTTPException(status_code=400, detail="Output format must be JPG, PNG, or WEBP.")

    w = _parse_int(width)
    h = _parse_int(height)

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file.")

    out_bytes, (nw, nh) = _process_bytes(
        data, width=w, height=h, keep_ratio=keep_ratio, quality=quality, out_fmt=out_fmt
    )

    safe = _clean_filename(file.filename or "image")
    base_name, _ext = _split_name_ext(safe)
    out_name = f"{base_name}{_format_ext(out_fmt)}"

    headers = {
        "Content-Disposition": f'attachment; filename="{out_name}"',
        "X-Original-Bytes": str(len(data)),
        "X-Processed-Bytes": str(len(out_bytes)),
        "X-Output-Width": str(nw),
        "X-Output-Height": str(nh),
    }

    return StreamingResponse(
        io.BytesIO(out_bytes),
        media_type=f"image/{'jpeg' if out_fmt == 'jpeg' else out_fmt}",
        headers=headers,
        status_code=200,
    )


@app.post("/api/process-zip")
async def process_zip(
    files: List[UploadFile] = File(...),
    width: Optional[str] = Form(None),
    height: Optional[str] = Form(None),
    preset: Optional[str] = Form(None),  # supports "1024x1024", "50%", "25%"
    keep_ratio: bool = Form(True),
    quality: int = Form(85),
    out_format: str = Form("jpeg"),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    out_fmt = _normalize_format(out_format)
    if not out_fmt:
        raise HTTPException(status_code=400, detail="Output format must be JPG, PNG, or WEBP.")

    w = _parse_int(width)
    h = _parse_int(height)

    preset = (preset or "").strip()
    pct = None
    fixed = None
    if preset.endswith("%"):
        try:
            pct = int(preset[:-1])
            if pct <= 0:
                pct = None
        except ValueError:
            pct = None
    elif "x" in preset:
        try:
            a, b = preset.lower().split("x", 1)
            fixed = (int(a), int(b))
        except Exception:
            fixed = None

    zip_buf = io.BytesIO()
    processed_count = 0

    with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            data = await f.read()
            if not data:
                continue

            # Determine per-file size for % presets
            if pct is not None:
                try:
                    im = Image.open(io.BytesIO(data))
                    im = ImageOps.exif_transpose(im)
                    ow, oh = im.size
                except Exception:
                    continue
                tw = max(1, int(round(ow * (pct / 100.0))))
                th = max(1, int(round(oh * (pct / 100.0))))
                use_w, use_h = tw, th
            elif fixed is not None:
                use_w, use_h = fixed
            else:
                use_w, use_h = w, h

            out_bytes, _size = _process_bytes(
                data, width=use_w, height=use_h, keep_ratio=keep_ratio, quality=quality, out_fmt=out_fmt
            )

            safe = _clean_filename(f.filename or f"image_{processed_count+1}")
            base_name, _ext = _split_name_ext(safe)
            out_name = f"{base_name}{_format_ext(out_fmt)}"

            # avoid duplicate names
            if out_name in zf.namelist():
                out_name = f"{base_name}_{processed_count+1}{_format_ext(out_fmt)}"

            zf.writestr(out_name, out_bytes)
            processed_count += 1

    if processed_count == 0:
        raise HTTPException(status_code=400, detail="All uploaded files were empty or invalid.")

    zip_buf.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="processed_images.zip"'}
    return StreamingResponse(zip_buf, media_type="application/zip", headers=headers)


# IMPORTANT: mount frontend AFTER API routes (otherwise /api/* can be shadowed)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
