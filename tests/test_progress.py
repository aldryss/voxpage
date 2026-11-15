import pytest

from voxpage.progress import Cancelled, CancelToken


def test_cancel_token():
    t = CancelToken()
    assert not t.cancelled
    t.raise_if_cancelled()
    t.cancel()
    assert t.cancelled
    with pytest.raises(Cancelled):
        t.raise_if_cancelled()
