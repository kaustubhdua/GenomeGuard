import base64
import warnings

from app.core import crypto
from app.core.crypto import DecryptionError, decrypt, encrypt

MASTER = bytes(range(32))


def raises(exc, fn, *a):
    try:
        fn(*a)
    except exc:
        return True
    return False


def test_roundtrip_and_blob_layout():
    blob = encrypt(MASTER, "ds1", 7, b"secret genotype bytes")
    assert blob != b"secret genotype bytes" and b"secret" not in blob
    assert len(blob) == 12 + len(b"secret genotype bytes") + 16
    assert decrypt(MASTER, "ds1", 7, blob) == b"secret genotype bytes"


def test_nonce_is_fresh_every_time():
    blobs = {encrypt(MASTER, "ds", 1, b"x")[:12] for _ in range(200)}
    assert len(blobs) == 200


def test_wrong_dataset_or_record_fails():
    blob = encrypt(MASTER, "ds1", 7, b"data")
    assert raises(DecryptionError, decrypt, MASTER, "ds2", 7, blob)  # other dataset key
    assert raises(DecryptionError, decrypt, MASTER, "ds1", 8, blob)  # blob moved to another donor


def test_wrong_master_key_fails():
    blob = encrypt(MASTER, "ds1", 7, b"data")
    assert raises(DecryptionError, decrypt, bytes(32), "ds1", 7, blob)


def test_any_single_bit_flip_is_detected():
    blob = encrypt(MASTER, "ds1", 7, b"integrity matters")
    for i in range(len(blob)):
        bad = bytearray(blob)
        bad[i] ^= 0x01
        assert raises(DecryptionError, decrypt, MASTER, "ds1", 7, bytes(bad)), i


def test_truncated_blob_rejected():
    assert raises(DecryptionError, decrypt, MASTER, "ds1", 7, b"short")


def test_dataset_keys_differ_and_are_256_bit():
    a, b = crypto.dataset_key(MASTER, "a"), crypto.dataset_key(MASTER, "b")
    assert a != b and len(a) == len(b) == 32
    assert crypto.dataset_key(MASTER, "a") == a  # deterministic derivation


def test_master_key_loading():
    k = crypto.new_master_key()
    assert len(base64.b64decode(k)) == 32 and crypto.load_master_key(k) == base64.b64decode(k)
    assert raises(ValueError, crypto.load_master_key, base64.b64encode(b"short").decode())
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        dev = crypto.load_master_key(None)
    assert len(dev) == 32 and any("INSECURE" in str(x.message) for x in w)
