"""tests/test_serialization.py"""
import sys
import os
import struct

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from serialization import Serializer


@pytest.mark.parametrize("use_msgpack", [True, False])
class TestSerializer:
    def test_roundtrip_dict(self, use_msgpack):
        s = Serializer(use_msgpack=use_msgpack)
        obj = {"a": 1, "b": [1, 2, 3], "c": "text"}
        assert s.loads(s.dumps(obj)) == obj

    def test_roundtrip_nested(self, use_msgpack):
        s = Serializer(use_msgpack=use_msgpack)
        obj = {"x": {"y": {"z": [1, 2, {"w": 3.5}]}}}
        assert s.loads(s.dumps(obj)) == obj

    def test_frame_length_prefix_correct(self, use_msgpack):
        s = Serializer(use_msgpack=use_msgpack)
        obj = {"payload": "x" * 500}
        framed = s.frame(obj)
        length = struct.unpack("!I", framed[:4])[0]
        assert length == len(framed) - 4
        assert s.loads(framed[4:]) == obj

    def test_empty_and_none(self, use_msgpack):
        s = Serializer(use_msgpack=use_msgpack)
        assert s.loads(s.dumps(None)) is None
        assert s.loads(s.dumps({})) == {}
        assert s.loads(s.dumps([])) == []

    def test_binary_bytes_survive_roundtrip(self, use_msgpack):
        s = Serializer(use_msgpack=use_msgpack)
        obj = {"raw": bytes(range(256))}
        result = s.loads(s.dumps(obj))
        assert result["raw"] == obj["raw"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
