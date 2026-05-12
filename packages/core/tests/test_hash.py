from promptwall.proxy import _hash_payload


def test_hash_is_deterministic():
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}
    assert _hash_payload(payload) == _hash_payload(payload)


def test_hash_is_full_sha256_hex():
    digest = _hash_payload({"model": "gpt-4o-mini"})
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_hash_differs_for_different_payloads():
    assert _hash_payload({"model": "gpt-4o"}) != _hash_payload({"model": "gpt-4o-mini"})


def test_hash_is_key_order_independent():
    assert _hash_payload({"a": 1, "b": 2}) == _hash_payload({"b": 2, "a": 1})
