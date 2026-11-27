from __future__ import annotations

import io
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz
from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMP_DIR = Path(tempfile.gettempdir()) / "taxmann-pdf-watermark"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf"}
LOGO_PATH = STATIC_DIR / "taxmann_logo.png"
WATERMARK_OPACITY = 0.12
WATERMARK_SIZE = 100
WATERMARK_ROTATION = 45


def cleanup_old_files() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    for path in TEMP_DIR.glob("*.pdf"):
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            continue


def is_pdf_upload(file_storage) -> bool:
    filename = secure_filename(file_storage.filename or "")
    if not filename or Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        return False
    header = file_storage.stream.read(5)
    file_storage.stream.seek(0)
    return header == b"%PDF-"


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def create_watermark_png(opacity: float, target_width: int, rotation: int) -> bytes:
    with Image.open(LOGO_PATH).convert("RGBA") as source:
        aspect_ratio = source.height / source.width
        target_height = max(1, round(target_width * aspect_ratio))
        logo = source.resize((target_width, target_height), Image.Resampling.LANCZOS)
        alpha = logo.getchannel("A").point(lambda channel: round(channel * opacity))
        logo.putalpha(alpha)
        logo = logo.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)
        output = io.BytesIO()
        logo.save(output, format="PNG", optimize=True)
        return output.getvalue()


def process_pdf(input_bytes: bytes, opacity: float, logo_size: float, rotation: int) -> bytes:
    if not LOGO_PATH.exists():
        raise FileNotFoundError("The Taxmann logo asset is missing from the static folder.")

    source_document = fitz.open(stream=input_bytes, filetype="pdf")
    output_document = fitz.open()
    try:
        output_document.insert_pdf(source_document)
        watermark_cache: dict[int, tuple[bytes, float, float]] = {}
        for output_page in output_document:
            short_edge = min(output_page.rect.width, output_page.rect.height)
            logo_width = max(24, round(short_edge * (logo_size / 100)))
            if logo_width not in watermark_cache:
                logo_bytes = create_watermark_png(opacity, logo_width * 4, rotation)
                with Image.open(io.BytesIO(logo_bytes)) as watermark:
                    watermark_width, watermark_height = watermark.size
                watermark_cache[logo_width] = (
                    logo_bytes,
                    logo_width * watermark_width / max(1, logo_width * 4),
                    logo_width * watermark_height / max(1, logo_width * 4),
                )
            logo_bytes, width, height = watermark_cache[logo_width]
            center_x = output_page.rect.width / 2
            center_y = output_page.rect.height / 2
            watermark_rect = fitz.Rect(
                center_x - width / 2,
                center_y - height / 2,
                center_x + width / 2,
                center_y + height / 2,
            )
            output_page.insert_image(
                watermark_rect,
                stream=logo_bytes,
                keep_proportion=True,
                overlay=True,
            )

        return output_document.tobytes(garbage=3, deflate=True)
    finally:
        source_document.close()
        output_document.close()


@app.errorhandler(413)
def request_entity_too_large(_error):
    limit = "4 MB" if os.environ.get("VERCEL") else "50 MB"
    return jsonify({"error": f"The PDF is too large. Please upload a file smaller than {limit}."}), 413


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/process")
def process():
    cleanup_old_files()
    upload = request.files.get("pdf")
    if upload is None or not upload.filename:
        return jsonify({"error": "Please choose a PDF file to upload."}), 400
    if not is_pdf_upload(upload):
        return jsonify({"error": "Only valid PDF files are accepted."}), 400

    try:
        adjust_watermark = request.form.get("adjust") == "true"
        if adjust_watermark:
            opacity = clamp(float(request.form.get("opacity", str(WATERMARK_OPACITY))), 0.02, 0.6)
            logo_size = clamp(float(request.form.get("logo_size", str(WATERMARK_SIZE))), 10, 100)
            rotation = int(clamp(float(request.form.get("rotation", str(WATERMARK_ROTATION))), -45, 45))
        else:
            opacity = WATERMARK_OPACITY
            logo_size = WATERMARK_SIZE
            rotation = WATERMARK_ROTATION
        input_bytes = upload.read()
        if not input_bytes:
            return jsonify({"error": "The uploaded PDF is empty."}), 400
        output_bytes = process_pdf(input_bytes, opacity, logo_size, rotation)
    except (ValueError, fitz.FileDataError, RuntimeError) as error:
        return jsonify({"error": f"Unable to process this PDF: {error}"}), 422
    except Exception:
        app.logger.exception("Unexpected PDF processing failure")
        return jsonify({"error": "Something went wrong while processing the PDF. Please try another file."}), 500

    original_name = secure_filename(upload.filename or "document.pdf")
    stem = Path(original_name).stem or "document"
    output_name = f"{stem}_watermarked.pdf"
    processed_document = fitz.open(stream=output_bytes, filetype="pdf")
    page_count = len(processed_document)
    processed_document.close()
    if os.environ.get("VERCEL"):
        response = send_file(
            io.BytesIO(output_bytes),
            mimetype="application/pdf",
            download_name=output_name,
            max_age=0,
        )
        response.headers["X-PDF-Pages"] = str(page_count)
        return response

    file_id = uuid.uuid4().hex
    output_path = TEMP_DIR / f"{file_id}.pdf"
    output_path.write_bytes(output_bytes)
    return jsonify(
        {
            "id": file_id,
            "filename": output_name,
            "pages": page_count,
            "preview_url": f"/api/files/{file_id}/preview",
            "download_url": f"/api/files/{file_id}/download?filename={output_name}",
        }
    )


def get_output_path(file_id: str) -> Path | None:
    if not re.fullmatch(r"[a-f0-9]{32}", file_id):
        return None
    path = TEMP_DIR / f"{file_id}.pdf"
    return path if path.is_file() else None


@app.get("/api/files/<file_id>/preview")
def preview(file_id: str):
    path = get_output_path(file_id)
    if path is None:
        return jsonify({"error": "This processed file is no longer available."}), 404
    return send_file(path, mimetype="application/pdf", download_name="preview.pdf", max_age=0)


@app.get("/api/files/<file_id>/download")
def download(file_id: str):
    path = get_output_path(file_id)
    if path is None:
        return jsonify({"error": "This processed file is no longer available."}), 404
    filename = secure_filename(request.args.get("filename", "watermarked.pdf"))
    return send_file(path, as_attachment=True, download_name=filename, mimetype="application/pdf", max_age=0)


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG", "").lower() == "true",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
    )
