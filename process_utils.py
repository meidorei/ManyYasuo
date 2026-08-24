"""Efficient helpers for reading 7-Zip pipe output."""

from __future__ import annotations

import codecs
from collections.abc import Iterator
from typing import BinaryIO


def iter_decoded_chunks(stream: BinaryIO, chunk_size: int = 4096) -> Iterator[str]:
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    read = getattr(stream, "read1", stream.read)
    while True:
        chunk = read(chunk_size)
        if not chunk:
            break
        text = decoder.decode(chunk)
        if text:
            yield text
    tail = decoder.decode(b"", final=True)
    if tail:
        yield tail
