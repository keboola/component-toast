"""
Template Component main class.

"""
import csv
import logging

from keboola.component.base import ComponentBase
from keboola.component.exceptions import UserException
from keboola.component.dao import TableDefinition
from keboola.utils import parse_datetime_interval as parse_date
from keboola.json_to_csv import TableMapping, Parser

from configuration import Configuration
from client import ToastClient

import json
from pathlib import Path
from typing import Dict, IO
from dataclasses import dataclass


@dataclass
class WriterCacheRecord:
    file: IO
    writer: csv.DictWriter
    table_definition: TableDefinition


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

        self._writer_cache: dict[str, WriterCacheRecord] = dict()
        with open(Path(__file__).parent.joinpath('parser_mapping.json')) as f:
            self.parser_mapping = json.loads(f.read())

        self._init_configuration()
        self._init_client()

    def _init_configuration(self) -> None:
        self.validate_configuration_parameters(Configuration.get_dataclass_required_parameters())
        self.cfg: Configuration = Configuration.load_from_dict(self.configuration.parameters)

    def _init_client(self) -> None:
        self.client = ToastClient(self.configuration.image_parameters.get("client_id"),
                                  self.configuration.image_parameters.get("#client_secret"),
                                  self.cfg.credentials.url)

    def run(self):
        """
        Main execution code
        """

        restaurant_ids = self.cfg.restaurants.restaurants_ids.split(',')

        if not restaurant_ids:
            raise UserException("No restaurant IDs provided")

        for guid in restaurant_ids:
            if 'configuration_information' in self.cfg.endpoints:
                self.download_restaurant_config(guid)
            if 'orders' in self.cfg.endpoints:
                self.download_orders(guid)

        for table, cache_record in self._writer_cache.items():
            cache_record.file.close()
            self.write_manifest(cache_record.table_definition)

    def download_orders(self, restaurant_id: str):

        start_date, end_date = parse_date(self.cfg.sync_options.start_date, self.cfg.sync_options.end_date)
        orders = self.client.list_orders(restaurant_id, start_date, end_date)

        for batch in orders:
            mapping = TableMapping.build_from_mapping_dict(self.parser_mapping['orders'])
            parser = Parser("orders", TableMapping.build_from_mapping_dict(self.parser_mapping['orders']), False)

            out = parser.parse_data(batch)

            logging.info(f'Writing {len(out["orders"])} orders to output')

            for table_name, table_mapping in table_mappings_flattened_by_key(mapping).items():
                if table_name in out:
                    self.write_to_csv(out, table_name, table_mapping)

    def download_restaurant_config(self, restaurant_id: str):
        config = self.client.get_restaurant_configuration(restaurant_id)
        mapping = TableMapping.build_from_mapping_dict(self.parser_mapping['configuration'])

        parser = Parser("configuration", mapping, False)
        out = parser.parse_data(config)

        for table_name, table_mapping in table_mappings_flattened_by_key(mapping).items():
            if table_name in out:
                self.write_to_csv(out, table_name, table_mapping)

    def write_to_csv(self, parsed_data: dict,
                     table_name: str,
                     table_mapping: TableMapping,
                     ) -> None:

        if not self._writer_cache.get(table_name):
            incremental_load = self.cfg.destination.load_type.is_incremental()
            # TODO: use table_mapping.table_name for name once fixed in Parser
            columns = list(table_mapping.column_mappings.values())
            table_def = self.create_out_table_definition(f'{table_name}.csv',
                                                         primary_key=table_mapping.primary_keys,
                                                         incremental=incremental_load,
                                                         schema=columns)

            out = open(table_def.full_path, 'w', newline='')
            writer = csv.DictWriter(out, columns)
            writer.writeheader()

            self._writer_cache[table_name] = WriterCacheRecord(out, writer, table_def)

        writer = self._writer_cache[table_name].writer
        for record in parsed_data[table_name]:
            writer.writerow(record)


# temp before fix is merged
def table_mappings_flattened_by_key(table_mapping: TableMapping) -> dict[str, TableMapping]:
    """
    Retrieve a flattened representation of the mapping structures. Returns dictionary structure where each mapping
    in the hierarchy is indexed by the table name.

    E.g. Table mapping with root table name `user` and child table `user_address` returns following strucutre:
    {"user": TableMapping, "user_address":TableMapping")

    Parameters:
    - path (Optional[str]): The object path for which the mapping should be retrieved.
                            If None, the full flattened mapping is returned.

    Returns:
    - Dict: Flattened representation of the mapping structure.
    """

    def _flatten_mapping(mapping: 'TableMapping', key='') -> Dict:
        flat_mappings = {}

        table_name = mapping.table_name
        if not key:
            key = table_name
        flat_mappings[key] = mapping

        for child_key, child_mapping in mapping.child_tables.items():
            # TODO: use dynamic separator
            new_key = f'{key}_{child_key}'
            flat_mappings.update(_flatten_mapping(child_mapping, new_key))

        return flat_mappings

    # recursively flatten
    full_mapping = _flatten_mapping(table_mapping)

    return full_mapping


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
