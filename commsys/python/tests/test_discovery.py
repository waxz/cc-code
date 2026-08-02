"""tests/test_discovery.py"""
import sys
import os
import uuid
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from discovery import DiscoveryRegistry, REGISTRY_NAME


@pytest.fixture
def registry_name():
    # unique name per test so tests don't see each other's stale slots
    name = f"/commsys_test_{uuid.uuid4().hex[:10]}"
    yield name
    try:
        from multiprocessing import shared_memory
        shared_memory.SharedMemory(name=name).unlink()
    except FileNotFoundError:
        pass


class TestDiscoveryRegistry:
    def test_register_and_list(self, registry_name):
        r = DiscoveryRegistry(name=registry_name)
        slot = r.register("node_a", "127.0.0.1", 9001, {"imu"}, set())
        active = r.list_active()
        assert len(active) == 1
        assert active[0].node_id == "node_a"
        assert active[0].published == {"imu"}
        r.unregister(slot)
        r.close()

    def test_two_nodes_see_each_other(self, registry_name):
        r1 = DiscoveryRegistry(name=registry_name)
        r2 = DiscoveryRegistry(name=registry_name)
        s1 = r1.register("a", "127.0.0.1", 1, {"topic1"}, set())
        s2 = r2.register("b", "127.0.0.1", 2, set(), {"topic1"})

        seen_by_b = {n.node_id for n in r2.list_active()}
        seen_by_a = {n.node_id for n in r1.list_active()}
        assert seen_by_b == {"a", "b"}
        assert seen_by_a == {"a", "b"}

        r1.unregister(s1); r2.unregister(s2)
        r1.close(); r2.close()

    def test_exclude_slot_omits_self(self, registry_name):
        r = DiscoveryRegistry(name=registry_name)
        slot = r.register("self_node", "127.0.0.1", 1, set(), set())
        others = r.list_active(exclude_slot=slot)
        assert others == []
        r.unregister(slot)
        r.close()

    def test_stale_heartbeat_pruned_by_ttl(self, registry_name):
        r = DiscoveryRegistry(name=registry_name)
        slot = r.register("stale_node", "127.0.0.1", 1, {"t"}, set())
        # manually backdate the heartbeat to simulate a node that
        # stopped heartbeating without a clean unregister()
        r._table.slots[slot].last_heartbeat_ns = time.time_ns() - int(5 * 1e9)
        active = r.list_active(ttl_sec=1.0)
        assert active == []
        r.unregister(slot)
        r.close()

    def test_unregister_removes_from_active_list(self, registry_name):
        r = DiscoveryRegistry(name=registry_name)
        slot = r.register("temp_node", "127.0.0.1", 1, set(), set())
        assert len(r.list_active()) == 1
        r.unregister(slot)
        assert len(r.list_active()) == 0
        r.close()

    def test_heartbeat_updates_topics(self, registry_name):
        r = DiscoveryRegistry(name=registry_name)
        slot = r.register("evolving_node", "127.0.0.1", 1, {"a"}, set())
        r.heartbeat(slot, published={"a", "b"}, subscribed={"c"})
        active = r.list_active()
        assert active[0].published == {"a", "b"}
        assert active[0].subscribed == {"c"}
        r.unregister(slot)
        r.close()

    def test_transport_pref_roundtrip(self, registry_name):
        r = DiscoveryRegistry(name=registry_name)
        slot = r.register("pref_node", "127.0.0.1", 1, set(), set(), transport_pref=2)
        active = r.list_active()
        assert active[0].transport_pref == 2
        r.unregister(slot)
        r.close()

    def test_dead_process_pruned_via_pid_check(self, registry_name):
        import subprocess
        r = DiscoveryRegistry(name=registry_name)
        # register a slot claiming to belong to a pid that we know is dead
        proc = subprocess.Popen(["true"])
        proc.wait()
        dead_pid = proc.pid
        slot = r.register("ghost_node", "127.0.0.1", 1, {"t"}, set())
        r._table.slots[slot].pid = dead_pid
        active = r.list_active()
        assert active == []  # pruned because the owning pid is gone
        r.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
