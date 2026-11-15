"""Read chosen members of a very large public zip without downloading the whole archive.

The batch distillation dataset is one 85 GB zip, almost all of it audio and video. Its tables are about 150 MB.
The server honours byte ranges, so the archive's directory and only the wanted members are fetched.
"""
from __future__ import annotations

import io
import urllib.request
import zipfile

BLOCK = 4 * 1024 * 1024


class HttpFile(io.RawIOBase):
    """A read-only, seekable view of a remote file, fetched in blocks on demand."""

    def __init__(self, url: str):
        self.url, self.position, self.blocks = url, 0, {}
        request = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'skill-benchmark-fetch/1'})
        with urllib.request.urlopen(request, timeout=120) as response:
            self.size = int(response.headers['Content-Length'])
        self.fetched = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        self.position = offset if whence == io.SEEK_SET else self.position + offset if whence == io.SEEK_CUR else self.size + offset
        return self.position

    def _block(self, index: int) -> bytes:
        if index not in self.blocks:
            start, end = index * BLOCK, min((index + 1) * BLOCK, self.size) - 1
            request = urllib.request.Request(self.url, headers={'Range': f'bytes={start}-{end}', 'User-Agent': 'skill-benchmark-fetch/1'})
            with urllib.request.urlopen(request, timeout=300) as response:
                data = response.read()
            if len(data) != end - start + 1:
                raise OSError('the server did not return the requested byte range')
            if len(self.blocks) > 24:           # keep memory bounded; members are read once, front to back
                self.blocks.pop(next(iter(self.blocks)))
            self.blocks[index] = data
            self.fetched += len(data)
        return self.blocks[index]

    def read(self, size=-1):
        if size < 0:
            size = self.size - self.position
        out = bytearray()
        while size > 0 and self.position < self.size:
            index, offset = divmod(self.position, BLOCK)
            chunk = self._block(index)[offset:offset + size]
            out += chunk
            self.position += len(chunk)
            size -= len(chunk)
        return bytes(out)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)


def open_remote(url: str) -> tuple[zipfile.ZipFile, HttpFile]:
    remote = HttpFile(url)
    return zipfile.ZipFile(remote), remote
