import pytest
from sqlalchemy import text
from nath_standalone_flask_template.lib import database, config
from nath_standalone_flask_template import create_app
from nath_standalone_flask_template.models import User


def test_database_connection():
    """
    Test that the application can successfully connect to the database.
    
    This is a fundamental test that verifies the database connection
    is working properly. It's essential because if the database connection
    fails, most other functionality in the application will not work.
    
    The test:
    1. Opens a database connection using the test configuration
    2. Executes a simple SQL query (SELECT 1) to verify connectivity
    3. Verifies the query returns the expected result
    4. Cleans up the database session
    
    This test should run first in the test suite as it's a prerequisite
    for other database-dependent tests.
    
    Assertions:
        - Database connection should be established successfully
        - Simple query should execute and return expected result (1)
    """
    try:
        # Step 1: Open database connection using test configuration
        database.open(config.SQLALCHEMY_DATABASE_URI)
        # Step 2: Execute a simple test query to verify connectivity
        result = database.DBSession.execute(text("SELECT 1"))
        # Step 3: Verify the query returned the expected result
        assert result.scalar() == 1
    finally:
        # Step 4: Clean up database session
        database.DBSession.remove()


def test_config_loading():
    """
    Test that the application configuration is loaded correctly for the test environment.
    
    This test verifies that the configuration system is working properly
    and that the test environment is configured correctly. It ensures
    that the application is running in test mode with the appropriate
    settings.
    
    The test checks:
    - The context is one of dev, integration, validation, prod
    - Testing mode is enabled
    - Database URI contains the expected test database name
    
    This test is important because incorrect configuration can cause
    tests to behave unexpectedly or connect to the wrong database.
    
    Assertions:
        - CONTEXT should be a known deployment context
        - TESTING flag should be True
        - Database URI should contain 'nsft' (test database)
    """
    # Verify test context is set correctly
    assert config.CONTEXT in ('integration', 'dev', 'validation', 'prod')
    # Verify testing mode is enabled
    assert 'nsft' in config.SQLALCHEMY_DATABASE_URI


def test_app_creation():
    """
    Test that the Flask application can be created successfully.
    
    This test verifies that the Flask application factory function
    works correctly and creates a properly configured application
    instance. This is a basic sanity check that the application
    can be instantiated without errors.
    
    The test:
    1. Calls the create_app() factory function
    2. Verifies an application object is returned
    
    This test is important because if the application can't be created,
    none of the web-based tests will work.
    
    Assertions:
        - Application should be created successfully (not None)
        - Application should have testing mode enabled
    """
    # Step 1: Create Flask application using factory function
    app = create_app()
    # Step 2: Verify application was created successfully
    assert app is not None

def test_user_model():
    """
    Test basic User model functionality including creation and validation.
    
    This test verifies that the User model works correctly for basic
    operations like user creation, password hashing, and string representation.
    It tests the model in isolation without involving the database.
    
    The test covers:
    - User object creation with basic attributes
    - Password hashing functionality (passwords should be hashed, not plain text)
    - String representation of user objects
    
    This test is important because the User model is central to the
    application's authentication system.
    
    Assertions:
        - User should be created with provided attributes
        - Password should be hashed (not plain text)
        - Password hash should be a Werkzeug hash (scrypt or pbkdf2)
        - String representation should show user's full name
    """
    try:
        # Step 1: Open database connection
        database.open(config.SQLALCHEMY_DATABASE_URI)
        
        # Step 2: Create a test user with basic attributes
        user = User(
            ide='testuser',
            pwd='testpass',
            first_name='Test',
            last_name='User',
            email='test@example.com'
        )
        
        # Step 3: Test password hashing functionality
        assert user.pwd != 'testpass'  # Password should be hashed, not plain text
        assert user.pwd.startswith('scrypt:') or user.pwd.startswith('pbkdf2:')
        
        # Step 4: Test string representation
        assert str(user) == 'Test User'
        
    finally:
        # Step 5: Clean up database session
        database.DBSession.remove()


def test_user_authentication():
    """
    Test the User model's authentication functionality end-to-end.
    
    This test verifies that the complete authentication flow works correctly:
    from user creation to password verification. It tests the authenticate
    method which is the core of the login functionality.
    
    The test covers:
    - Creating a user in the database
    - Successful authentication with correct credentials
    - Failed authentication with incorrect password
    - Proper cleanup of test data
    
    This test is crucial because authentication is a core feature of the
    application and must work reliably.
    
    Assertions:
        - User should be created successfully in database
        - Authentication should succeed with correct credentials
        - Authentication should fail with incorrect credentials
        - Test data should be cleaned up properly
    """
    try:
        # Step 1: Open database connection
        database.open(config.SQLALCHEMY_DATABASE_URI)
        
        # Step 2: Create a test user in the database
        user = User(
            ide='authuser',
            pwd='authpass',
            first_name='Auth',
            last_name='User'
        )
        database.DBSession.add(user)
        database.DBSession.commit()
        
        # Step 3: Test successful authentication
        authenticated_user = User.authenticate('authuser', 'authpass')
        assert authenticated_user is not None
        assert authenticated_user.ide == 'authuser'
        
        # Step 4: Test failed authentication (wrong password)
        with pytest.raises(Exception):
            User.authenticate('authuser', 'wrongpass')
            
    finally:
        # Step 5: Clean up test data
        database.DBSession.query(User).filter_by(ide='authuser').delete()
        database.DBSession.commit()
        database.DBSession.remove() 