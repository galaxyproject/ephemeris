import logging
import tempfile


def disable_external_library_logging():
    # Omit (most of the) logging by external libraries
    logging.getLogger("bioblend").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)
    try:
        logging.captureWarnings(True)  # Capture HTTPS warngings from urllib3
    except AttributeError:
        pass


def setup_global_logger(name, log_file=None, log_level='DEBUG'):
    formatter = logging.Formatter("%(asctime)s %(levelname)-5s - %(message)s")
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level))

    if not log_file:
        handler = logging.StreamHandler()
    else:
        handler = logging.FileHandler(log_file)
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
