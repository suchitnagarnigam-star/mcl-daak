from fastapi import APIRouter, UploadFile, File, HTTPException, status
import logging
from uuid import uuid4

from app.services.opencv_services import process_image
from app.services.mistral_ocr_services import mistral_process_ocr
from app.services.claude_service import process_document
from app.services.sheets_service import push_to_sheets
from app.utils.file_utils import save_uploaded_file, delete_file, MAX_FILES_PER_REQUEST
from app.services.supabase_service import insert_data, update_status
from app.schemas.submission import DocumentSubmission, ImageItem

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
)


@router.post("/")
async def upload_images(
    files: list[UploadFile] = File(...)
):
    # 1. VALIDATE REQUEST FILE COUNT
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No images were provided.",
        )

    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Exceeded maximum limit of {MAX_FILES_PER_REQUEST} files per request.",
        )

    # 2. CREATE ISOLATED DOCUMENT SUBMISSION CONTAINER
    submission = DocumentSubmission(submission_id=str(uuid4()))

    logger.info(
        "Starting document submission %s with %d image(s)",
        submission.submission_id,
        len(files),
    )

    # 3. PROCESS EACH IMAGE IN ORDER
    for index, file in enumerate(files, start=1):
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Image #{index} does not have a valid filename.",
            )

        logger.info(
            "[%s] Processing page %d/%d: %s",
            submission.submission_id,
            index,
            len(files),
            file.filename,
        )

        saved_path = None
        processed_path = None

        try:
            # SAVE ORIGINAL FILE WITH SERVER-GENERATED SAFE FILENAME
            saved_path = save_uploaded_file(file, submission.submission_id, index)

            logger.info(
                "[%s] Page %d saved securely: %s",
                submission.submission_id,
                index,
                saved_path,
            )

            # OPENCV PREPROCESSING
            processed_path = process_image(saved_path)

            logger.info(
                "[%s] Page %d OpenCV processing complete",
                submission.submission_id,
                index,
            )

            # MISTRAL OCR
            ocr_result = mistral_process_ocr(processed_path)
            ocr_text = ocr_result.get("text", "")

            if not ocr_text:
                logger.warning(
                    "[%s] Page %d returned empty OCR text",
                    submission.submission_id,
                    index,
                )

            logger.info(
                "[%s] Page %d OCR complete",
                submission.submission_id,
                index,
            )

            # CLEANUP TEMPORARY FILES FOR THIS PAGE
            delete_file(saved_path)
            delete_file(processed_path)

            # STORE ISOLATED IMAGE ITEM IN ORDER
            item = ImageItem(
                img_index=index,
                original_filename=file.filename,
                saved_path=saved_path,
                processed_path=processed_path,
                ocr_md=ocr_text,
            )
            submission.image_items.append(item)

        except HTTPException:
            if saved_path:
                delete_file(saved_path)
            if processed_path:
                delete_file(processed_path)
            raise

        except Exception as exc:
            if saved_path:
                delete_file(saved_path)
            if processed_path:
                delete_file(processed_path)

            logger.exception(
                "[%s] Failed while processing page %d: %s",
                submission.submission_id,
                index,
                exc,
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process image #{index} ({file.filename}).",
            ) from exc

    # 4. COMBINE OCR TEXT IN STRICT INDEX ORDER
    page_sections = []
    for item in sorted(submission.image_items, key=lambda x: x.img_index):
        page_sections.append(
            "\n".join(
                [
                    f"===== BEGIN PAGE {item.img_index} =====",
                    "",
                    item.ocr_md,
                    "",
                    f"===== END PAGE {item.img_index} =====",
                ]
            )
        )

    submission.combined_ocr = "\n\n".join(page_sections)
    if not submission.combined_ocr.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "All pages returned empty OCR text.", "status": "failed"},
        )

    logger.info(
        "[%s] Combined OCR created from %d page(s)",
        submission.submission_id,
        len(submission.image_items),
    )

    # 5. STRUCTURED EXTRACTION VIA CLAUDE
    try:
        submission.llm_result = process_document(submission.combined_ocr)

        if not submission.llm_result:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Failed to extract subject or summary.", "status": "failed"},
            )

        if not submission.llm_result.get("subject") or not submission.llm_result.get("summary"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Failed to extract required fields.", "status": "failed"},
            )

        logger.info(
            "[%s] LLM extraction complete",
            submission.submission_id,
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception(
            "[%s] LLM processing failed: %s",
            submission.submission_id,
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to extract structured document data.", "status": "failed"},
        ) from exc

    # NORMALIZE NULL FIELDS
    fields = ["date", "department", "sender_name", "sender_contact", "receiver", "reference_number"]
    for field in fields:
        if not submission.llm_result.get(field):
            submission.llm_result[field] = "N/A"

    # 6. SUPABASE INSERTION
    try:
        submission.serial_number = insert_data(submission.llm_result)
    except Exception as exc:
        logger.exception(
            "[%s] Failed to insert data into database: %s",
            submission.submission_id,
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to insert data into database.", "status": "failed"},
        ) from exc

    # 7. GOOGLE SHEETS SYNC (INDEPENDENT)
    try:
        if len(files) == 1:
            sheets_filename = submission.image_items[0].original_filename
        else:
            sheets_filename = f"submission_{submission.submission_id}"

        await push_to_sheets(
            submission.llm_result,
            sheets_filename,
            submission.serial_number
        )

        logger.info(
            "[%s] Google Sheets sync complete",
            submission.submission_id,
        )

    except Exception as exc:
        logger.exception(
            "[%s] Google Sheets sync failed: %s",
            submission.submission_id,
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document processed but Google Sheets sync failed.",
        ) from exc

    # 8. UPDATE STATUS IN DATABASE
    try:
        update_status(submission.serial_number, "complete")
        submission.status = "complete"

        logger.info(
            "[%s] Status updated to complete",
            submission.submission_id,
        )

    except Exception as exc:
        logger.exception(
            "[%s] Failed to update status: %s",
            submission.submission_id,
            exc,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Document processed but status update failed.", "status": "failed"},
        ) from exc

    # 9. FINAL RESPONSE
    return {
        "serial_number": submission.serial_number,
        "message": "Document processed successfully",
        "submission_id": submission.submission_id,
        "status": submission.status,
        "file_count": len(submission.image_items),
        "files": [
            item.original_filename
            for item in submission.image_items
        ],
        "images": [
            {
                "img_index": item.img_index,
                "filename": item.original_filename,
                "ocr_md": item.ocr_md,
            }
            for item in submission.image_items
        ],
        "extracted_data": submission.llm_result,
    }