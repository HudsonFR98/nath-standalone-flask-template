import pytest
from nath_standalone_flask_template import create_app, dao
from nath_standalone_flask_template.lib import config
from nath_standalone_flask_template.lib.const import CONTEXT_VALIDATION
from nath_standalone_flask_template.models.setting import AppSetting
from nath_standalone_flask_template.tests.util import login


@pytest.fixture
def app():
    application = create_app()
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


@pytest.fixture
def validation_guest_enabled(app, monkeypatch):
    """Validation deploys do not run pytest; force validation context in tests."""
    monkeypatch.setattr(config, 'CONTEXT', CONTEXT_VALIDATION)
    dao.set_validation_reviewer_guest_login(True)
    yield
    record = AppSetting.query.get(dao.VALIDATION_REVIEWER_GUEST_LOGIN)
    if record is not None:
        from nath_standalone_flask_template.lib import database
        database.DBSession.delete(record)
        database.DBSession.commit()


def test_guest_reviewer_post_logs_in(app, validation_guest_enabled):
    with app.test_client() as client:
        response = client.post('/login/reviewer', follow_redirects=False)
        assert response.status_code in (302, 303)
        with client.session_transaction() as sess:
            assert not sess.get('validation_reviewer_declined')
        home = client.get('/home')
        assert home.status_code == 200


def test_logout_blocks_auto_reviewer_until_guest_button(app, validation_guest_enabled):
    with app.test_client() as client:
        client.post('/login/reviewer', follow_redirects=True)
        client.get('/logout', follow_redirects=True)
        with client.session_transaction() as sess:
            assert sess.get('validation_reviewer_declined')
        login_page = client.get('/login')
        assert login_page.status_code == 200
        assert b'Connect as reviewer' in login_page.data or 'reviewer' in login_page.get_data(as_text=True)


def test_admin_can_toggle_guest_setting(app, validation_guest_enabled):
    with app.test_client() as client:
        # Guest auto-login runs in before_request; block it so admin credentials apply.
        with client.session_transaction() as sess:
            sess['validation_reviewer_declined'] = True
        login(client, config.ADMIN_USER_USERNAME, config.ADMIN_USER_PASSWORD)
        client.post(
            '/admin/settings/validation-reviewer-guest',
            data={'enabled': ''},
            follow_redirects=True,
        )
        assert not dao.is_validation_reviewer_guest_login_enabled()
