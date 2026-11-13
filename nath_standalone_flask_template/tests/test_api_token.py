import pytest
from nath_standalone_flask_template import create_app, dao
from nath_standalone_flask_template.lib import config, database
from nath_standalone_flask_template.lib.api_token import ApiToken
from nath_standalone_flask_template.lib.exc import DomainError
from nath_standalone_flask_template.models.user import User
from nath_standalone_flask_template.tests.util import login


@pytest.fixture
def app():
    application = create_app()
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


def _delete_user(ide):
    user = User.query.filter_by(ide=ide).first()
    if user is None:
        return
    user.roles.clear()
    database.DBSession.delete(user)
    database.DBSession.commit()


def test_generated_token_is_stored_hashed(app):
    try:
        user = User(ide='apitokenuser', pwd='secret', first_name='Api', last_name='Token')
        database.DBSession.add(user)
        database.DBSession.commit()
        result = dao.generate_api_token(user.id)
        database.DBSession.refresh(user)
        assert result['token'].startswith('nst_')
        assert user.api_token_hash == ApiToken(result['token']).digest()
        assert result['token'] not in (user.api_token_hash or '')
        assert user.has_api_token()
    finally:
        _delete_user('apitokenuser')


def test_rest_test_requires_token(app):
    with app.test_client() as client:
        response = client.get('/rest/test')
        assert response.status_code == 401


def test_rest_test_accepts_bearer_token(app):
    try:
        user = User(ide='apitokenuser', pwd='secret', first_name='Api', last_name='Token')
        database.DBSession.add(user)
        database.DBSession.commit()
        result = dao.generate_api_token(user.id)
        with app.test_client() as client:
            response = client.get(
                '/rest/test',
                headers={'Authorization': 'Bearer ' + result['token']},
            )
            assert response.status_code == 200
            payload = response.get_json()
            assert payload['ok'] is True
            assert payload['user'] == 'apitokenuser'
            assert payload['user_id'] == user.id
    finally:
        _delete_user('apitokenuser')


def test_rest_test_accepts_x_api_token_header(app):
    try:
        user = User(ide='apitokenuser', pwd='secret')
        database.DBSession.add(user)
        database.DBSession.commit()
        result = dao.generate_api_token(user.id)
        with app.test_client() as client:
            response = client.get(
                '/rest/test',
                headers={'X-API-Token': result['token']},
            )
            assert response.status_code == 200
            assert response.get_json()['user'] == 'apitokenuser'
    finally:
        _delete_user('apitokenuser')


def test_revoked_token_is_rejected(app):
    try:
        user = User(ide='apitokenuser', pwd='secret')
        database.DBSession.add(user)
        database.DBSession.commit()
        result = dao.generate_api_token(user.id)
        dao.revoke_api_token(user.id)
        with app.test_client() as client:
            response = client.get(
                '/rest/test',
                headers={'Authorization': 'Bearer ' + result['token']},
            )
            assert response.status_code == 401
    finally:
        _delete_user('apitokenuser')


def test_inactive_user_token_is_rejected(app):
    try:
        user = User(ide='apitokenuser', pwd='secret', active=True)
        database.DBSession.add(user)
        database.DBSession.commit()
        result = dao.generate_api_token(user.id)
        user.active = False
        database.DBSession.commit()
        with app.test_client() as client:
            response = client.get(
                '/rest/test',
                headers={'Authorization': 'Bearer ' + result['token']},
            )
            assert response.status_code == 401
    finally:
        _delete_user('apitokenuser')


def test_replaced_token_invalidates_previous(app):
    try:
        user = User(ide='apitokenuser', pwd='secret')
        database.DBSession.add(user)
        database.DBSession.commit()
        first = dao.generate_api_token(user.id)
        second = dao.generate_api_token(user.id)
        assert first['token'] != second['token']
        with app.test_client() as client:
            stale = client.get(
                '/rest/test',
                headers={'Authorization': 'Bearer ' + first['token']},
            )
            fresh = client.get(
                '/rest/test',
                headers={'Authorization': 'Bearer ' + second['token']},
            )
            assert stale.status_code == 401
            assert fresh.status_code == 200
    finally:
        _delete_user('apitokenuser')


def test_revoke_without_token_raises(app):
    try:
        user = User(ide='apitokenuser', pwd='secret')
        database.DBSession.add(user)
        database.DBSession.commit()
        with pytest.raises(DomainError):
            dao.revoke_api_token(user.id)
    finally:
        _delete_user('apitokenuser')


def test_admin_can_generate_token_via_http(app):
    try:
        user = User(ide='apitokenuser', pwd='secret')
        database.DBSession.add(user)
        database.DBSession.commit()
        user_id = user.id
        with app.test_client() as client:
            login(client, config.ADMIN_USER_USERNAME, config.ADMIN_USER_PASSWORD)
            response = client.post('/admin/api/user/%s/token' % user_id)
            assert response.status_code == 200
            payload = response.get_json()
            assert payload['success'] is True
            assert payload['token'].startswith('nst_')
        assert dao.get_user_by_api_token(payload['token']).id == user_id
    finally:
        _delete_user('apitokenuser')


def test_non_admin_cannot_generate_token(app):
    try:
        user = User(ide='apitokenuser', pwd='secret')
        database.DBSession.add(user)
        database.DBSession.commit()
        user_id = user.id
        with app.test_client() as client:
            login(client, 'apitokenuser', 'secret')
            response = client.post('/admin/api/user/%s/token' % user_id)
            assert response.status_code == 403
    finally:
        _delete_user('apitokenuser')
