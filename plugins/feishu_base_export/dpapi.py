"""Windows DPAPI wrapper. Other platforms fail closed and do not invent ciphertext."""

from __future__ import annotations

import sys


class DpapiUnavailable(RuntimeError):
    pass


class WindowsDpapiProtector:
    name = "windows-dpapi"

    def protect(self, data: bytes) -> bytes:
        if sys.platform != "win32":
            raise DpapiUnavailable("DPAPI protect was not called: this is not Windows")
        return _crypt(data, protect=True)

    def unprotect(self, data: bytes) -> bytes:
        if sys.platform != "win32":
            raise DpapiUnavailable("DPAPI unprotect was not called: this is not Windows")
        return _crypt(data, protect=False)


def production_protector() -> WindowsDpapiProtector:
    if sys.platform != "win32":
        raise DpapiUnavailable("refusing to store Feishu user tokens without Windows DPAPI")
    return WindowsDpapiProtector()


def _crypt(data: bytes, *, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buffer = ctypes.create_string_buffer(data)
    in_blob = DataBlob(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_char)))
    out_blob = DataBlob()
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = function(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
    if not ok:
        raise DpapiUnavailable("CryptProtectData failed" if protect else "CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
