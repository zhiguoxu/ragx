import threading
import time

from docling.document_converter import DocumentConverter
from docling_core.types.doc.base import Figure, BaseText
from docling_core.types import Ref, Table
from tabulate import tabulate
from docling_core.types import Document as DsDocument

from config.config import config
from file_parser.docling_wrapper.document_convertor import MyDocumentConverter


def export_to_markdown(  # noqa: C901
        self: DsDocument,
        delim: str = "\n\n",
        main_text_start: int = 0,
        main_text_stop: int | None = None,
        main_text_labels: list[str] = [
            "title",
            "subtitle-level-1",
            "paragraph",
            "caption",
            "table",
            "figure",
        ],
        strict_text: bool = False,
        image_placeholder: str = "<!-- image -->",
) -> list[str]:
    has_title = False
    prev_text = ""
    md_texts: list[list[str]] = [[] for _ in range(self.file_info.num_pages)]

    if self.main_text is not None:
        # collect all captions embedded in table and figure objects
        # to avoid repeating them
        embedded_captions = set()
        for orig_item in self.main_text[main_text_start:main_text_stop]:
            item = (
                self._resolve_ref(orig_item)
                if isinstance(orig_item, Ref)
                else orig_item
            )
            if item is None:
                continue

            if (
                    isinstance(item, (Table, Figure))
                    and item.text
                    and item.obj_type in main_text_labels
            ):
                embedded_captions.add(item.text)

        # serialize document to markdown
        for orig_item in self.main_text[main_text_start:main_text_stop]:
            markdown_text = ""

            item = (
                self._resolve_ref(orig_item)
                if isinstance(orig_item, Ref)
                else orig_item
            )
            if item is None:
                continue

            item_type = item.obj_type
            if isinstance(item, BaseText) and item_type in main_text_labels:
                text = item.text

                # skip captions of they are embedded in the actual
                # floating object
                if item_type == "caption" and text in embedded_captions:
                    continue

                # ignore repeated text
                if prev_text == text or text is None:
                    continue
                else:
                    prev_text = text

                # first title match
                if item_type == "title" and not has_title:
                    if strict_text:
                        markdown_text = f"{text}"
                    else:
                        markdown_text = f"# {text}"
                    has_title = True

                # secondary titles
                elif item_type in {"title", "subtitle-level-1"} or (
                        has_title and item_type == "title"
                ):
                    if strict_text:
                        markdown_text = f"{text}"
                    else:
                        markdown_text = f"## {text}"

                # normal text
                else:
                    markdown_text = text

            elif (
                    isinstance(item, Table)
                    and item.data
                    and item_type in main_text_labels
            ):

                md_table = ""
                table = []
                for row in item.data:
                    tmp = []
                    for col in row:
                        tmp.append(col.text)
                    table.append(tmp)

                if len(table) > 1 and len(table[0]) > 0:
                    try:
                        md_table = tabulate(
                            table[1:], headers=table[0], tablefmt="github"
                        )
                    except ValueError:
                        md_table = tabulate(
                            table[1:],
                            headers=table[0],
                            tablefmt="github",
                            disable_numparse=True,
                        )

                markdown_text = ""
                if item.text:
                    markdown_text = item.text
                if not strict_text:
                    markdown_text += "\n" + md_table

            elif isinstance(item, Figure) and item_type in main_text_labels:
                markdown_text = ""
                if item.text:
                    markdown_text = item.text
                if not strict_text:
                    markdown_text += f"\n{image_placeholder}"

            if markdown_text:
                page_index = item.prov[0].page - 1
                md_texts[page_index].append(markdown_text)

    return [delim.join(item) for item in md_texts]


converter: MyDocumentConverter | None = None
lock = threading.Lock()


def docling_pdf_to_markdown(source: str, file_node_id: str, notify_url: str) -> list[str]:
    # from celery_task.model import AcceptedNotifyRequest
    # from celery_task.model import ParseFileNotify
    # notify_request = AcceptedNotifyRequest(type='ParseFileNotify',
    #                                        data=ParseFileNotify(file_node_id=file_node_id,
    #                                                             percent=100).model_dump())
    # import requests
    # requests.post(notify_url, json=notify_request.model_dump())

    start = time.time()
    global converter
    with lock:
        if converter is None:
            print('*' * 20, config.docling_model_path)
            converter = MyDocumentConverter(artifacts_path=config.docling_model_path)
            # converter = DocumentConverter()
    print("-------- used 1: ", time.time() - start)
    start = time.time()
    result = converter.convert_single_(source, file_node_id, notify_url)
    # result = converter.convert_single(source)
    print("-------- used 2: ", time.time() - start)
    start = time.time()
    ret = export_to_markdown(result.output)
    print("-------- used 3: ", time.time() - start)
    start = time.time()
    return ret
