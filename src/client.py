import logging
import datetime
from collections.abc import Iterator
from typing import Dict
from requests.exceptions import HTTPError
from ratelimit import limits, sleep_and_retry

from keboola.component import UserException
from keboola.http_client import HttpClient

ORDERS_PAGE_SIZE = 100
ORDERS_BATCH_SIZE = 1000


def _parse_http_error(e) -> str:
    try:
        body = e.response.json()
        message = body.get("message", str(e))
        code = body.get("code")
        request_id = body.get("requestId")
        code_part = f"[code={code}] " if code is not None else ""
        request_id_part = f" (requestId={request_id})" if request_id else ""
        return f"{code_part}{message}{request_id_part}"
    except Exception:
        return e.response.text or str(e)


class ToastClient(HttpClient):

    def __init__(self, client_id, client_secret, url):
        super().__init__(url)

        self.access_token = self.get_token(client_id, client_secret)
        self.update_auth_header({"Authorization": f'Bearer {self.access_token}'})

    # API rate limits: https://doc.toasttab.com/doc/devguide/apiRateLimiting.html
    @sleep_and_retry
    @limits(calls=20, period=1)
    @sleep_and_retry
    @limits(calls=10_000, period=900)
    def request(self, method, endpoint_path, **kwargs):
        logging.debug(f"Requesting {method}, {endpoint_path}")
        return self._request_raw(method, endpoint_path, **kwargs)

    def get_token(self, client_id, client_secret):
        headers = {"Content-Type": "application/json"}
        payload = {"clientId": client_id, "clientSecret": client_secret, "userAccessType": "TOAST_MACHINE_CLIENT"}

        refresh_rsp = self.request("POST", "authentication/v1/authentication/login", headers=headers, json=payload)

        if refresh_rsp.status_code == 200:
            logging.info("Successfully refreshed access token.")
            return refresh_rsp.json()['token']['accessToken']

        else:
            raise UserException(f"Could not refresh access token. "
                                f"Received: {refresh_rsp.status_code} - {refresh_rsp.json()}.")

    def list_restaurants(self) -> list[Dict]:
        """
        List all orders
        """

        try:
            response = self.request("GET", "partners/v1/restaurants")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while listing restaurants: {_parse_http_error(e)}")

        return response.json()

    def list_restaurants_in_group(self, restaurant_id: str, restaurant_group_id: str) -> list[str]:
        """
        List all orders
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.request("GET", endpoint_path=f"/restaurants/v1/groups/{restaurant_group_id}/restaurants")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while listing orders: {_parse_http_error(e)}")

        return [str(r['guid']) for r in response if 'guid' in r]

    def get_restaurant_configuration(self, restaurant_id: str) -> Dict:
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.request("GET", endpoint_path=f"restaurants/v1/restaurants/{restaurant_id}")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while listing restaurant details: {_parse_http_error(e)}")

        return response.json()

    def list_orders(self, restaurant_id: str, date_from: datetime, date_to: datetime) -> Iterator[list[Dict]]:
        """
        List all orders
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})
        batch = []
        page = 1
        while True:
            query = {
                "endDate": date_to.isoformat(timespec="milliseconds") + '+0000',
                "page": page,
                "pageSize": ORDERS_PAGE_SIZE,
                "startDate": date_from.isoformat(timespec="milliseconds") + '+0000'
            }

            try:

                response = self.request("GET", endpoint_path='orders/v2/ordersBulk', params=query)
                response.raise_for_status()

            except HTTPError as e:
                raise UserException(f"Error while listing orders: {_parse_http_error(e)}")

            if not response.json():
                break

            batch.extend(response.json())

            if page % (ORDERS_BATCH_SIZE/ORDERS_PAGE_SIZE) == 0:
                yield batch
                batch = []

            page += 1

        if batch:
            yield batch

    def dining_options(self, restaurant_id: str) -> list[Dict]:
        """
        List all dinning options
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.request("GET", "config/v2/diningOptions")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while getting dining options: {_parse_http_error(e)}")

        return response.json()

    def menus(self, restaurant_id: str) -> list[Dict]:
        """
        List all menus
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.request("GET", "menus/v2/menus")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while getting menus: {_parse_http_error(e)}")

        data = response.json()
        return data.get("menus", [])

    def employees(self, restaurant_id: str) -> list[Dict]:
        """
        List all employees
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.request("GET", "labor/v1/employees")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while getting employees: {_parse_http_error(e)}")

        return response.json()
