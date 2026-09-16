from fastapi import APIRouter, UploadFile, File, HTTPException
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.services.opencv_services import process_image
from app.services.mistral_ocr_services import mistral_process_ocr
from app.services.claude_service import process_document
from app.services.sheets_service import push_to_sheets
from app.utils.file_utils import save_uploaded_file, delete_file
from app.services.supabase_service import insert_data, update_status

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/upload",
    tags=["Upload"],
)


@router.post("/")
async def upload_images(
    files: list[UploadFile] = File(...)
):

    # VALIDATE UPLOAD
    if not files:
        raise HTTPException(
            status_code=400,
            detail="No images were provided.",
        )


    # CREATE SUBMISSION ID
    submission_id = str(uuid4())

    logger.info(
        "Starting document submission %s with %d image(s)",
        submission_id,
        len(files),
    )

    # =========================================================
    # IMAGE-LEVEL RESULTS
    #
    # Each image gets its own:
    #   - index
    #   - filename
    #   - original path
    #   - processed path
    #   - OCR markdown/text
    #
    # Claude is NOT called here.
    # =========================================================

    image_items = []

   
    # PROCESS EACH IMAGE
    for index, file in enumerate(files, start=1):

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail=f"Image {index} does not have a filename.",
            )

        logger.info(
            "[%s] Processing page %d/%d: %s",
            submission_id,
            index,
            len(files),
            file.filename,
        )

        saved_path = None
        processed_path = None

        try:
            # SAVE ORIGINAL IMAGE
            saved_path = save_uploaded_file(file)

            logger.info(
                "[%s] Page %d saved: %s",
                submission_id,
                index,
                saved_path,
            )

            # OPENCV
            processed_path = process_image(saved_path)

            logger.info(
                "[%s] Page %d OpenCV processing complete",
                submission_id,
                index,
            )

            # MISTRAL OCR
            ocr_result = mistral_process_ocr(
                processed_path
            )

            ocr_text = ocr_result.get("text", "")

            if not ocr_text:
                logger.warning(
                    "[%s] Page %d returned empty OCR text",
                    submission_id,
                    index,
                )

            logger.info(
                "[%s] Page %d OCR complete",
                submission_id,
                index,
            )

            delete_file(saved_path)
            delete_file(processed_path)
            
            # STORE IMAGE ITEM
            image_items.append(
                {
                    "img_index": index,
                    "filename": file.filename,
                    "ocr_md": ocr_text,
                }
            )
        except HTTPException:
            raise

        except Exception as exc:
            if saved_path:
                delete_file(saved_path)
            if processed_path:
                delete_file(processed_path)

            logger.exception(
                "[%s] Failed while processing page %d: %s",
                submission_id,
                index,
                exc,
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    f"Failed to process image "
                    f"{index} ({file.filename})."
                ),
            ) from exc

    page_sections = []

    for image in image_items:

        page_sections.append(
            "\n".join(
                [
                    f"===== BEGIN PAGE {image['img_index']} =====",
                    "",
                    image["ocr_md"],
                    "",
                    f"===== END PAGE {image['img_index']} =====",
                ]
            )
        )

    combined_ocr = "\n\n".join(page_sections)
    if not combined_ocr.strip():
        raise HTTPException(
            status_code=400,
            detail={"message": "All pages returned empty OCR text.", "status": "failed"}
        )
        
    logger.info(
        "[%s] Combined OCR created from %d page(s)",
        submission_id,
        len(image_items),
    )

    try:

        llm_result = process_document(
            combined_ocr
        )
        if not llm_result:
            raise HTTPException(
                status_code=422,
                detail={"message": "Failed to extract subject or summary.", "status": "failed"}
            )

        if not llm_result.get("subject") or not llm_result.get("summary"):
            raise HTTPException(
                status_code=422,
                detail={"message": "Failed to extract data.", "status": "failed"}
            )

        logger.info(
            "[%s] LLM extraction complete",
            submission_id,
        )

    except HTTPException: 
        raise 

    except Exception as exc:

        logger.exception(
            "[%s] LLM processing failed: %s",
            submission_id,
            exc,
        )

        raise HTTPException(
            status_code=500,
            detail={"message": "Failed to extract structured document data.", "status": "failed"},
        ) from exc


    # normlaize null fields to N/A "sender_contact", "receiver",
    fields = ["date", "department", "sender_name","sender_contact", "receiver", "reference_number"]

    for field in fields:
        if not llm_result.get(field):
            llm_result[field] = "N/A"

    # =========================================================
    # supabase ENTRY
    #
    # We push the final document result only once.
    # =========================================================
    try:
        serial_number = insert_data(llm_result)
    except Exception as exc:
        logger.exception(
            "[%s] Failed to insert data into database: %s",
            submission_id,
            exc,
        )

        raise HTTPException(
            status_code=500,
            detail={"message": "Failed to insert data into database.", "status": "failed"},
        ) from exc


    # sheets

    try:

        # For a single image, keep the original filename.
        #
        # For multiple images, use a submission-level name
        # rather than treating every page as a separate document.

        if len(files) == 1:
            sheets_filename = files[0].filename
        else:
            sheets_filename = (
                f"submission_{submission_id}"
            )

        await push_to_sheets(
            llm_result,
            sheets_filename,
            serial_number
        )

        logger.info(
            "[%s] Google Sheets sync complete",
            submission_id,
        )

    except Exception as exc:

        logger.exception(
            "[%s] Google Sheets sync failed: %s",
            submission_id,
            exc,
        )

        raise HTTPException(
            status_code=500,
            detail="Document processed but Google Sheets sync failed.",
        ) from exc

    # =========================================================
    # UPDATE STATUS IN DATABASE
    # =========================================================
    try:
        update_status(serial_number, "complete")

        logger.info(
            "[%s] Status updated to complete",
            submission_id,
        )

    except Exception as exc:
        logger.exception(
            "[%s] Failed to update status: %s",
            submission_id,
            exc,
        )

        raise HTTPException(
            status_code=500,
            detail={"message": "Document processed but status update failed.", "status": "failed"},
        ) from exc

    # =========================================================
    # FINAL RESPONSE
    # =========================================================

    return {
        "serial_number": serial_number,
        "message": "Document processed successfully",
        "submission_id": submission_id,
        "status": "complete",
        "file_count": len(image_items),
        "files": [
            image["filename"]
            for image in image_items
        ],
        "images": image_items,
        "extracted_data": llm_result,
    }