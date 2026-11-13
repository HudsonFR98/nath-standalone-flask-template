import logging

from flask import redirect, url_for, request, Blueprint, render_template, abort
from flask import make_response, g, flash
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _

from nath_standalone_flask_template import dao
from nath_standalone_flask_template.lib import config
from nath_standalone_flask_template.lib.validation_guest import ValidationGuestReviewer
from nath_standalone_flask_template.models import User

auth = Blueprint('auth', __name__)
log = logging.getLogger(__name__)


@auth.route('/', methods=['GET', 'POST'])
@auth.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    # Redirect if user is already logged in
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        try:
            user = User.authenticate(request.form['USR'], request.form['PWD'])
            if user and user.is_active():
                ValidationGuestReviewer.clear_declined()
                login_user(user, remember=True)
                log.debug(f"User logged in successfully: {user.ide}")
                response = make_response(redirect(url_for("dashboard.home")))
                response.set_cookie('nath_signature', value='signed !!')
                return response
            else:
                flash(_('User account is inactive'), 'error')
        except Exception as e:
            log.warning(f"Authentication failed: {e}")
            if config.CONTEXT == 'dev':
                flash(str(e), 'error')
            else:
                flash(_('Invalid username or password'), 'error')

    return render_template(
        'login.html',
        validation_reviewer_guest_login=ValidationGuestReviewer.active(),
    )


@auth.route('/login/reviewer', methods=['POST'])
def login_reviewer_guest():
    """Passwordless reviewer session (validation only, when enabled by admin)."""
    if config.CONTEXT != 'validation' or not ValidationGuestReviewer.active():
        abort(404)
    user = ValidationGuestReviewer.login_reviewer()
    if user is None:
        flash(_('Reviewer account is not available.'), 'error')
        return redirect(url_for('auth.login'))
    response = make_response(redirect(url_for('dashboard.home')))
    response.set_cookie('nath_signature', value='signed !!')
    return response


@auth.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    if ValidationGuestReviewer.active():
        ValidationGuestReviewer.mark_declined()
    logout_user()
    flash(_('Please sign in again'), 'message')
    response = make_response(redirect(url_for('.login')))
    response.delete_cookie('nath_signature')
    return response


@auth.route('/test-session')
@login_required
def test_session():
    """Test route to verify session functionality"""
    log.debug(f"Test session route - Current user: {current_user.ide if current_user else 'None'}")
    
    if current_user.is_authenticated:
        return f"Session working! User: {current_user.ide}, User ID: {current_user.id}"
    else:
        return "No user in session"
