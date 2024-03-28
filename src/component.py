"""
Template Component main class.

"""
import csv
import logging
# from datetime import datetime

from keboola.component.base import ComponentBase
from keboola.component.exceptions import UserException
from keboola.utils import parse_datetime_interval

from configuration import Configuration
from client import ToastClient


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

        orders = self.client.list_orders(self.cfg.report_settings.restaurant_id, start_date, end_date)

        out_table = self.create_out_table_definition("orders.csv")

        with open(out_table.full_path, 'w') as out_file:
            writer = csv.DictWriter(out_file, fieldnames=orders[0].keys())
            for order in orders:
                writer.writerow(order)

        self.write_manifest(out_table)


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
