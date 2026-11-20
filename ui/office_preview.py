"""Baca isi dokumen Office untuk pratinjau teks tanpa menjalankan Office."""

import io
import posixpath
from collections.abc import Iterator
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


def _parts(archive: ZipFile, main: str, tag: str) -> Iterator[tuple[str, str]]:
    """Ikuti urutan slide atau lembar di dokumen, termasuk setelah dipindahkan."""
    folder, name = posixpath.split(main)
    relationships = ET.fromstring(archive.read(f"{folder}/_rels/{name}.rels"))
    targets = {
        node.get("Id"): node.attrib["Target"] for node in relationships
        if node.get("TargetMode") != "External"
    }
    for node in ET.fromstring(archive.read(main)).iterfind(f".//{{*}}{tag}"):
        identifier = next((v for k, v in node.attrib.items() if k.endswith("}id")), None)
        if identifier in targets:
            path = posixpath.join(folder, targets[identifier])
            path = posixpath.normpath(path).lstrip("/")
            if path.endswith(".xml"):
                yield node.get("name", ""), path


def _paragraphs(root: ET.Element) -> Iterator[str]:
    for paragraph in root.iterfind(".//{*}p"):
        yield "".join(node.text or "" for node in paragraph.iterfind(".//{*}t"))


def _lines(archive: ZipFile) -> Iterator[str]:
    if "word/document.xml" in archive.NameToInfo:
        yield from _paragraphs(ET.fromstring(archive.read("word/document.xml")))
    elif "ppt/presentation.xml" in archive.NameToInfo:
        for index, (_, path) in enumerate(_parts(archive, "ppt/presentation.xml", "sldId"), 1):
            yield f"Slide {index}"
            yield from _paragraphs(ET.fromstring(archive.read(path)))
            yield ""
    elif "xl/workbook.xml" in archive.NameToInfo:
        strings = []
        if "xl/sharedStrings.xml" in archive.NameToInfo:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in si.iterfind(".//{*}t")) for si in root]
        for name, path in _parts(archive, "xl/workbook.xml", "sheet"):
            yield f"Lembar {name}"
            root = ET.fromstring(archive.read(path))
            for row in root.iterfind(".//{*}sheetData/{*}row"):
                cells = []
                for cell in row.iterfind("{*}c"):
                    value = cell.findtext("{*}v", "")
                    if cell.get("t") == "s":
                        value = strings[int(value)]
                    elif cell.get("t") == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iterfind(".//{*}t"))
                    elif not value and cell.find("{*}f") is not None:
                        value = "=" + cell.findtext("{*}f", "")
                    if value:
                        cells.append(f"{cell.get('r', '')}  {value}")
                if cells:
                    yield "    |    ".join(cells)
            yield ""
    else:
        raise ValueError("Format dokumen ini belum mendukung pratinjau.")


def office_text(data: bytes) -> str:
    """Batasi XML yang dimekarkan serta teks yang ditampilkan dari arsip Office."""
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            xml_size = sum(part.file_size for part in archive.infolist()
                           if part.filename.endswith((".xml", ".rels")))
            if xml_size > 32 * 1024 * 1024:
                raise ValueError("Isi dokumen terlalu besar untuk pratinjau teks.")
            lines = []
            remaining = 100_000
            for line in _lines(archive):
                lines.append(line[:remaining])
                remaining -= len(line) + 1
                if remaining <= 0:
                    lines.append("… Pratinjau dibatasi hingga 100.000 karakter.")
                    break
            return "\n".join(lines).strip() or "Dokumen ini tidak memuat teks."
    except (BadZipFile, ET.ParseError, KeyError, IndexError, RuntimeError, NotImplementedError) as exc:
        raise ValueError("Isi dokumen Office tidak dapat dibaca.") from exc
