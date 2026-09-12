from pathlib import Path
import shutil
import json
from datetime import datetime
from fastapi import HTTPException, UploadFile, status

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("output")

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB limit per file
MAX_FILES_PER_REQUEST = 10


def validate_file(file: UploadFile, img_index: int) -> str:
    """
    Validates uploaded file filename, extension, MIME type, and size.
    Returns the lowercased extension (e.g. '.jpg').
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File #{img_index} does not have a valid filename."
        )

    # Extract base filename to prevent path traversal
    safe_filename = Path(file.filename).name
    if not safe_filename or safe_filename.startswith("."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or hidden filename for file #{img_index}."
        )

    # Extension validation
    ext = Path(safe_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}' for file #{img_index}. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Content-type / MIME type validation
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MIME type '{file.content_type}' for file #{img_index}."
        )

    return ext


def save_uploaded_file(file: UploadFile, submission_id: str, img_index: int) -> str:
    """
    Saves uploaded file securely to the uploads folder using a server-generated filename:
    <submission_id>_<img_index><ext>
    
    Prevents path traversal, filename collision, and enforces file size limits.
    Returns the saved file path.
    """
    ext = validate_file(file, img_index)

    # Server-generated safe filename
    server_filename = f"{submission_id}_{img_index}{ext}"
    file_path = UPLOAD_DIR / server_filename

    # Read and save file with file size check
    file_size = 0
    with open(file_path, "wb") as buffer:
        for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE_BYTES:
                # Remove partially written file if limit exceeded
                file_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File #{img_index} exceeds maximum allowed size of 15MB."
                )
            buffer.write(chunk)

    return str(file_path)


def save_result_json(image_filename: str, data: dict) -> str:
    """
    Save processing result metadata to the output folder and link it to the source image.
    """
    sanitized_name = Path(image_filename).stem
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    output_filename = f"{sanitized_name}_{timestamp}.json"
    output_path = OUTPUT_DIR / output_filename

    with open(output_path, "w", encoding="utf-8") as buffer:
        json.dump(data, buffer, ensure_ascii=False, indent=2)

    return str(output_path)


def delete_file(file_path: str) -> None:
    """
    Delete a file from disk after it is no longer needed.
    """
    try:
        if file_path:
            Path(file_path).unlink(missing_ok=True)
    except Exception as e:
        print(f"Failed to delete file {file_path}: {e}")