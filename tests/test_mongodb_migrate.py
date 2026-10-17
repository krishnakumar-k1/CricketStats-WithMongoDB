import sqlite3

from cricketstats.mongodb_migrate import maybe_decode_json, sqlite_tables


def test_maybe_decode_json():
    assert maybe_decode_json('["a", 2]', True) == ["a", 2]
    assert maybe_decode_json('{"x": 1}', True) == {"x": 1}
    assert maybe_decode_json('not json', True) == 'not json'
    assert maybe_decode_json('[1]', False) == '[1]'


def test_sqlite_tables_excludes_internal_tables():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE matches (match_id TEXT)")
    assert sqlite_tables(conn) == ["matches"]
