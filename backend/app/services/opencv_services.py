"""THIS WHOLE CODE IS LIKE A TEMPLATE SO THAT THE FUNCTION NAMES STAY THE SAME WHILE YOU STILL HAVE TO COMPLETE THE ENTIRE FUNCTIONALITY"""

from pathlib import Path
import cv2
import numpy as np

PROCESSED_DIR = Path("processed")
# this will create the processed directory if it doesn't exist
PROCESSED_DIR.mkdir(exist_ok=True)


# placeholder for openCV preprocessing.
def process_image(file_path: str) -> str:
    """
    Preprocess image to use for paddleocr and after adjusting the image, save processed RGB image.
    """
    
    source = Path(file_path)
    destination = PROCESSED_DIR / source.name

    # ------------------------------------------------
    # 1. Read image
    # ------------------------------------------------
    image = cv2.imread(str(source))

    if image is None:
        raise ValueError(f"Could not read the image file: {source}")

    # ------------------------------------------------
    # 2. Convert BGR -> RGB
    # ------------------------------------------------
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # ------------------------------------------------
    # 3. Brightness Adjustment
    # ------------------------------------------------
    brightness = 0  # Adjust this value as needed
    if brightness != 0:
        rgb =  cv2.convertScaleAbs(
            rgb,
            alpha= 1.0,
            beta= brightness
        )

     # ------------------------------------------------
     # 4. Contrast Adjustment
     # ------------------------------------------------
    contrast = 1.0  # Adjust this value as needed
    if contrast != 1.0:
        rgb = cv2.convertScaleAbs(
            rgb,
            alpha= contrast,
            beta= 0
        )

    # -------------------------------------------------
    # 5. Contrast & Sharpening for OCR (No Gaussian Blur)
    # -------------------------------------------------
    # Avoid GaussianBlur as it blurs character edges and degrades OCR accuracy
    kernel = np.array([
        [0, -1, 0],
        [-1, 5, -1],
        [0, -1, 0]
    ])
    rgb = cv2.filter2D(rgb, -1, kernel)

    # -------------------------------------------------
    # 6. Ensuring 8-bit 3-channel image
    # -------------------------------------------------
    rgb =  np.clip(rgb, 0, 255).astype(np.uint8)

    if len(rgb.shape) != 3 or rgb.shape[2] != 3:
        raise ValueError(f"Processed image is not a 3-channel RGB image: {destination}")

    # -------------------------------------------------
    # Convert RGB -> BGR and save the processed image
    # -------------------------------------------------
    output_bgr =  cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    success = cv2.imwrite(str(destination), output_bgr)
    if not success:
        raise IOError(f"Failed to write the processed image to: {destination}")

    # # convert image to grayscale
    # gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # # save processed image
    # cv2.imwrite(str(destination), gray)    

    return str(destination)