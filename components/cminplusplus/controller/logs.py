import logging

class CustomFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    blue = "\x1b[34;20m"
    reset = "\x1b[0m"
    format = " %(asctime)s | %(module)s | %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: blue + "[*]" + format + reset,
        logging.INFO: grey + "[+]" + format + reset,
        logging.WARNING: yellow + "[!]" + format + reset,
        logging.ERROR: red + "[X]" + format + reset,
        logging.CRITICAL: bold_red + "[!]"+ format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

def init_logging(debug = False):
    console_handler = logging.StreamHandler()
    formatter = CustomFormatter()
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    if debug:
        root_logger.setLevel(logging.DEBUG)
    else:
        root_logger.setLevel(logging.INFO)

    root_logger.addHandler(console_handler)