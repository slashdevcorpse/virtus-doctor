"""Text extraction for Python callers, without Django.

The service extracts text at ``/extract/doc/text/``
(``doctor.views.extract_doc_content``). This module runs the same
extraction as a library: it reads no Django setting, so a caller needs no
Django project and no ``DJANGO_SETTINGS_MODULE``. The OCR slice size is an
argument instead of the ``DOCTOR_OCR_PAGES_PER_SLICE`` setting.
"""

from dataclasses import dataclass

from lxml.etree import ParserError, XMLSyntaxError

from doctor.tasks import (
    OCR_FAIL_MSG,
    extract_from_doc,
    extract_from_docx,
    extract_from_html,
    extract_from_pdf,
    extract_from_txt,
    extract_from_wpd,
    get_page_count,
)

# The default of settings.DOCTOR_OCR_PAGES_PER_SLICE.
DEFAULT_OCR_PAGES_PER_SLICE = 25

EXTENSIONS = ("pdf", "doc", "docx", "html", "txt", "wpd")


@dataclass(frozen=True)
class ExtractedText:
    """The result of one extraction, as the service returns it.

    :ivar content: The text. Text from a PDF has a form feed between pages.
    :ivar err: The error output of the extractor, or None
    :ivar returncode: 0 on success
    :ivar extracted_by_ocr: Whether the text came from OCR
    :ivar page_count: The page count of a PDF, else None (0 if pypdf
        cannot read the PDF)
    """

    content: str
    err: str | None
    returncode: int
    extracted_by_ocr: bool
    page_count: int | None


async def extract_text(
    path: str,
    extension: str,
    ocr_available: bool = True,
    ocr_pages_per_slice: int = DEFAULT_OCR_PAGES_PER_SLICE,
) -> ExtractedText:
    """Extract the text of a document file.

    PDFs go through pdftotext, then tesseract if the PDF has images or no
    text and OCR is available. doc, docx and wpd files go through antiword,
    docx2txt and wpd2html. Those programs must be on the PATH.

    :param path: The path to the file
    :param extension: The file type, one of EXTENSIONS (lower case, no dot)
    :param ocr_available: Whether OCR may run on a PDF
    :param ocr_pages_per_slice: How many PDF pages OCR does at a time
    :return: The extracted text and how it was made
    """
    page_count = get_page_count(path, extension)
    extracted_by_ocr = False
    err = None
    try:
        if extension == "pdf":
            (
                content,
                err,
                returncode,
                extracted_by_ocr,
            ) = await extract_from_pdf(
                path, ocr_available, page_count, ocr_pages_per_slice
            )
        elif extension == "doc":
            content, err, returncode = await extract_from_doc(path)
        elif extension == "docx":
            content, err, returncode = await extract_from_docx(path)
        elif extension == "html":
            content, err, returncode = extract_from_html(path)
        elif extension == "txt":
            content, err, returncode = extract_from_txt(path)
        elif extension == "wpd":
            content, err, returncode = await extract_from_wpd(path)
        else:
            content = ""
            err = "Unable to extract content due to unknown extension"
            returncode = 1
    except (XMLSyntaxError, ParserError) as e:
        content = OCR_FAIL_MSG
        err = f"HTML cleaning failed due to {type(e).__name__}."
        returncode = 1
    if isinstance(err, bytes):
        err = err.decode(errors="replace")
    return ExtractedText(
        content=content,
        err=err or None,
        returncode=returncode if returncode is not None else 1,
        extracted_by_ocr=extracted_by_ocr,
        page_count=page_count,
    )
