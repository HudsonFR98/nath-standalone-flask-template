import pytest
from nath_standalone_flask_template import create_app, dao
from nath_standalone_flask_template.lib import config, database
from nath_standalone_flask_template.lib.exc import DomainError
from nath_standalone_flask_template.models.user import Permission, Role, User
from nath_standalone_flask_template.tests.util import login


@pytest.fixture
def app():
    application = create_app()
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


def _permission_ids(*names):
    ids = []
    for name in names:
        permission = Permission.query.filter_by(name=name).first()
        assert permission is not None, f"missing default permission {name}"
        ids.append(permission.id)
    return ids


def _delete_role(name):
    role = Role.query.filter_by(name=name).first()
    if role is None:
        return
    role.granted_permissions.clear()
    role.users.clear()
    database.DBSession.delete(role)
    database.DBSession.commit()


def _delete_permission(name):
    permission = Permission.query.filter_by(name=name).first()
    if permission is None:
        return
    permission.roles.clear()
    database.DBSession.delete(permission)
    database.DBSession.commit()


def _delete_user(ide):
    user = User.query.filter_by(ide=ide).first()
    if user is None:
        return
    user.roles.clear()
    database.DBSession.delete(user)
    database.DBSession.commit()


def test_admin_bootstrap_keeps_admin_permission(app):
    admin_user = User.query.get(1)
    assert admin_user is not None
    admin_user.reload_permissions()
    assert admin_user.has_permission('admin')
    admin_role = Role.query.filter_by(name='admin').first()
    assert admin_role is not None
    assert 'admin' in admin_role.get_permissions()


def test_bootstrap_creates_reviewer_from_config(app):
    from nath_standalone_flask_template.lib._config import reviewer_bootstrap_configured

    if not reviewer_bootstrap_configured():
        pytest.skip('REVIEWER_USER_USERNAME and REVIEWER_USER_PASSWORD not set')
    user = User.query.filter_by(ide=config.REVIEWER_USER_USERNAME).first()
    assert user is not None
    user.reload_permissions()
    assert user.has_role('reviewer')
    assert not user.has_permission('admin')
    assert user.first_name == config.REVIEWER_USER_FIRST_NAME
    assert user.last_name == config.REVIEWER_USER_LAST_NAME
    assert user.email == config.REVIEWER_USER_EMAIL


def test_permission_union_across_roles(app):
    try:
        read_id, write_id = _permission_ids('read', 'write')
        readers = dao.create_role('test_readers', 'Readers', [read_id])
        writers = dao.create_role('test_writers', 'Writers', [write_id])
        user = User(ide='permunion', pwd='secret', first_name='P', last_name='U')
        user.add_role(readers)
        user.add_role(writers)
        database.DBSession.add(user)
        database.DBSession.commit()
        user.reload_permissions()
        assert user.has_permission('read')
        assert user.has_permission('write')
        assert not user.has_permission('delete')
    finally:
        _delete_user('permunion')
        _delete_role('test_readers')
        _delete_role('test_writers')


def test_delete_role_blocked_when_assigned(app):
    try:
        role = dao.create_role('test_assigned', 'Assigned')
        user = User(ide='assignedrole', pwd='secret')
        user.add_role(role)
        database.DBSession.add(user)
        database.DBSession.commit()
        with pytest.raises(DomainError):
            dao.delete_role(role.id)
    finally:
        _delete_user('assignedrole')
        _delete_role('test_assigned')


def test_system_permission_cannot_be_deleted(app):
    admin_permission = Permission.query.filter_by(name='admin').first()
    assert admin_permission is not None
    with pytest.raises(DomainError):
        dao.delete_permission(admin_permission.id)


def test_permission_delete_blocked_when_assigned(app):
    try:
        permission = dao.create_permission('reports', 'Access reports')
        role = dao.create_role('test_reports', 'Reports', [permission.id])
        with pytest.raises(DomainError):
            dao.delete_permission(permission.id)
        assert Permission.query.filter_by(name='reports').first() is not None
    finally:
        _delete_role('test_reports')
        _delete_permission('reports')


