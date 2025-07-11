import logging
import math
import sys

import colorlog


def setup_logger(
        log_level,
        log_name="seadex_sonarr",
):
    """
    Set up the logger.

    Parameters:
        log_level (str): The log level to use
        log_name (str): The name of the log file

    Returns:
        A logger object for logging messages.
    """

    # Create a logger object with the script name
    logger = logging.getLogger(log_name)
    logger.propagate = False

    # Set the log level based on the provided parameter
    log_level = log_level.upper()
    if log_level == "DEBUG":
        logger.setLevel(logging.DEBUG)
    elif log_level == "INFO":
        logger.setLevel(logging.INFO)
    elif log_level == "WARNING":
        logger.setLevel(logging.WARNING)
    elif log_level == "CRITICAL":
        logger.setLevel(logging.CRITICAL)
    else:
        logger.critical(f"Invalid log level '{log_level}', defaulting to 'INFO'")
        logger.setLevel(logging.INFO)

    # Configure console logging with the specified log level
    console_handler = colorlog.StreamHandler(sys.stdout)
    if log_level == "DEBUG":
        console_handler.setLevel(logging.DEBUG)
    elif log_level == "INFO":
        console_handler.setLevel(logging.INFO)
    elif log_level == "CRITICAL":
        console_handler.setLevel(logging.CRITICAL)

    # Add the console handler to the logger
    console_handler.setFormatter(
        colorlog.ColoredFormatter("%(log_color)s%(levelname)s: %(message)s")
    )
    logger.addHandler(console_handler)

    # Overwrite previous logger if exists
    logging.getLogger(log_name).handlers.clear()
    logging.getLogger(log_name).addHandler(console_handler)

    return logger


def centred_string(
        str_to_centre,
        total_length=80,
        str_prefix="",
):
    """Centre string for a logger

    Args:
        str_to_centre: String to centre
        total_length: Total length of the string. Defaults to 80.
        str_prefix: Will include this at the start of any string. Defaults to ""
    """

    remaining_length = total_length - len(str_to_centre)
    left_side_length = math.floor(remaining_length / 2)
    right_side_length = remaining_length - left_side_length

    return f"{str_prefix}|{' ' * left_side_length} {str_to_centre} {' ' * right_side_length}|"


def left_aligned_string(
        str_to_align,
        total_length=80,
        str_prefix="",
):
    """Left-align string for a logger

    Args:
        str_to_align: String to align
        total_length: Total length of the string
        str_prefix: Will include this at the start of any string. Defaults to ""
    """

    remaining_length = total_length - len(str_to_align)
    left_side_length = 1
    right_side_length = remaining_length - left_side_length

    return f"{str_prefix}|{' ' * left_side_length} {str_to_align} {' ' * right_side_length}|"
