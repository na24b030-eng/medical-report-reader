from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

def generate_sample_lab_report(output_path: str = "samples/sample_report.png"):
    """Creates a realistic synthetic scanned lab report image with OCR-typical text."""
    width, height = 800, 500
    img = Image.new("RGB", (width, height), color=(250, 250, 250))
    draw = ImageDraw.Draw(img)

    # Header
    draw.text((40, 30), "METROPOLIS CLINICAL LABORATORIES", fill=(20, 20, 20))
    draw.text((40, 55), "Patient: John Doe | Age: 42 | Gender: Male | Date: 2026-09-15", fill=(80, 80, 80))
    draw.line([(40, 85), (760, 85)], fill=(180, 180, 180), width=2)

    # Report Body matching PDF OCR Sample
    draw.text((40, 110), "COMPLETE BLOOD COUNT (CBC)", fill=(30, 30, 30))
    draw.text((40, 150), "CBC: Hemglobin 10.2 g/dL (Low)", fill=(20, 20, 20))
    draw.text((40, 190), "WBC 11200 /uL (Hgh)", fill=(20, 20, 20))
    draw.text((40, 230), "Platelets 280000 /uL (Normal)", fill=(20, 20, 20))

    draw.line([(40, 320), (760, 320)], fill=(200, 200, 200), width=1)
    draw.text((40, 340), "Status: Verified by Clinical Pathologist", fill=(100, 100, 100))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    print(f"Sample report image generated at: {output_path}")

if __name__ == "__main__":
    generate_sample_lab_report()
