import dataclasses
import json
from dataclasses import dataclass, field
from typing import List
from enum import Enum
import dataconf


class ConfigurationBase:
    @staticmethod
    def _convert_private_value(value: str):
        return value.replace('"#', '"pswd_')

    @staticmethod
    def _convert_private_value_inv(value: str):
        if value and value.startswith("pswd_"):
            return value.replace("pswd_", "#", 1)
        else:
            return value

    @classmethod
    def load_from_dict(cls, configuration: dict):
        """
        Initialize the configuration dataclass object from dictionary.
        Args:
            configuration: Dictionary loaded from json configuration.

        Returns:

        """
        json_conf = json.dumps(configuration)
        json_conf = ConfigurationBase._convert_private_value(json_conf)
        return dataconf.loads(json_conf, cls, ignore_unexpected=True)

    @classmethod
    def get_dataclass_required_parameters(cls) -> List[str]:
        """
        Return list of required parameters based on the dataclass definition (no default value)
        Returns: List[str]

        """
        return [cls._convert_private_value_inv(f.name)
                for f in dataclasses.fields(cls)
                if f.default == dataclasses.MISSING
                and f.default_factory == dataclasses.MISSING
                ]


@dataclass
class Credentials(ConfigurationBase):
    url: str = ""
    client_id: str = ""
    pswd_client_secret: str = ""


@dataclass
class RestaurantsOptions(ConfigurationBase):
    restaurant_select_type: str = ""
    restaurants_ids: str = ""


@dataclass
class SyncOptions(ConfigurationBase):
    start_date: str = ""
    end_date: str = ""


class LoadType(str, Enum):
    full_load = "full_load"
    incremental_load = "incremental_load"

    def is_incremental(self) -> bool:
        return self.value == self.incremental_load


@dataclass
class Destination(ConfigurationBase):
    load_type: LoadType = "incremental_load"


@dataclass
class Configuration(ConfigurationBase):
    credentials: Credentials
    restaurants: RestaurantsOptions
    sync_options: SyncOptions
    destination: Destination
    endpoints: List[str] = field(default_factory=list)
