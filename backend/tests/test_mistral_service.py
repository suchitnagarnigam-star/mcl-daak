import base64
import os
from pathlib import Path

from dotenv import load_dotenv
from mistralai.client import Mistral
from mistralai.client.models import ResponseFormat, JSONSchema

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

api_key = os.environ["MISTRAL_API_KEY"]

client = Mistral(api_key=api_key)

def encode_file(file_path: Path) -> str:
    with file_path.open("rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

file_path = Path(__file__).resolve().parents[1] / "processed" / "eng_eg.jpeg"
base64_file = encode_file(file_path)

ocr_response = client.ocr.process(
    document={
      "type": "image_url",
      "image_url": f"data:image/jpeg;base64,{base64_file}"
    },
    model="mistral-ocr-latest",
	include_image_base64=True,
	document_annotation_format=ResponseFormat(
		type="json_schema",
		json_schema=JSONSchema(
			name="response_schema",
			schema_definition={
				"type": "object",
				"required": [
					"document_metadata",
					"association_details",
					"letter_details"
				],
				"properties": {
					"document_metadata": {
						"type": "object",
						"required": [
							"account_info",
							"document_url"
						],
						"properties": {
							"account_info": {
								"type": "string"
							},
							"document_url": {
								"type": "string"
							}
						}
					},
					"association_details": {
						"type": "object",
						"required": [
							"name",
							"registration_details",
							"office_bearers",
							"contact_info"
						],
						"properties": {
							"name": {
								"type": "string"
							},
							"registration_details": {
								"type": "string"
							},
							"office_bearers": {
								"type": "string"
							},
							"office_bearers_list": {
								"type": "string"
							},
							"office_bearers_details": {
								"type": "string"
							},
							"office_bearers_roles": {
								"type": "string"
							},
							"office_bearers_names": {
								"type": "string"
							},
							"contact_info": {
								"type": "string"
							},
							"address": {
								"type": "string"
							},
							"phone": {
								"type": "string"
							},
							"email": {
								"type": "string"
							}
						}
					},
					"letter_details": {
						"type": "object",
						"required": [
							"recipient",
							"subject",
							"date",
							"body",
							"signatories"
						],
						"properties": {
							"recipient": {
								"type": "string"
							},
							"recipient_title": {
								"type": "string"
							},
							"subject": {
								"type": "string"
							},
                            "date": {
                                "type": "string"
                            },
                            "body": {
                                "type": "string"
                            },
                            "signatories": {
                                "type": "string"
                            },
                            "body_paragraphs": {
                                "type": "string"
                            }
						}
					}
				}
			},
			strict=True,
		),
	),
	include_blocks=True
)

print(type(ocr_response))
print(ocr_response.__dict__)
