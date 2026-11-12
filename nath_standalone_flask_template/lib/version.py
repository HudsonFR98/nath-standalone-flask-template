import os
import re
from datetime import datetime

def get_version():
    """
    Get the version based on context:
    - DEV: Only setup.py version (e.g., v2.0.0)
    - INTEGRATION/VALIDATION/PROD: setup.py version + build date (e.g., v2.0.0+20260626.164400)
    """
    try:
        # Read setup.py to extract version
        setup_py_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'setup.py')
        with open(setup_py_path, 'r') as f:
            setup_content = f.read()
        
        # Extract version using regex
        version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', setup_content)
        if version_match:
            base_version = version_match.group(1)
        else:
            base_version = "1.0.0"  # fallback
        
        # Get context from environment
        context = os.environ.get('NATH_STANDALONE_FLASK_TEMPLATE_CONTEXT', 'dev')
        
        if context == 'dev':
            # In dev context, show only the base version
            return f"v{base_version}"
        else:
            # In other contexts, try to get build date from environment variable
            # This should be set during deployment in the pipeline
            build_date = os.environ.get('BUILD_DATE')
            if build_date:
                # Convert Ansible date format to our compact format (YYYYMMDD.HHMMSS)
                # Ansible format: 2026.01.15.14.30.25.123456
                if '.' in build_date:
                    parts = build_date.split('.')
                    if len(parts) >= 6:
                        # Extract year, month, day, hour, minute, second
                        year, month, day, hour, minute, second = parts[:6]
                        # Format as YYYYMMDD.HHMMSS
                        formatted_date = f"{year}{month.zfill(2)}{day.zfill(2)}.{hour.zfill(2)}{minute.zfill(2)}{second.zfill(2)}"
                        return f"v{base_version}+{formatted_date}"
                    else:
                        # Fallback: use as is
                        return f"v{base_version}+{build_date}"
                else:
                    return f"v{base_version}+{build_date}"
            else:
                # Fallback: use current date/time in compact format
                now = datetime.now()
                date_str = now.strftime("%Y%m%d.%H%M%S")
                return f"v{base_version}+{date_str}"
                
    except Exception:
        # Fallback if anything goes wrong
        return "v1.0.0+unknown" 