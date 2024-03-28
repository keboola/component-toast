"""
Template Component main class.

"""
import csv
import logging
from datetime import datetime

from keboola.component.base import ComponentBase
from keboola.component.exceptions import UserException
from keboola.utils import parse_datetime_interval

from configuration import Configuration
from client import ToastClient

# configuration variables
KEY_API_TOKEN = '#api_token'
KEY_PRINT_HELLO = 'print_hello'

# list of mandatory parameters => if some is missing,
# component will fail with readable message on initialization.
REQUIRED_PARAMETERS = [KEY_PRINT_HELLO]
REQUIRED_IMAGE_PARS = []


class Component(ComponentBase):
    """
        Extends base class for general Python components. Initializes the CommonInterface
        and performs configuration validation.

        For easier debugging the data folder is picked up by default from `../data` path,
        relative to working directory.

        If `debug` parameter is present in the `config.json`, the default logger is set to verbose DEBUG mode.
    """

    def __init__(self):
        super().__init__()

    def _init_configuration(self) -> None:
        self.validate_configuration_parameters(Configuration.get_dataclass_required_parameters())
        self.cfg: Configuration = Configuration.load_from_dict(self.configuration.parameters)

    def _init_client(self) -> None:
        self.client = ToastClient(self.cfg.credentials.client_id, self.cfg.credentials.pswd_client_secret,
                                  self.cfg.credentials.url)

    def run(self):
        """
        Main execution code
        """

        self._init_configuration()
        self._init_client()

        start_date, end_date = parse_datetime_interval(self.cfg.report_settings.date_from,
                                                       self.cfg.report_settings.date_to)

        self.client.list_orders(self.cfg.report_settings.restaurant_id, start_date, end_date)

        logging.info("Hello!")


"""
        Main entrypoint
"""
if __name__ == "__main__":
    try:
        comp = Component()
        # this triggers the run method by default and is controlled by the configuration.action parameter
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
