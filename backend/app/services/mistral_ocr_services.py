from asyncio.log import logger
import logging
from pathlib import Path
import base64
import os 

from dotenv import load_dotenv
from mistralai.client import Mistral

# load_dotenv() will automatically look for .env in the parent directories
load_dotenv()

api_key = os.getenv("MISTRAL_API_KEY", "")
client = Mistral(api_key=api_key) if api_key else None

def mistral_process_ocr(file_path: Path)-> dict:    

    source = Path(file_path)
    
    # -----------------------------------
    # 1. validate input file
    # -----------------------------------
    if not source.exists():
        raise FileNotFoundError(
            f"File not found: {source}"
        )

    if not source.is_file():
        raise ValueError(
            f"Provide OCR Path is not a file: {source}"
        )

    MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    mime_type = MIME_TYPES.get(source.suffix.lower(), "image/jpeg")
    
    def encode_file(file_path: Path) -> str:
        with file_path.open("rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    base64_file = encode_file(source)
    

    ocr_response = client.ocr.process(
        document={
        "type": "image_url",
        "image_url": f"data:{mime_type};base64,{base64_file}"
        },
        model="mistral-ocr-latest",
    #     document_annotation_format=ResponseFormat(
	# 	type="json_schema",
	# 	json_schema=JSONSchema(
	# 		name="response_schema",
	# 		schema_definition={
	# 			"type": "object",
	# 			"required": [
	# 				"document_metadata",
	# 				"letter_details"
	# 			],
	# 			"properties": {
	# 				"letter_details": {
	# 					"type": "object",
	# 					"required": [
	# 						"recipient",
	# 						"subject",
	# 						"date",
	# 						"body",
	# 						"signatories"
	# 					],
	# 					"properties": {
	# 						"date": {
	# 							"type": "string"
	# 						},
	# 						"subject": {
	# 							"type": "string"
	# 						},
	# 						"summary": {
	# 							"type": "string"
	# 						},
    #                         "department": {
    #                             "type": "string"
    #                         },
    #                         "sender_name": {
    #                             "type": "string"
    #                         },
    #                         "signatories": {
    #                             "type": "string"
    #                         },
    #                         "body_paragraphs": {
    #                             "type": "string"
    #                         }
	# 					}
	# 				}
	# 			}
	# 		},
	# 		strict=True,
	# 	),
	# ),
	# include_blocks=True
)

    ocr_output = ocr_response.pages[0].markdown
    logger = logging.getLogger(__name__)
    logger.info(f"Mistral OCR markdown output:\n{ocr_output}")
    return {
        "text": ocr_output
    }
