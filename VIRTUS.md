# virtus-doctor

This repo is the Virtus fork of the upstream project. Virtus uses it as a Python wheel (library use, not the
service) in the extract stage of the corpus ETL: PDF, DOC, DOCX, HTML, TXT and WPD to text, with OCR for PDFs.

- Upstream: https://github.com/freelawproject/doctor (licence BSD-2-Clause).
- Base: upstream `main` at `cce98c25f5bcf4b7340b33c5d81cfb2466624b4e`.

## Branches

- `main` is equal to upstream `main`. Only a fast-forward from upstream moves it.
- `virtus` holds our patches as separate commits on top of an upstream commit.

## Patches

One line for each commit on `virtus` that is not in upstream:

1. `Build a wheel for library use`: the `uv_build` backend in `pyproject.toml` (upstream builds no wheel). The wheel
   holds the `doctor` package without its tests and test assets; the sdist keeps them. `tool.uv.package = false`
   keeps `uv sync` from installing the project, as `docker/Dockerfile` expects. The version is
   `<upstream version>+virtus.<n>`.
2. `Add a library entry point for text extraction without Django`: `doctor/extract.py`, `extract_text(path,
   extension, ocr_available, ocr_pages_per_slice)`, with tests in `doctor/test_extract.py`. It runs the extraction
   of `/extract/doc/text/` and reads no Django setting. `extract_by_ocr` and `extract_from_pdf` in `doctor/tasks.py`
   take the OCR slice size as an optional argument; `None` reads `DOCTOR_OCR_PAGES_PER_SLICE`, so the service does
   not change.
3. `Add the release workflow of the virtus fork`: `.github/workflows/virtus-release.yml`.
4. `Add VIRTUS.md`: this file.
5. `Run the upstream deploy workflow only in upstream`: each job of `.github/workflows/deploy.yml` (Docker Hub push,
   EKS deploy) has `if: github.repository == 'freelawproject/doctor'`, so it never runs in this fork.

## Library use

```python
import asyncio

from doctor.extract import extract_text

result = asyncio.run(extract_text("/tmp/opinion.pdf", "pdf"))
print(result.content, result.extracted_by_ocr, result.page_count)
```

The caller needs no Django project and no `DJANGO_SETTINGS_MODULE`. Django is still installed, because it is a
dependency of the package. The host needs the programs and libraries that the service image installs
(`docker/Dockerfile`): poppler (`pdftotext`), ghostscript, tesseract, antiword, docx2txt, libwpd (`wpd2html`) and
libmagic (`doctor/tasks.py` imports `magic`).

## Release

1. Increase `<n>` in the `pyproject.toml` version `<upstream version>+virtus.<n>` and in the `doctor` entry of
   `uv.lock`.
2. Tag the `virtus` commit `v<upstream version>+virtus.<n>` and push the tag.
3. The workflow `virtus-release` builds the wheel and the sdist with `uv build` and publishes them with one
   `SHA256SUMS` as the release assets of the tag.
4. In `virtus`, run `tools/pins/bump.py virtus-doctor <tag>`.

## Sync with upstream

1. Fast-forward `main` to upstream `main`: `git fetch upstream && git push origin upstream/main:main`.
2. Merge `main` into `virtus` (never rebase `virtus`). Solve the conflicts in the patch commits.
3. Compare `extract_text` in `doctor/extract.py` with `extract_doc_content` in `doctor/views.py`. If upstream
   changed the extension dispatch or the extractor calls, make the same change in `extract_text`. If upstream added
   a new Django setting on the extraction path, make it an argument as patch 2 does.
4. Run `python -m unittest doctor.test_extract` with no `DJANGO_SETTINGS_MODULE`.
5. Update "Base" in this file. If the upstream version changes, set the version to `<new upstream version>+virtus.1`.
6. Do a release.
