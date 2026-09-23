import sqlite3

from sf_express_mcp.order_map import OrderMap, RETENTION_SECONDS


def test_mapping_persists_for_24_hours_and_is_removed_at_expiry(tmp_path):
    path = tmp_path / "order-map.sqlite3"
    OrderMap(path).save("sandbox", "partner", "ORDER-1", ["SF-1", "SF-2"], now=1000)

    reopened = OrderMap(path)
    assert reopened.lookup("sandbox", "partner", "SF-1", now=1000 + RETENTION_SECONDS - 1) == "ORDER-1"
    assert reopened.lookup("sandbox", "partner", "SF-2", now=1000 + RETENTION_SECONDS) is None
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM order_map").fetchone()[0] == 0


def test_mapping_is_scoped_to_environment_and_partner(tmp_path):
    store = OrderMap(tmp_path / "order-map.sqlite3")
    store.save("sandbox", "partner-a", "ORDER-A", ["SF-1"], now=1000)
    assert store.lookup("sandbox", "partner-b", "SF-1", now=1001) is None
    assert store.lookup("production", "partner-a", "SF-1", now=1001) is None
    assert store.lookup("sandbox", "partner-a", "SF-1", now=1001) == "ORDER-A"
