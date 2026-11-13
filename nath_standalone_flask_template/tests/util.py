import logging

from nath_standalone_flask_template.lib import database
from nath_standalone_flask_template.lib import config
from nath_standalone_flask_template import models
from sqlalchemy import text


def load(collections):
    """
    Load test data collections into the database.
    
    This function is used to populate the database with test data before
    running tests. It takes a list of collections (dictionaries mapping
    model classes to lists of data dictionaries) and creates the corresponding
    database records.
    
    The function handles the creation of model instances and commits them
    to the database. If any error occurs during the loading process,
    it rolls back the transaction to maintain database consistency.
    
    Args:
        collections (list): List of collections, where each collection is a dict
                           mapping model classes to lists of data dictionaries.
                           Example: [{User: [{'ide': 'user1', 'pwd': 'pass1'}]}]
    
    Raises:
        Exception: If loading fails, the transaction is rolled back and the
                  exception is re-raised.
    
    Example:
        collections = [{User: [{'ide': 'testuser', 'pwd': 'testpass'}]}]
        load(collections)
    """
    try:
        # Iterate through each collection
        for collection in collections:
            # Iterate through each model and its data in the collection
            for model, data_list in collection.items():
                # Create model instances for each data dictionary
                for data in data_list:
                    instance = model(**data)
                    database.DBSession.add(instance)
        # Commit all changes to the database
        database.DBSession.commit()
    except Exception as e:
        # Rollback on error to maintain database consistency
        database.DBSession.rollback()
        logging.error(f"Failed to load test data: {e}")
        raise


def unload(collections):
    """
    Remove test data collections from the database.
    
    This function is used to clean up test data after tests complete.
    It handles foreign key constraints by deleting related records first,
    then deletes the main records. This ensures referential integrity
    is maintained during cleanup.
    
    The function handles different models differently:
    - User and Role models: Delete user_roles associations first
    - Other models: Delete directly
    
    Args:
        collections (list): List of collections to unload (same format as load())
    
    Raises:
        Exception: If unloading fails, the transaction is rolled back and the
                  exception is re-raised.
    
    Example:
        collections = [{User: [{'ide': 'testuser'}]}]
        unload(collections)
    """
    try:
        # Iterate through each collection
        for collection in collections:
            # Iterate through each model in the collection
            for model in collection.keys():
                # Handle foreign key constraints for specific models
                if model == models.User:
                    # Delete user_roles associations first to avoid foreign key violations
                    database.DBSession.execute(text("DELETE FROM user_roles"))
                    # Then delete users
                    database.DBSession.query(model).delete()
                elif model == models.Role:
                    # Delete user_roles associations first to avoid foreign key violations
                    database.DBSession.execute(text("DELETE FROM user_roles"))
                    database.DBSession.execute(text("DELETE FROM role_permissions"))
                    # Then delete roles
                    database.DBSession.query(model).delete()
                elif model == models.Permission:
                    database.DBSession.execute(text("DELETE FROM role_permissions"))
                    database.DBSession.query(model).delete()
                else:
                    # For other models, delete directly
                    database.DBSession.query(model).delete()
        # Commit all deletions
        database.DBSession.commit()
    except Exception as e:
        # Rollback on error
        database.DBSession.rollback()
        logging.error(f"Failed to unload test data: {e}")
        raise


def connect():
    """
    Connect to the database using the test configuration.
    
    This function initializes the database connection for testing.
    It sets up logging and opens a connection to the test database.
    
    This function is typically called at the beginning of test suites
    that require database access.
    """
    # Set up logging with the configured log level
    logging.basicConfig(level=config.LOG_LEVEL)
    # Open database connection using test configuration
    database.open(config.SQLALCHEMY_DATABASE_URI)


def disconnect():
    """
    Disconnect from the database and clean up the session.
    
    This function removes the database session, effectively disconnecting
    from the database. It should be called at the end of test suites
    to ensure proper cleanup.
    """
    database.DBSession.remove()


def flush():
    """
    Flush all test data from the database.
    
    This function removes all test data from the database, providing
    a clean slate for tests. It handles foreign key constraints by
    deleting related records first.
    
    The function specifically targets the models used in testing
    (User and Role) and their associations (user_roles).
    
    Raises:
        Exception: If flushing fails, the transaction is rolled back and the
                  exception is re-raised.
    """
    try:
        # Rollback any pending transactions
        database.DBSession.rollback()
        # Delete related records first to avoid foreign key constraints
        database.DBSession.execute(text("DELETE FROM user_roles"))
        database.DBSession.execute(text("DELETE FROM role_permissions"))
        # Delete data from our test models
        models.User.query.delete()
        models.Role.query.delete()
        models.Permission.query.filter_by(is_system=False).delete()
        if getattr(models, 'AppSetting', None) is not None:
            models.AppSetting.query.delete()
        # Commit the deletions
        database.DBSession.commit()
    except Exception as e:
        # Rollback on error
        database.DBSession.rollback()
        logging.error(f"Failed to flush database: {e}")
        raise


def expire():
    """
    Expire all objects in the current database session.
    
    This function forces SQLAlchemy to reload all objects from the database
    on their next access. This is useful when you want to ensure you're
    working with the most up-to-date data from the database.
    """
    database.DBSession.expire_all()


def commit():
    """
    Commit the current database transaction.
    
    This function commits all pending changes in the current database session
    to the database. It's a convenience function that delegates to the
    database session's commit method.
    """
    database.DBSession.commit()


def rollback():
    """
    Rollback the current database transaction.
    
    This function rolls back all pending changes in the current database session,
    effectively canceling any uncommitted modifications. It's useful for
    cleaning up after failed operations or tests.
    """
    database.DBSession.rollback()


def login(client, username, password):
    """
    Helper function to perform a login request using the test client.
    
    This function simulates a user login by making a POST request to the
    login endpoint with the provided credentials. It follows redirects
    to handle any post-login redirects.
    
    Args:
        client: Flask test client instance
        username (str): The username to login with
        password (str): The password to login with
    
    Returns:
        Response: The Flask response object from the login request
    
    Example:
        response = login(client, 'testuser', 'testpass')
        assert response.status_code == 200
    """
    return client.post(
        '/login',
        data=dict(USR=username, PWD=password),
        follow_redirects=True)


def logout(client):
    """
    Helper function to perform a logout request using the test client.
    
    This function simulates a user logout by making a GET request to the
    logout endpoint. It follows redirects to handle any post-logout redirects.
    
    Args:
        client: Flask test client instance
    
    Returns:
        Response: The Flask response object from the logout request
    
    Example:
        response = logout(client)
        assert response.status_code == 200
    """
    return client.get('/logout', follow_redirects=True) 