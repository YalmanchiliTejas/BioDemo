"""Real client protocol checks against local test endpoints, not vendor qualification."""
import json
import socket
import socketserver
import struct
import threading
import time

import pytest

from src.lifesci.connectors import MqttSource, OpcUaSource
from src.lifesci.store import RecordStore


def test_mqtt_client_persists_before_ack_and_replays_cursor(monkeypatch):
    pytest.importorskip("paho.mqtt.client")
    monkeypatch.setenv("LIFESCI_CONNECTOR_ALLOWED_HOSTS", "127.0.0.1")
    acked = threading.Event()
    def packet(sock):
        head = sock.recv(1)
        if not head:
            return 0, b""
        size, multiplier = 0, 1
        while True:
            b = sock.recv(1)[0]; size += (b & 127) * multiplier
            if b < 128: break
            multiplier *= 128
        data = b""
        while len(data) < size: data += sock.recv(size - len(data))
        return head[0] >> 4, data
    def send(sock, head, body):
        size, encoded = len(body), bytearray()
        while True:
            digit, size = size % 128, size // 128
            encoded.append(digit | (128 if size else 0))
            if not size: break
        sock.sendall(bytes([head]) + encoded + body)
    class Broker(socketserver.BaseRequestHandler):
        def handle(self):
            sock = self.request; sock.settimeout(10)
            assert packet(sock)[0] == 1  # CONNECT
            send(sock, 0x20, b"\x00\x00")
            kind, sub = packet(sock); assert kind == 8
            send(sock, 0x90, sub[:2] + b"\x01")
            topic = b"plant/ph"
            raw = json.dumps({"id": "reading-1", "timestamp": "2026-10-24T00:00:00Z", "value": 7.1}).encode()
            send(sock, 0x32, struct.pack("!H", len(topic)) + topic + b"\x00\x07" + raw)
            kind, body = packet(sock)
            assert kind == 4 and body == b"\x00\x07"  # PUBACK
            acked.set()
            packet(sock)  # DISCONNECT
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Broker)
    t = threading.Thread(target=server.serve_forever, daemon=True); t.start()
    source = None
    try:
        store = RecordStore()
        source = MqttSource(store, "T", {"connector_id": "mqtt1", "family": "HISTORIAN", "site_id": "S1",
            "options": {"base_url": f"mqtt://127.0.0.1:{server.server_address[1]}", "addresses": ["plant/ph"]}})
        assert acked.wait(5)
        batch = source.pull(None)
        assert batch.records[0].payload["value"] == 7.1
        assert batch.records[0].payload["topic"] == "plant/ph"
        assert source.pull(batch.next_checkpoint).records == ()
        # Persisted queue remains replayable independently of network-client state.
        assert source.queue.read(0, 1)[0]["record"]["source_record_id"] == "reading-1"
    finally:
        if source: source.close()
        server.shutdown(); server.server_close(); t.join()


def test_opcua_encrypted_read_preserves_source_time_and_quality(monkeypatch, tmp_path):
    pytest.importorskip("asyncua")
    from asyncua import ua
    from asyncua.sync import Server
    from asyncua.crypto.cert_gen import generate_self_signed_app_certificate
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID
    monkeypatch.setenv("LIFESCI_CONNECTOR_ALLOWED_HOSTS", "127.0.0.1")
    def certificates(name, uri):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = generate_self_signed_app_certificate(key, name, {},
            [x509.UniformResourceIdentifier(uri), x509.DNSName("localhost")],
            [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH])
        cert_path, key_path = tmp_path / f"{name}.der", tmp_path / f"{name}.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.DER))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))
        return cert_path, key_path
    server_cert, server_key = certificates("server", "urn:freeopcua:python:server")
    client_cert, client_key = certificates("client", "urn:example.org:FreeOpcUa:opcua-asyncio")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    endpoint = f"opc.tcp://127.0.0.1:{port}/test"
    server = Server()
    server.set_endpoint(endpoint)
    server.load_certificate(server_cert); server.load_private_key(server_key)
    server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
    idx = server.register_namespace("urn:biodemo:test")
    node = server.nodes.objects.add_variable(idx, "pH", 7.1)
    monkeypatch.setenv("TEST_OPCUA_SECURITY", f"Basic256Sha256,SignAndEncrypt,{client_cert},{client_key},{server_cert}")
    server.start()
    try:
        source = OpcUaSource({"connector_id": "opc1", "family": "HISTORIAN", "site_id": "S1",
            "options": {"base_url": endpoint, "addresses": [node.nodeid.to_string()],
                        "security_string_env": "TEST_OPCUA_SECURITY"}})
        batch = source.pull(None)
        assert batch.records[0].payload["value"] == 7.1
        assert batch.records[0].payload["quality"] == "Good"
        assert batch.records[0].occurred_at.tzinfo is not None
        assert not hasattr(source, "write")
    finally:
        server.stop()
