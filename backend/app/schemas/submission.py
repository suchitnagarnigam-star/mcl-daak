from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ImageItem:
    img_index: int
    original_filename: str
    saved_path: str
    processed_path: Optional[str] = None
    ocr_md: str = ""


@dataclass
class DocumentSubmission:
    submission_id: str
    image_items: List[ImageItem] = field(default_factory=list)
    combined_ocr: str = ""
    llm_result: Optional[Dict[str, Any]] = None
    serial_number: Optional[str] = None
    status: str = "processing"
