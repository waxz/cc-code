"""
serialization.py
-----------------
Pluggable, framing-aware serializer shared by both the shared-memory
transport and the network transport, so a message is encoded once
regardless of which path it travels over.

- Uses msgpack when available (compact, fast, no arbitrary code exec).
- Falls back to pickle if msgpack isn't installed.
- `frame()` prefixes a 4-byte big-endian length so stream-oriented
  consumers (ring buffer, TCP fallback) can split messages without
  needing a delimiter that might collide with binary payloads.
"""

import struct
import pickle

try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False


class Serializer:
    def __init__(self, use_msgpack: bool = True):
        self.use_msgpack = use_msgpack and HAS_MSGPACK
        if use_msgpack and not HAS_MSGPACK:
            import warnings
            warnings.warn("msgpack not installed, falling back to pickle "
                           "(pip install msgpack for smaller/faster frames)")

    def dumps(self, obj) -> bytes:
        if self.use_msgpack:
            return msgpack.packb(obj, use_bin_type=True)
        return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)

    def loads(self, data: bytes):
        if self.use_msgpack:
            return msgpack.unpackb(data, raw=False)
        return pickle.loads(data)

    def frame(self, obj) -> bytes:
        payload = self.dumps(obj)
        return struct.pack("!I", len(payload)) + payload

    @staticmethod
    def unframe_len(header4: bytes) -> int:
        return struct.unpack("!I", header4)[0]
