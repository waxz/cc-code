"""tests/test_node.py"""
import asyncio
import sys
import os
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import discovery
from node import Node


def uniq(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def reg_name():
    """Give each test its own discovery table so tests never see each
    other's nodes (tests run fast enough that TTL-based expiry alone
    wouldn't reliably separate them)."""
    name = f"/commsys_test_{uuid.uuid4().hex[:10]}"
    yield name
    try:
        from multiprocessing import shared_memory
        shared_memory.SharedMemory(name=name).unlink()
    except FileNotFoundError:
        pass


async def settle(seconds=0.9):
    await asyncio.sleep(seconds)


@pytest.mark.asyncio
async def test_shm_pubsub_basic(reg_name):
    received = []
    pub = Node(uniq("pub"), force_transport="shm", registry_name=reg_name)
    sub = Node(uniq("sub"), force_transport="shm", registry_name=reg_name)
    await pub.start()
    await sub.start()
    try:
        pub.advertise("t")
        sub.subscribe("t", received.append)
        await settle()
        for i in range(10):
            await pub.publish("t", f"m{i}".encode())
        await asyncio.sleep(0.3)
        assert received == [f"m{i}".encode() for i in range(10)]
    finally:
        await pub.stop()
        await sub.stop()


@pytest.mark.asyncio
async def test_udp_pubsub_basic(reg_name):
    received = []
    pub = Node(uniq("pub"), force_transport="udp", registry_name=reg_name)
    sub = Node(uniq("sub"), force_transport="udp", registry_name=reg_name)
    await pub.start()
    await sub.start()
    try:
        pub.advertise("t")
        sub.subscribe("t", received.append)
        await settle()
        for i in range(10):
            await pub.publish("t", f"m{i}".encode())
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.3)
        assert received == [f"m{i}".encode() for i in range(10)]
    finally:
        await pub.stop()
        await sub.stop()


@pytest.mark.asyncio
async def test_fan_out_one_publisher_many_subscribers(reg_name):
    recv_a, recv_b = [], []
    pub = Node(uniq("pub"), force_transport="shm", registry_name=reg_name)
    sub_a = Node(uniq("sub_a"), force_transport="shm", registry_name=reg_name)
    sub_b = Node(uniq("sub_b"), force_transport="udp", registry_name=reg_name)
    for n in (pub, sub_a, sub_b):
        await n.start()
    try:
        pub.advertise("fanout")
        sub_a.subscribe("fanout", recv_a.append)
        sub_b.subscribe("fanout", recv_b.append)
        await settle()
        for i in range(8):
            await pub.publish("fanout", f"m{i}".encode())
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.3)
        expected = [f"m{i}".encode() for i in range(8)]
        assert recv_a == expected
        assert recv_b == expected
    finally:
        for n in (pub, sub_a, sub_b):
            await n.stop()


@pytest.mark.asyncio
async def test_fan_in_many_publishers_one_subscriber(reg_name):
    received = []
    pub1 = Node(uniq("pub1"), force_transport="shm", registry_name=reg_name)
    pub2 = Node(uniq("pub2"), force_transport="shm", registry_name=reg_name)
    sub = Node(uniq("sub"), force_transport="shm", registry_name=reg_name)
    for n in (pub1, pub2, sub):
        await n.start()
    try:
        pub1.advertise("merged")
        pub2.advertise("merged")
        sub.subscribe("merged", lambda p: received.append(p))
        await settle()
        for i in range(5):
            await pub1.publish("merged", f"a{i}".encode())
            await pub2.publish("merged", f"b{i}".encode())
        await asyncio.sleep(0.3)
        assert sorted(received) == sorted(
            [f"a{i}".encode() for i in range(5)] + [f"b{i}".encode() for i in range(5)])
    finally:
        for n in (pub1, pub2, sub):
            await n.stop()


@pytest.mark.asyncio
async def test_subscriber_started_before_publisher_still_connects(reg_name):
    """Discovery should work regardless of startup order."""
    received = []
    sub = Node(uniq("sub"), force_transport="shm", registry_name=reg_name)
    await sub.start()
    sub.subscribe("late", received.append)
    await asyncio.sleep(0.3)  # subscriber running with no publisher yet

    pub = Node(uniq("pub"), force_transport="shm", registry_name=reg_name)
    await pub.start()
    pub.advertise("late")
    try:
        await settle()
        await pub.publish("late", b"hi")
        await asyncio.sleep(0.3)
        assert received == [b"hi"]
    finally:
        await pub.stop()
        await sub.stop()


@pytest.mark.asyncio
async def test_no_cross_talk_between_unrelated_topics(reg_name):
    recv_x, recv_y = [], []
    pub = Node(uniq("pub"), force_transport="shm", registry_name=reg_name)
    sub = Node(uniq("sub"), force_transport="shm", registry_name=reg_name)
    await pub.start()
    await sub.start()
    try:
        pub.advertise("x")
        pub.advertise("y")
        sub.subscribe("x", recv_x.append)
        sub.subscribe("y", recv_y.append)
        await settle()
        await pub.publish("x", b"only-x")
        await pub.publish("y", b"only-y")
        await asyncio.sleep(0.3)
        assert recv_x == [b"only-x"]
        assert recv_y == [b"only-y"]
    finally:
        await pub.stop()
        await sub.stop()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
