"""
Core functionality for the Tenant Legal Guidance System.
"""

import logging
import os
import sys
from datetime import datetime

import uvicorn


# Configure logging
def setup_logging():
    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # Configure logging format and handlers
    log_filename = f"logs/tenant_legal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Create formatters
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_formatter = logging.Formatter("%(levelname)s - %(message)s")

    # Create handlers
    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


def main():
    """Main entry point for the application."""
    # Initialize logging
    logger = setup_logging()
    logger.info("Starting Tenant Legal Guidance System")

    # Get port from environment or use default
    port = int(os.getenv("PORT", "8000"))

    # Run the FastAPI application
    uvicorn.run("tenant_legal_guidance.api.app:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    main()
