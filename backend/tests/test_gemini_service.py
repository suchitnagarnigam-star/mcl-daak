
import pytest
import json
from unittest.mock import patch
from app.services.gemini_service import process_document, DEPARTMENTS

# Mock the gemini_client for testing
@pytest.fixture
def mock_gemini_client():
    with patch("app.services.gemini_service.gemini_client") as mock_client:
        yield mock_client

def test_process_document_punjabi_success(mock_gemini_client):
    # Sample OCR output in Punjabi
    punjabi_ocr_output = """ਸੇਵਾ ਵਿਖੇ,
    ਕਮਿਸ਼ਨਰ ਸਾਹਿਬ,
    ਨਗਰ ਨਿਗਮ ਲੁਧਿਆਣਾ (MCL)
    
ਨੰਬਰ: MCL/HQ/2026/7743-B
ਮਿਤੀ: 04/05/2026

ਵਿਸ਼ਾ: ਸਟ੍ਰੀਟ ਲਾਈਟਾਂ ਖਰਾਬ ਹੋਣ ਸਬੰਧੀ ਅਤੇ ਇਲਾਕੇ ਵਿੱਚ ਹਨੇਰੇ ਬਾਰੇ।

ਸ਼੍ਰੀਮਾਨ ਜੀ,
ਬੇਨਤੀ ਹੈ ਕਿ ਵਾਰਡ ਨੰਬਰ 32, ਗੁਰੂ ਨਾਨਕ ਨਗਰ ਦੀਆਂ ਮੁੱਖ ਸੜਕਾਂ 'ਤੇ ਲੱਗੀਆਂ 5 ਸਟ੍ਰੀਟ ਲਾਈਟਾਂ ਪਿਛਲੇ 3 ਹਫ਼ਤਿਆਂ ਤੋਂ ਬੰਦ ਪਈਆਂ ਹਨ। ਰਾਤ ਵੇਲੇ ਹਨੇਰੇ ਕਾਰਨ ਹਾਦਸਿਆਂ ਦਾ ਡਰ ਰਹਿੰਦਾ ਹੈ ਅਤੇ ਚੋਰੀਆਂ ਦੀਆਂ ਘਟਨਾਵਾਂ ਵਧ ਰਹੀਆਂ ਹਨ। 1l4k4 n1v4s|y4n ਨੂੰ ਆਉਣ-ਜਾਣ ਵਿੱਚ ਭਾਰੀ ਪਰੇਸ਼ਾਨੀ ਹੋ ਰਹੀ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਲਾਈਟਿੰਗ ਵਿੰਗ (Lighting Wing) ਨੂੰ ਇਹਨਾਂ ਨੂੰ ਜਲਦੀ ਠੀਕ ਕਰਨ ਦੀ ਹਦਾਇਤ ਦਿੱਤੀ ਜਾਵੇ।

ਧੰਨਵਾਦ ਸਹਿਤ,
ਬਲਦੇਵ ਸਿੰਘ (ਪ੍ਰਧਾਨ, ਰੈਜ਼ੀਡੈਂਟ ਵੈਲਫੇਅਰ ਐਸੋਸੀਏਸ਼ਨ)
ਮੋਬਾਈਲ: 98140-XXXXX
"""

    # Expected JSON output from Gemini (mocked)
    expected_llm_output = {
        "date": "04/05/2026",
        "subject": "Regarding broken street lights and darkness in the area.",
        "summary": "This document reports that 5 street lights on the main roads of Ward No. 32, Guru Nanak Nagar, have been non-functional for the past 3 weeks. The darkness at night poses a risk of accidents and an increase in thefts. Residents are facing significant inconvenience. The letter requests the Lighting Wing to fix them urgently.",
        "department": "Lights / Electrical Branch",
        "sender_name": "Baldev Singh (President, Resident Welfare Association)",
        "sender_contact": "98140-XXXXX",
        "receiver": "Commissioner Sahib, Municipal Corporation Ludhiana (MCL)",
        "reference_number": "MCL/HQ/2026/7743-B"
    }

    # Configure the mock Gemini client to return the expected output
    mock_gemini_client.generate_content.return_value.text = json.dumps(expected_llm_output)

    # Call the function under test
    result = process_document(punjabi_ocr_output)

    # Assertions
    assert result == expected_llm_output
    mock_gemini_client.generate_content.assert_called_once()

