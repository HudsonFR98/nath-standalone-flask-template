#!/usr/bin/env python3
"""
Test runner for nath_standalone_flask_template tests.
This script handles permission issues and provides comprehensive test execution.

This test runner is designed to solve common issues when running tests in
Docker containers, particularly permission problems with pytest cache and
coverage files. It creates temporary directories with proper permissions
and ensures clean test execution.

Key Features:
- Creates temporary directories to avoid permission issues
- Sets up proper environment variables for testing
- Runs comprehensive test suite with coverage reporting
- Provides detailed output and error reporting
- Cleans up temporary files after execution
"""

import os
import sys
import subprocess
import tempfile


def get_database_host(context):
    """
    Get the appropriate database host based on the environment context.
    
    Args:
        context (str): The environment context (dev, integration, validation, prod)
    
    Returns:
        str: Database host name following the new naming scheme
    """
    if context == 'dev':
        # Development environment uses external database specified by DB_IP
        return os.environ.get('DB_IP', 'nsft_db_dev')
    else:
        # Integration, validation, and prod use the container naming scheme
        return f'nsft_db_{context}'


def main():
    """
    Run the tests with proper environment setup and cleanup.
    
    This function orchestrates the complete test execution process:
    1. Sets up environment variables for testing
    2. Creates temporary directories to avoid permission issues
    3. Configures pytest and coverage settings
    4. Executes the test suite with comprehensive options
    5. Reports results and coverage information
    6. Cleans up temporary files
    
    The function handles the common issue where pytest and coverage
    try to write to directories that the container user doesn't have
    permission to access. By using temporary directories, we ensure
    tests can run successfully regardless of file system permissions.
    
    Returns:
        int: Exit code from pytest (0 for success, non-zero for failure)
    
    Environment Variables Set:
        NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT: Context the suite runs in (integration on CI)
        DB_IP: Set to appropriate database host based on context
        COVERAGE_FILE: Points to temporary coverage data file
        PYTEST_CACHE_DIR: Points to temporary pytest cache directory
    """
    # Step 1: Get context from environment or default to integration
    context = os.environ.get('NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT', 'integration')
    print(f"Running tests in context: {context}")
    
    # Step 2: Set environment variables for test execution
    os.environ['NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT'] = context
    
    # Get the appropriate database host for this context
    db_host = get_database_host(context)
    os.environ['DB_IP'] = db_host
    
    # Step 3: Create temporary directories to avoid permission issues
    temp_dir = tempfile.mkdtemp(prefix='nath_standalone_flask_templatetest_')
    cache_dir = os.path.join(temp_dir, 'pytest_cache')
    coverage_dir = os.path.join(temp_dir, 'coverage')
    
    # Create the temporary directories with proper permissions
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(coverage_dir, exist_ok=True)
    
    # Step 4: Set coverage data file to a writable location
    os.environ['COVERAGE_FILE'] = os.path.join(coverage_dir, '.coverage')
    
    # Step 5: Set pytest cache directory via environment variable
    os.environ['PYTEST_CACHE_DIR'] = cache_dir
    
    # Step 6: Build the pytest command with comprehensive options
    cmd = [
        sys.executable, '-m', 'pytest',
        '--cov=nath_standalone_flask_template',           # Enable coverage for the main package
        '--cov-report=term',                     # Show coverage in terminal
        '--cov-report=html:' + os.path.join(coverage_dir, 'html'),  # Generate HTML report
        '--cov-report=xml:' + os.path.join(coverage_dir, 'coverage.xml'),  # Generate XML report
        '--tb=short',                            # Short traceback format
        '-v',                                    # Verbose output
        'nath_standalone_flask_template/tests/'           # Test directory to run
    ]
    cmd.extend(sys.argv[1:])
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    
    # Step 7: Display execution information
    print("Running tests with command:", ' '.join(cmd))
    print("Environment variables:")
    print(f"  NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT: {os.environ.get('NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT')}")
    print(f"  DB_IP: {os.environ.get('DB_IP')}")
    print(f"  COVERAGE_FILE: {os.environ.get('COVERAGE_FILE')}")
    print(f"  PYTEST_CACHE_DIR: {os.environ.get('PYTEST_CACHE_DIR')}")
    
    # Step 8: Execute the test suite
    # Run pytest with real-time output to console, but also capture for web interface
    print("\n" + "=" * 50)
    print("RUNNING TESTS:")
    print("=" * 50)
    
    # Use Popen to get real-time output while also capturing it
    process = subprocess.Popen(
        cmd, 
        cwd=repo_root, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Collect output while showing it in real-time
    stdout_lines = []
    stderr_lines = []
    
    # Read stdout in real-time
    if process.stdout:
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.rstrip())  # Show in console
                stdout_lines.append(output)  # Capture for web interface
    
    # Read stderr in real-time
    if process.stderr:
        while True:
            error = process.stderr.readline()
            if error == '' and process.poll() is not None:
                break
            if error:
                print(error.rstrip(), file=sys.stderr)  # Show in console
                stderr_lines.append(error)  # Capture for web interface
    
    # Wait for process to complete and get return code
    result = process.wait()
    
    # Combine captured output
    result_stdout = ''.join(stdout_lines)
    result_stderr = ''.join(stderr_lines)
    
    # Create a result object similar to subprocess.run for compatibility
    class Result:
        def __init__(self, returncode, stdout, stderr):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr
    
    result = Result(result, result_stdout, result_stderr)
    
    # Step 9: Save test output to file for web interface (integration and dev)
    if context in ('integration', 'dev'):
        test_output_file = '/opt/nath_standalone_flask_template_data/test_output.log'
        try:
            with open(test_output_file, 'w', encoding='utf-8') as f:
                f.write("Test Execution Command:\n")
                f.write(" ".join(cmd) + "\n\n")
                f.write("Environment Variables:\n")
                f.write(f"  NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT: {os.environ.get('NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT')}\n")
                f.write(f"  DB_IP: {os.environ.get('DB_IP')}\n")
                f.write(f"  COVERAGE_FILE: {os.environ.get('COVERAGE_FILE')}\n")
                f.write(f"  PYTEST_CACHE_DIR: {os.environ.get('PYTEST_CACHE_DIR')}\n\n")
                f.write("Test Output:\n")
                f.write("=" * 50 + "\n")
                f.write(result.stdout)
                if result.stderr:
                    f.write("\nErrors:\n")
                    f.write("=" * 50 + "\n")
                    f.write(result.stderr)
                f.write(f"\n\nExit Code: {result.returncode}")
            print(f"Test output saved to: {test_output_file}")
        except Exception as e:
            print(f"Warning: Could not save test output: {e}")
    else:
        # In dev context, just display the output without saving
        print("\n" + "=" * 50)
        print("TEST OUTPUT:")
        print("=" * 50)
        print(result.stdout)
        if result.stderr:
            print("\n" + "=" * 50)
            print("ERRORS:")
            print("=" * 50)
            print(result.stderr)
        print(f"\nExit Code: {result.returncode}")
    
    # Step 10: Report results and coverage information
    if result.returncode == 0:
        print(f"\nCoverage reports generated in: {coverage_dir}")
        
        # Copy coverage report to the expected location for the coverage blueprint
        coverage_dest_dir = '/opt/nath_standalone_flask_template_data/coverage_report'
        html_source = os.path.join(coverage_dir, 'html')
        html_dest = os.path.join(coverage_dest_dir, 'html')
        
        try:
            import shutil
            # Create destination directory if it doesn't exist
            os.makedirs(coverage_dest_dir, exist_ok=True)
            
            # Copy HTML coverage report to the expected location
            if os.path.exists(html_source):
                if os.path.exists(html_dest):
                    # Remove existing directory
                    shutil.rmtree(html_dest)
                
                # Copy the directory
                shutil.copytree(html_source, html_dest)
                print(f"Coverage report copied to: {html_dest}")
            else:
                print("Warning: HTML coverage report not found")
        except Exception as e:
            print(f"Warning: Could not copy coverage report: {e}")
            # Try alternative approach - copy to a different location
            try:
                alt_dest = '/tmp/coverage_report'
                if os.path.exists(html_source):
                    shutil.copytree(html_source, alt_dest, dirs_exist_ok=True)
                    print(f"Coverage report copied to alternative location: {alt_dest}")
            except Exception as alt_e:
                print(f"Warning: Alternative copy also failed: {alt_e}")
    
    # Step 11: Clean up temporary directory (but keep coverage report)
    try:
        import shutil
        shutil.rmtree(temp_dir)
        print(f"Cleaned up temporary directory: {temp_dir}")
    except Exception as e:
        print(f"Warning: Could not clean up temporary directory {temp_dir}: {e}")
    
    # Step 12: Return the test execution result
    return result.returncode


if __name__ == '__main__':
    # Run the main function and exit with the appropriate code
    sys.exit(main()) 