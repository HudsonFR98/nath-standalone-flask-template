from flask import Flask, render_template, request, session
from flask_login import LoginManager
from flask_babel import Babel, gettext as _

from nath_standalone_flask_template.lib import config
from nath_standalone_flask_template.lib import flask_util
from nath_standalone_flask_template.lib import database
from nath_standalone_flask_template.lib.telegram import send_error_notification_telegram
from nath_standalone_flask_template.lib import version
from nath_standalone_flask_template.models import User

from .blueprints.auth import auth
from .blueprints.dashboard import dashboard
from .blueprints.doc import doc
from .blueprints.coverage import coverage
from .blueprints.tests import test_output
from .blueprints.i18n import i18n
from .blueprints.admin import admin
from .blueprints.rest import rest


def create_app():

    app = Flask(__name__)
    app.config.from_object(config)
    
    def get_locale():
        """Get the locale for the current request"""
        # Check if user has set a language preference
        if 'language' in session:
            return session['language']
        # Otherwise, try to guess the language from the user accept
        # header the browser transmits. The best match wins.
        return request.accept_languages.best_match(config.LANGUAGES.keys())
    
    # Initialize Flask-Babel with locale selector
    babel = Babel(app, locale_selector=get_locale)
    
    # Session configuration is now handled in the config file
    # The app.config.from_object(config) above loads all the session settings
    
    database.open(config.SQLALCHEMY_DATABASE_URI)

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        return User.query.get(int(user_id))

    # Create admin user if no users exist
    User.create_admin_if_not_exists()

    # Initialize task scheduler
    from nath_standalone_flask_template.lib.task_scheduler import task_scheduler
    
    # Start the task scheduler only in the main process
    # In development mode with reloader, this prevents duplicate schedulers
    # In production environments (test, demo, prod), always start the scheduler
    import os
    if config.CONTEXT == 'dev':
        # In dev mode, only start if not in reloader process
        if not os.environ.get('WERKZEUG_RUN_MAIN'):
            task_scheduler.start()
    else:
        # In production environments, always start the scheduler
        task_scheduler.start()

    # Register error handlers for common HTTP errors
    # In development mode, let Flask handle errors natively for better debugging
    if config.CONTEXT != 'dev':
        @app.errorhandler(404)
        def page_not_found(e):
            return render_template('error.html',
                                  error_code=404,
                                  error_name='Page Not Found',
                                  error_description='The requested page could not be found.'), 404

        @app.errorhandler(403)
        def forbidden(e):
            return render_template('error.html',
                                  error_code=403,
                                  error_name='Forbidden',
                                  error_description='You do not have permission to access this resource.'), 403

        @app.errorhandler(400)
        def bad_request(e):
            return render_template('error.html',
                                  error_code=400,
                                  error_name='Bad Request',
                                  error_description='The server could not understand the request.'), 400

        @app.errorhandler(500)
        def internal_server_error(e):
            app.logger.error(f"Internal server error: {str(e)}")
            
            # Send error notification via Telegram
            try:
                # Collect request information
                request_info = {
                    'URL': request.url if request else 'Unknown',
                    'Method': request.method if request else 'Unknown',
                    'Remote Address': request.remote_addr if request else 'Unknown',
                    'User Agent': request.headers.get('User-Agent', 'Unknown') if request else 'Unknown',
                    'Referrer': request.headers.get('Referer', 'None') if request else 'None'
                }
                
                # Collect context information
                context_info = {
                    'Environment': config.CONTEXT,
                    'Database URI': config.SQLALCHEMY_DATABASE_URI.split('@')[1] if '@' in config.SQLALCHEMY_DATABASE_URI else 'Unknown',
                    'Debug Mode': getattr(config, 'DEBUG', False),
                    'Testing Mode': getattr(config, 'TESTING', False)
                }
                
                # Build details
                details = {
                    **request_info,
                    **context_info,
                    'Exception Type': type(e).__name__,
                    'Exception Message': str(e)
                }
                send_error_notification_telegram(
                    title="Internal Server Error",
                    details=details
                )
                
            except Exception as email_error:
                # Log email sending failure but don't let it break the error handling
                app.logger.error(f"Failed to send error notification email: {email_error}")

            if config.CONTEXT == 'prod':
                # In production, don't show traceback to users
                return render_template('error.html', 
                                      error_code=500,
                                      error_name='Internal Server Error',
                                      error_description='An unexpected error occurred. The administrator has been notified.'), 500
            else:
                # In development, show detailed error information
                import traceback
                return render_template('error.html', 
                                      error_code=500,
                                      error_name='Internal Server Error',
                                      error_description=str(e),
                                      traceback=traceback.format_exc()), 500

        @app.errorhandler(Exception)
        def unhandled_exception(e):
            app.logger.error(f"Unhandled exception: {str(e)}")
            
            # Send error notification via Telegram
            try:
                # Collect request information
                request_info = {
                    'URL': request.url if request else 'Unknown',
                    'Method': request.method if request else 'Unknown',
                    'Remote Address': request.remote_addr if request else 'Unknown',
                    'User Agent': request.headers.get('User-Agent', 'Unknown') if request else 'Unknown',
                    'Referrer': request.headers.get('Referer', 'None') if request else 'None'
                }
                
                # Collect context information
                context_info = {
                    'Environment': config.CONTEXT,
                    'Database URI': config.SQLALCHEMY_DATABASE_URI.split('@')[1] if '@' in config.SQLALCHEMY_DATABASE_URI else 'Unknown',
                    'Debug Mode': getattr(config, 'DEBUG', False),
                    'Testing Mode': getattr(config, 'TESTING', False)
                }
                
                details = {
                    **request_info,
                    **context_info,
                    'Exception Type': type(e).__name__,
                    'Exception Message': str(e)
                }
                send_error_notification_telegram(
                    title="Unhandled Exception",
                    details=details
                )
                
            except Exception as email_error:
                # Log email sending failure but don't let it break the error handling
                app.logger.error(f"Failed to send error notification email: {email_error}")

            if config.CONTEXT == 'prod':
                # In production, don't show traceback to users
                return render_template('error.html', 
                                      error_code=500,
                                      error_name='Internal Server Error',
                                      error_description='An unexpected error occurred. The administrator has been notified.'), 500
            else:
                # In development, show detailed error information
                import traceback
                return render_template('error.html', 
                                      error_code=500,
                                      error_name='Internal Server Error',
                                      error_description=str(e),
                                      traceback=traceback.format_exc()), 500

    @app.before_request
    def before_request():
        return flask_util.before_request()

    @app.after_request
    def after_request(response):
        flask_util.after_request()
        return response

    @app.context_processor
    def inject_ui():
        return dict(CONTEXT=config.CONTEXT, VERSION=version.get_version(), get_locale=get_locale, _=_)

    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(doc, url_prefix='/doc/')
    app.register_blueprint(i18n, url_prefix='/i18n/')
    app.register_blueprint(admin, url_prefix='/admin/')
    app.register_blueprint(rest, url_prefix='/rest')
    # Register coverage blueprint only in integration and local dev
    if config.CONTEXT in ['integration', 'dev']:
        app.register_blueprint(coverage, url_prefix='/coverage/')
    app.register_blueprint(test_output, url_prefix='/tests/')

    return app
