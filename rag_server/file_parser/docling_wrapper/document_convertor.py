import functools
import tempfile
import time
import traceback
from pathlib import Path
from typing import Iterable

import requests
from docling.datamodel.base_models import ConversionStatus, Page, ErrorItem, DoclingComponentType
from docling.datamodel.document import InputDocument, ConversionResult, DocumentConversionInput
from docling.datamodel.settings import settings
from docling.document_converter import DocumentConverter, _log
from docling.utils.utils import chunkify
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from celery_task.model import ParseFileNotify, send_process_notify


class MyDocumentConverter(DocumentConverter):

    def convert_(self, input: DocumentConversionInput,
                 file_node_id: str,
                 notify_url: str) -> Iterable[ConversionResult]:

        for input_batch in chunkify(
                input.docs(pdf_backend=self.pdf_backend), settings.perf.doc_batch_size
        ):
            _log.info(f"Going to convert document batch...")
            # parallel processing only within input_batch
            # with ThreadPoolExecutor(
            #    max_workers=settings.perf.doc_batch_concurrency
            # ) as pool:
            #   yield from pool.map(self.process_document, input_batch)

            # Note: Pdfium backend is not thread-safe, thread pool usage was disabled.
            yield from map(functools.partial(self._process_document_,
                                             file_node_id=file_node_id,
                                             notify_url=notify_url),
                           input_batch)

    def convert_single_(self,
                        source: Path | AnyHttpUrl | str,
                        file_node_id: str,
                        notify_url: str) -> ConversionResult:
        """Convert a single document.

        Args:
            source (Path | AnyHttpUrl | str): The PDF input source. Can be a path or URL.
            file_node_id:
            notify_url:
        Raises:
            ValueError: If source is of unexpected type.
            RuntimeError: If conversion fails.

        Returns:
            ConversionResult: The conversion result object.

        """
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                http_url: AnyHttpUrl = TypeAdapter(AnyHttpUrl).validate_python(source)
                res = requests.get(http_url, stream=True)
                res.raise_for_status()
                fname = None
                # try to get filename from response header
                if cont_disp := res.headers.get("Content-Disposition"):
                    for par in cont_disp.strip().split(";"):
                        # currently only handling directive "filename" (not "*filename")
                        if (split := par.split("=")) and split[0].strip() == "filename":
                            fname = "=".join(split[1:]).strip().strip("'\"") or None
                            break
                # otherwise, use name from URL:
                if fname is None:
                    fname = Path(http_url.path).name or self._default_download_filename
                local_path = Path(temp_dir) / fname
                with open(local_path, "wb") as f:
                    for chunk in res.iter_content(chunk_size=1024):  # using 1-KB chunks
                        f.write(chunk)
            except ValidationError:
                try:
                    local_path = TypeAdapter(Path).validate_python(source)
                except ValidationError:
                    raise ValueError(
                        f"Unexpected file path type encountered: {type(source)}"
                    )
            conv_inp = DocumentConversionInput.from_paths(paths=[local_path])
            conv_res_iter = self.convert_(conv_inp, file_node_id, notify_url)
            conv_res: ConversionResult = next(conv_res_iter)
        if conv_res.status not in {
            ConversionStatus.SUCCESS,
            ConversionStatus.PARTIAL_SUCCESS,
        }:
            raise RuntimeError(f"Conversion failed with status: {conv_res.status}")
        return conv_res

    def _process_document_(self,
                           in_doc: InputDocument,
                           file_node_id: str,
                           notify_url: str) -> ConversionResult:
        start_doc_time = time.time()
        conv_res = ConversionResult(input=in_doc)

        _log.info(f"Processing document {in_doc.file.name}")

        if not in_doc.valid:
            conv_res.status = ConversionStatus.FAILURE
            return conv_res

        for i in range(0, in_doc.page_count):
            conv_res.pages.append(Page(page_no=i))

        all_assembled_pages = []

        try:
            iter_count = 0
            # Iterate batches of pages (page_batch_size) in the doc
            for page_batch in chunkify(conv_res.pages, settings.perf.page_batch_size):
                iter_count += 1
                start_pb_time = time.time()
                # Pipeline

                # 1. Initialise the page resources
                init_pages = map(
                    functools.partial(self._initialize_page, in_doc), page_batch
                )

                # 2. Populate page image
                pages_with_images = map(
                    functools.partial(self._populate_page_images, in_doc), init_pages
                )

                # 3. Populate programmatic page cells
                pages_with_cells = map(
                    functools.partial(self._parse_page_cells, in_doc),
                    pages_with_images,
                )

                # 4. Run pipeline stages
                pipeline_pages = self.model_pipeline.apply(pages_with_cells)

                # 5. Assemble page elements (per page)
                assembled_pages = self.page_assemble_model(pipeline_pages)

                # exhaust assembled_pages
                for assembled_page in assembled_pages:
                    # Free up mem resources before moving on with next batch

                    # Remove page images (can be disabled)
                    if self.assemble_options.images_scale is None:
                        assembled_page._image_cache = {}

                    # Unload backend
                    assembled_page._backend.unload()

                    all_assembled_pages.append(assembled_page)

                end_pb_time = time.time() - start_pb_time
                _log.info(f"Finished converting page batch time={end_pb_time:.3f}")

                # 通知解析进度
                percent = min(100, 100 * iter_count * settings.perf.page_batch_size / len(conv_res.pages))
                send_process_notify(notify_url, ParseFileNotify, file_node_id, percent)

            # Free up mem resources of PDF backend
            in_doc._backend.unload()

            conv_res.pages = all_assembled_pages
            self._assemble_doc(conv_res)

            status = ConversionStatus.SUCCESS
            for page in conv_res.pages:
                if not page._backend.is_valid():
                    conv_res.errors.append(
                        ErrorItem(
                            component_type=DoclingComponentType.PDF_BACKEND,
                            module_name=type(page._backend).__name__,
                            error_message=f"Page {page.page_no} failed to parse.",
                        )
                    )
                    status = ConversionStatus.PARTIAL_SUCCESS

            conv_res.status = status

        except Exception as e:
            conv_res.status = ConversionStatus.FAILURE
            trace = "\n".join(traceback.format_exception(e))
            _log.info(
                f"Encountered an error during conversion of document {in_doc.document_hash}:\n"
                f"{trace}"
            )

        end_doc_time = time.time() - start_doc_time
        _log.info(
            f"Finished converting document time-pages={end_doc_time:.2f}/{in_doc.page_count}"
        )

        return conv_res
