"""
tests/test_scheduler.py — Tests for app/scheduler.py.
"""
import app.scheduler as scheduler


class TestInitScheduler:

    def test_not_started_under_testing(self, app):
        assert app.testing
        assert scheduler._scheduler is None

    def test_init_is_noop_under_testing(self, app):
        scheduler.init_scheduler()
        assert scheduler._scheduler is None
