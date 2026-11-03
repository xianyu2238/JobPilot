"""Generate synthetic resume files in ignored uploads/samples (no personal data)."""

from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / "uploads" / "samples"
    target.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate(sorted((ROOT / "examples" / "resumes").glob("*.txt")), start=1):
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((40, 50), path.read_text(encoding="utf-8"), fontname="china-s", fontsize=11)
            if index == 1:
                document.save(target / "01_text_resume.pdf")
            else:
                png = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).tobytes("png")
                if index == 2:
                    with pymupdf.open() as scanned:
                        scanned.new_page().insert_image(page.rect, stream=png)
                        scanned.save(target / "02_scanned_resume.pdf")
                else:
                    (target / "03_image_resume.png").write_bytes(png)
    print("Generated 3 synthetic resumes in uploads/samples/")


if __name__ == "__main__":
    main()
