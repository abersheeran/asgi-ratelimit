from ratelimit.__version__ import VERSION


def test_version():
    assert all(map(lambda v: isinstance(v, int), VERSION))
