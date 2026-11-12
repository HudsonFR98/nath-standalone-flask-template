import logging
import os
from flask import Blueprint, render_template, abort, jsonify
from nath_standalone_flask_template.lib import config
from nath_standalone_flask_template.lib.flask_util import login_required
from nath_standalone_flask_template.lib.telegram import send_telegram_message

test_output = Blueprint('test_output', __name__)
log = logging.getLogger(__name__)


@test_output.route('/simple')
def simple():
    raise Exception('Test exception')
    return jsonify({'message': 'Hello, World!'})

@test_output.route('/telegram')
def telegram():
    send_telegram_message('Hello, World!')
    return jsonify({'message': 'Telegram message sent'})


@test_output.route('/output')
@login_required
def output():
    """
    Display the last test run output with detailed results.
    
    This route shows the results of the most recent test run, including:
    - Number of tests passed/failed
    - Test execution time
    - Warnings and errors
    - Coverage information
    
    The test output is only available in test context for security reasons.
    
    Returns:
        HTML page with test output or 404 if not in test context
    """
    # Only allow access in test context
    if config.CONTEXT not in ['integration', 'dev']:
        abort(404)
    
    # Try to read the last test output from various possible locations
    test_output = get_last_test_output()
    
    if not test_output:
        # If no test output found, show a message
        return render_template('tests/output.html', 
                              test_output="No test output found. Run tests first.",
                              has_output=False)
    
    return render_template('tests/output.html', 
                          test_output=test_output,
                          has_output=True)


def get_last_test_output():
    """
    Retrieve the last test run output from various possible locations.
    
    This function checks multiple locations where test output might be stored
    and returns the most recent test output found.
    
    Returns:
        str: The test output text, or None if no output found
    """
    # Possible locations for test output
    possible_locations = [
        '/opt/nath_standalone_flask_template_data/test_output.log',
        '/tmp/test_output.log',
        '/var/log/nath_standalone_flask_template/test_output.log'
    ]
    
    for location in possible_locations:
        if os.path.exists(location):
            try:
                with open(location, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                log.warning(f"Could not read test output from {location}: {e}")
    
    return None 