def test_admin_role_cannot_be_deleted(app):
    admin_role = Role.query.filter_by(name='admin').first()
    assert admin_role is not None
    with pytest.raises(DomainError):
        dao.delete_role(admin_role.id)


def test_custom_permission_delete_when_unused(app):
    try:
        permission = dao.create_permission('reports', 'Access reports')
        dao.delete_permission(permission.id)
        assert Permission.query.filter_by(name='reports').first() is None
    finally:
        _delete_permission('reports')


def test_roles_page_forbidden_without_admin(app):
    try:
        user = User(ide='plainuser', pwd='secret', first_name='Plain', last_name='User')
        database.DBSession.add(user)
        database.DBSession.commit()
        with app.test_client() as client:
            login(client, 'plainuser', 'secret')
            response = client.get('/admin/roles')
            assert response.status_code == 403
    finally:
        _delete_user('plainuser')


def _make_reviewer(ide='revieweruser'):
    role = Role.query.filter_by(name='reviewer').first()
    assert role is not None
    user = User(ide=ide, pwd='secret', first_name='Rev', last_name='Iewer')
    user.add_role(role)
    database.DBSession.add(user)
    database.DBSession.commit()
    return user


def test_reviewer_role_has_no_admin_permission(app):
    role = Role.query.filter_by(name='reviewer').first()
    assert role is not None
    names = role.get_permissions()
    assert 'read' in names
    assert 'write' in names
    assert 'delete' in names
    assert 'admin' not in names


def test_reviewer_can_view_staff_pages(app):
    try:
        _make_reviewer()
        with app.test_client() as client:
            login(client, 'revieweruser', 'secret')
            assert client.get('/admin/users').status_code == 200
            assert client.get('/admin/roles').status_code == 200
            assert client.get('/admin/permissions').status_code == 200
            assert client.get('/admin/tasks').status_code == 200
    finally:
        _delete_user('revieweruser')


def test_reviewer_cannot_view_logs(app):
    try:
        _make_reviewer()
        with app.test_client() as client:
            login(client, 'revieweruser', 'secret')
            assert client.get('/admin/logs').status_code == 403
    finally:
        _delete_user('revieweruser')


def test_reviewer_cannot_mutate_users_roles_or_tokens(app):
    try:
        reviewer = _make_reviewer()
        with app.test_client() as client:
            login(client, 'revieweruser', 'secret')
            assert client.post(
                '/admin/create_user',
                data={'username': 'blocked', 'password': 'x'},
                follow_redirects=False,
            ).status_code == 403
            assert client.post(
                '/admin/roles/create',
                data={'name': 'blocked_role'},
                follow_redirects=False,
            ).status_code == 403
            assert client.post(
                '/admin/permissions/create',
                data={'name': 'blocked_perm'},
                follow_redirects=False,
            ).status_code == 403
            assert client.post(
                '/admin/api/user/%s/token' % reviewer.id,
            ).status_code == 403
    finally:
        _delete_user('revieweruser')
        _delete_user('blocked')
        _delete_role('blocked_role')
        _delete_permission('blocked_perm')


def test_admin_can_create_role_via_http(app):
    try:
        read_id = _permission_ids('read')[0]
        with app.test_client() as client:
            login(client, config.ADMIN_USER_USERNAME, config.ADMIN_USER_PASSWORD)
            response = client.post(
                '/admin/roles/create',
                data={
                    'name': 'test_http_role',
                    'description': 'HTTP role',
                    'permissions': [str(read_id)],
                },
                follow_redirects=True,
            )
            assert response.status_code == 200
        role = Role.query.filter_by(name='test_http_role').first()
        assert role is not None
        assert 'read' in role.get_permissions()
    finally:
        _delete_role('test_http_role')