def test_process_document_hindi_success(mock_gemini_client):
    # Sample OCR output in Hindi
    hindi_ocr_output = """प्रति,
मुख्य नगर आयुक्त,
नगर निगम (MCL)

दिनांक: 12-04-2026
संदर्भ संख्या: null / ਸ਼-402

विषय: कबाड़ और प्लास्टिक कचरे के अवैध डंपिंग को हटाने के संबंध में।

महोदय,
सविनय निवेदन है कि शास्त्री नगर गली नंबर 4 के कोने पर स्थानीय बाजार का कचरा खुले में फेंका जा रहा है। 50l1d W4st3 M4n4g3m3nt विभाग द्वारा पिछले कई दिनों से यहां से कूड़ा नहीं उठाया गया है। इससे पूरे इलाके में बदबू फैली है और बीमारियां फैलने का खतरा है। कृपया स्वास्थ्य विभाग (Health & Sanitation Department) को तुरंत कार्रवाई करने का आदेश दें।

भवदीय,
रमेश कुमार शर्मा
ईमेल: ramesh.sharma2026@email.com
"""

    # Expected JSON output from Gemini (mocked)
    expected_llm_output = {
        "date": "12-04-2026",
        "subject": "Regarding the removal of illegal dumping of scrap and plastic waste.",
        "summary": "This document reports that local market waste, including scrap and plastic, is being openly dumped at the corner of Shastri Nagar, Street No. 4. The Solid Waste Management department has not collected the garbage for several days, causing bad odor and a risk of disease spread. The letter requests the Health & Sanitation Department to take immediate action.",
        "department": "Health & Sanitation Branch",
        "sender_name": "Ramesh Kumar Sharma",
        "sender_contact": "ramesh.sharma2026@email.com",
        "receiver": "Chief Municipal Commissioner, Municipal Corporation (MCL)",
        "reference_number": "null / ਸ਼-402"
    }

    # Configure the mock Gemini client to return the expected output
    mock_gemini_client.generate_content.return_value.text = json.dumps(expected_llm_output)

    # Call the function under test
    result = process_document(hindi_ocr_output)

    # Assertions
    assert result == expected_llm_output
    mock_gemini_client.generate_content.assert_called_once()

def test_process_document_english_success(mock_gemini_client):
    # Sample OCR output in English
    english_ocr_output = """TO: The Joint Commissioner, Municipal Corporation Office
FROM: Anita Desai, Green Avenue Resident Welfare
CONTACT: 9876543210 | info@greenavenue.org

REF NO: MCL/2026/ENG-99
DATE: MAY 28, 2026

SUBJ: Repair of broken water pipeline and leakage on Main Road.

Dear Sir/Madam,
This is to bring to your urgent notice that the main water distribution pipeline near House No. 14B has burst. Thousands of liters of drinking water are being wasted daily, flooding the street. The Water Supply & Sewerage Department needs to intervene immediately to plug the leak and restore normal pressure. 

Sincerely,
Anita Desai
"""

    # Expected JSON output from Gemini (mocked)
    expected_llm_output = {
        "date": "MAY 28, 2026",
        "subject": "Repair of broken water pipeline and leakage on Main Road.",
        "summary": "This document brings to urgent notice that the main water distribution pipeline near House No. 14B has burst, leading to thousands of liters of drinking water being wasted daily and flooding the street. The Water Supply & Sewerage Department needs to intervene immediately to plug the leak and restore normal pressure.",
        "department": "Operations & Maintenance (O&M) Branch",
        "sender_name": "Anita Desai",
        "sender_contact": "9876543210 | info@greenavenue.org",
        "receiver": "The Joint Commissioner, Municipal Corporation Office",
        "reference_number": "MCL/2026/ENG-99"
    }

    # Configure the mock Gemini client to return the expected output
    mock_gemini_client.generate_content.return_value.text = json.dumps(expected_llm_output)

    # Call the function under test
    result = process_document(english_ocr_output)

    # Assertions
    assert result == expected_llm_output
    mock_gemini_client.generate_content.assert_called_once()

def test_process_document_json_decode_error(mock_gemini_client):
    # Configure the mock Gemini client to return invalid JSON
    mock_gemini_client.generate_content.return_value.text = "invalid json response"

    # Call the function under test
    result = process_document("some ocr output")

    # Assertions
    assert result == {"error": "Unable to parse Gemini response as JSON."}
    mock_gemini_client.generate_content.assert_called_once()

def test_process_document_no_department_match(mock_gemini_client):
    # Sample OCR output with no matching department
    no_match_ocr_output = """TO: The Commissioner
DATE: 01/01/2026
SUBJ: Request for a new alien petting zoo.
Dear Sir/Madam, I would like to request a new alien petting zoo.
Sincerely, John Doe"""

    # Expected JSON output from Gemini (mocked) with department as null
    expected_llm_output = {
        "date": "01/01/2026",
        "subject": "Request for a new alien petting zoo.",
        "summary": "The document requests the establishment of a new alien petting zoo.",
        "department": None,
        "sender_name": "John Doe",
        "sender_contact": None,
        "receiver": "The Commissioner",
        "reference_number": None
    }

    mock_gemini_client.generate_content.return_value.text = json.dumps(expected_llm_output)

    result = process_document(no_match_ocr_output)

    assert result == expected_llm_output
    mock_gemini_client.generate_content.assert_called_once()

    print(result)