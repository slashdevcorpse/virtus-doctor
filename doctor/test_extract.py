"""Tests of doctor.extract, the extraction library without Django.

These tests call the library directly. They need no running service, and
the ones that start a new interpreter run it with no Django settings.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont

from doctor import tasks
from doctor.extract import ExtractedText, extract_text

ASSETS = Path(__file__).parent / "test_assets"


class NoSettings:
    """Fails the test on any read of a Django setting."""

    def __getattr__(self, name):
        raise AssertionError(f"read the Django setting {name}")


def run_without_django(code: str) -> str:
    """Run code in a new interpreter with no Django settings module.

    :param code: Python code that prints its result
    :return: What the code printed
    """
    env = {
        k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"
    }
    root = str(Path(__file__).parent.parent)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (root, env.get("PYTHONPATH")) if p
    )
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout


def make_scanned_pdf(path: str, markers: list[str]) -> None:
    """Write a PDF with one image page per marker word and no text layer."""
    font = ImageFont.load_default(size=48)
    pages = []
    for marker in markers:
        page = Image.new("L", (1275, 1650), 255)
        ImageDraw.Draw(page).text(
            (200, 300), f"Page {marker} of the record", fill=0, font=font
        )
        pages.append(page)
    pages[0].save(path, save_all=True, append_images=pages[1:], resolution=150)


class ExtractTextTest(unittest.IsolatedAsyncioTestCase):
    markers = ["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO"]

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.scan_path = os.path.join(cls.tmpdir.name, "scan.pdf")
        make_scanned_pdf(cls.scan_path, cls.markers)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_runs_without_django_settings(self):
        """Does a text PDF extract with no Django settings module?

        OCR is off here so that the test needs only pdftotext;
        test_ocr_without_django_settings covers OCR.
        """
        out = run_without_django(
            f"""
            import asyncio

            from doctor.extract import extract_text

            result = asyncio.run(
                extract_text(
                    {str(ASSETS / "vector-pdf.pdf")!r}, "pdf", ocr_available=False
                )
            )
            from django.conf import settings

            print(settings.configured)
            print(result.returncode, result.extracted_by_ocr, result.page_count)
            print(result.content[:14])
            """
        )
        self.assertEqual(
            out.splitlines(), ["False", "0 False 30", "(Slip Opinion)"]
        )

    async def test_ocr_slices_read_no_setting(self):
        """Does OCR slice by the argument and read no Django setting?"""
        ranges = []

        async def fake_ocr(path, first=None, last=None):
            ranges.append((first, last))
            return True, f"text of pages {first} to {last}"

        with (
            patch.object(tasks, "settings", NoSettings()),
            patch("doctor.tasks._ocr_page_range", side_effect=fake_ocr),
        ):
            result = await extract_text(
                self.scan_path, "pdf", ocr_pages_per_slice=2
            )
        self.assertEqual(ranges, [(1, 2), (3, 4), (5, None)])
        self.assertTrue(result.extracted_by_ocr)
        self.assertEqual(result.page_count, len(self.markers))
        self.assertEqual(
            result.content.split(tasks.OCR_PAGE_SEPARATOR),
            [
                "text of pages 1 to 2",
                "text of pages 3 to 4",
                "text of pages 5 to None",
            ],
        )

    async def test_no_ocr_when_not_available(self):
        """Does a scanned PDF stay without OCR when OCR is not available?"""
        with patch("doctor.tasks.extract_by_ocr") as ocr:
            result = await extract_text(
                self.scan_path, "pdf", ocr_available=False
            )
        ocr.assert_not_called()
        self.assertFalse(result.extracted_by_ocr)

    @unittest.skipUnless(
        shutil.which("gs") and shutil.which("tesseract"),
        "OCR needs ghostscript and tesseract",
    )
    def test_ocr_without_django_settings(self):
        """Does a scanned PDF OCR end to end with no Django settings?"""
        out = run_without_django(
            f"""
            import asyncio

            from doctor.extract import extract_text

            result = asyncio.run(
                extract_text({self.scan_path!r}, "pdf", ocr_pages_per_slice=2)
            )
            print(result.extracted_by_ocr, result.page_count)
            print(repr(result.content))
            """
        )
        first, content = out.splitlines()
        self.assertEqual(first, "True 5")
        for marker in self.markers:
            self.assertIn(marker, content)
        self.assertEqual(content.count("\\x0c"), len(self.markers) - 1)

    async def test_txt(self):
        result = await extract_text(str(ASSETS / "small_txt.txt"), "txt")
        self.assertEqual(result.returncode, 0)
        self.assertIsNone(result.err)
        self.assertIsNone(result.page_count)
        self.assertTrue(result.content.strip())

    async def test_html(self):
        result = await extract_text(str(ASSETS / "broken_html.html"), "html")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.content.strip())

    async def test_unknown_extension(self):
        result = await extract_text(str(ASSETS / "small.xml"), "xml")
        self.assertEqual(
            result,
            ExtractedText(
                content="",
                err="Unable to extract content due to unknown extension",
                returncode=1,
                extracted_by_ocr=False,
                page_count=None,
            ),
        )


if __name__ == "__main__":
    unittest.main()
