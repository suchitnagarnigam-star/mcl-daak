from pathlib import Path
import shutil
import json
from datetime import datetime
from fastapi import UploadFile

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("output")
# this will create the uploads and output directories if they don't exist
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

def save_uploaded_file(file: UploadFile) -> str:
    """
    Save uploaded image to the uploads folder 
    Returns the saved file path
    """
    file_path = UPLOAD_DIR / file.filename
    
    # save the file to the uploads directory
    with open(file_path, "wb") as buffer:
        # this will save the file in chunks to avoid memory issues with large files
        shutil.copyfileobj(file.file, buffer)
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
        Path(file_path).unlink(missing_ok=True)
    except Exception as e:
        print(f"Failed to delete file {file_path}: {e}")