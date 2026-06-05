"""Argus ``.avux`` metadata reader.

.avux is Argus Enterprise's Valuation Underwriting eXchange format —
an OPC ZIP archive (like .docx) with three relevant entries:

    Content/Summary.xml    plain-text envelope summary
    Content/Info.xml       plain-text UTF-16 ModelFileInfo
    Content/Input.xml      **encrypted** — full deal payload

The Input.xml payload uses Argus's product-level encryption even when
Summary reports EncryptionMode="None" (the "None" refers to whether the
*user* added a password — the default product key still applies). Without
the Argus COM API or a published decryption routine we cannot read it.

This module ships a metadata-only loader: it extracts Summary + Info and
exposes the property header so callers can stub-create a ``Property``
with the right name / type / dates, then either (a) hand-fill the rest
or (b) pivot to ``.aeex`` export from Argus for the full payload.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
from xml.etree import ElementTree as ET


class AvuxEncryptedError(RuntimeError):
    """Raised when the caller tries to access the encrypted Input.xml payload."""


@dataclass(frozen=True)
class AvuxMetadata:
    """Plain-text metadata extracted from a .avux package."""

    property_name: Optional[str]
    property_id: Optional[str]
    property_type: Optional[str]
    description: Optional[str]
    address_line_1: Optional[str]
    address_line_2: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    analysis_begin: Optional[datetime]
    analysis_length: Optional[int]
    currency: Optional[str]
    measure_unit: Optional[str]
    argus_release: Optional[str]
    avux_version: Optional[str]
    product_version: Optional[str]
    summary_encryption_mode: Optional[str]
    file_encryption_mode: Optional[str]


def read_avux_metadata(path: Union[str, Path]) -> AvuxMetadata:
    """Parse Summary.xml + Info.xml from a .avux archive into ``AvuxMetadata``.

    Raises ``AvuxEncryptedError`` if the archive itself is encrypted at the
    zip layer (rare). The Input.xml payload is not accessed by this function.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f".avux file not found: {path}")

    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise AvuxEncryptedError(
            f"{path.name} is not a readable OPC archive (corrupt or fully encrypted): {exc}"
        ) from exc

    with archive:
        summary_xml = _read_text(archive, "Content/Summary.xml", encoding="utf-8")
        info_xml = _read_text(archive, "Content/Info.xml", encoding="utf-16")

    summary_mode = _summary_encryption_mode(summary_xml)
    info_fields = _info_fields(info_xml)

    return AvuxMetadata(
        property_name=info_fields.get("GenPropertyName"),
        property_id=info_fields.get("GenPropertyID"),
        property_type=info_fields.get("GenPropertyTypeItem"),
        description=info_fields.get("GenPropertyDescription"),
        address_line_1=info_fields.get("GenAddressLine1"),
        address_line_2=info_fields.get("GenAddressLine2"),
        city=info_fields.get("GenPropertyCity"),
        state=info_fields.get("GenPropertyState"),
        country=info_fields.get("GenCountry"),
        analysis_begin=_parse_datetime(info_fields.get("GenAnalysisBeginDate")),
        analysis_length=_parse_int(info_fields.get("GenAnalysisLength")),
        currency=info_fields.get("ModCurrencyItem"),
        measure_unit=info_fields.get("ModMeasureItem"),
        argus_release=info_fields.get("Release"),
        avux_version=info_fields.get("AVUXVersion"),
        product_version=info_fields.get("ProductVersion"),
        summary_encryption_mode=summary_mode,
        file_encryption_mode=info_fields.get("FileEncryptionMode"),
    )


def _read_text(archive: zipfile.ZipFile, name: str, encoding: str) -> str:
    with archive.open(name) as fh:
        return fh.read().decode(encoding)


def _summary_encryption_mode(xml_text: str) -> Optional[str]:
    root = ET.fromstring(xml_text)
    return root.attrib.get("EncryptionMode")


def _info_fields(xml_text: str) -> dict[str, str]:
    root = ET.fromstring(xml_text)
    out: dict[str, str] = {}
    for child in root:
        tag = child.tag.split("}", 1)[-1]
        if child.text is None:
            continue
        text = child.text.strip()
        if text:
            out[tag] = text
    return out


def _parse_datetime(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.rstrip("Z"))
    except ValueError:
        return None


def _parse_int(v: Optional[str]) -> Optional[int]:
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None
