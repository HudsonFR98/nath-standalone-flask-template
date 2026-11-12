import pytest
import logging
import os
from nath_standalone_flask_template.lib import database
from . import util
from nath_standalone_flask_template.lib import config


@pytest.fixture(scope="module", autouse=True)
def connect_db(request):
    """Open the application database for modules that need it.

    Modules that only check context names set ``NO_DB = True`` and skip this.
    """
    if getattr(request.module, "NO_DB", False):
        yield
        return
    try:
        # Set up logging with the configured log level
        logging.basicConfig(level=config.LOG_LEVEL)
        # Open database connection using test configuration
        database.open(config.SQLALCHEMY_DATABASE_URI)
        # Yield control to tests
        yield
    except Exception as e:
        # Log detailed error information for debugging
        logging.error(f"Failed to connect to database: {e}")
        logging.error(f"Database URI: {config.SQLALCHEMY_DATABASE_URI}")
        raise
    finally:
        # Clean up database connection
        util.disconnect()


@pytest.fixture
def with_data(data):
    """
    Load test data into the database and clean it up after the test.
    
    This fixture provides a convenient way to load test data for individual
    tests. It handles the complete lifecycle of test data:
    1. Loads the provided data into the database
    2. Yields control to the test
    3. Cleans up the data after the test completes
    
    The fixture is flexible and can handle different data formats:
    - List of collections: Multiple collections to load
    - Single collection: Single collection wrapped in a list
    
    This fixture is useful for tests that need specific data scenarios
    that aren't covered by the standard test user fixtures.
    
    Args:
        data: Test data to load. Can be:
              - List of collections: [{User: [{'ide': 'user1'}]}]
              - Single collection: {User: [{'ide': 'user1'}]}
    
    Yields:
        None - This fixture doesn't provide data, just manages test data lifecycle
    
    Example:
        @pytest.mark.parametrize('data', [{'User': [{'ide': 'testuser'}]}])
        def test_with_custom_data(with_data):
            # Test runs with the custom data loaded
            pass
    """
    # Handle different data formats
    if isinstance(data, list):
        # If data is already a list of collections, use it directly
        collections = data
    else:
        # If data is a single collection, wrap it in a list
        collections = [data]
    
    try:
        # Load the test data into the database
        util.load(collections)
        # Yield control to the test
        yield
    finally:
        # Clean up the test data after the test completes
        util.unload(collections)
        # Note: util.flush() is commented out - unload is used instead
        # util.flush()
