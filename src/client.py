from keboola.component import UserException
from keboola.http_client import HttpClient
from requests.exceptions import HTTPError

import logging
import datetime

ORDERS_PAGE_SIZE = 100
ORDERS_BATCH_SIZE = 1000


class ToastClient(HttpClient):

    def __init__(self, client_id, client_secret, url):
        super().__init__(url)

        self.access_token = self.get_token(client_id, client_secret)
        self.update_auth_header({"Authorization": f'Bearer {self.access_token}'})

    def get_token(self, client_id, client_secret):
        headers = {"Content-Type": "application/json"}
        payload = {"clientId": client_id, "clientSecret": client_secret, "userAccessType": "TOAST_MACHINE_CLIENT"}

        refresh_rsp = self.post_raw("authentication/v1/authentication/login", headers=headers, json=payload)

        if refresh_rsp.status_code == 200:
            logging.info("Successfully refreshed access token.")
            return refresh_rsp.json()['token']['accessToken']

        else:
            raise UserException(f"Could not refresh access token. "
                                f"Received: {refresh_rsp.status_code} - {refresh_rsp.json()}.")

    def list_restaurants(self):
        """
        List all orders
        """

        try:
            response = self.get(endpoint_path='partners/v1/restaurants')
        except HTTPError as e:
            raise UserException(f"Error while listing orders: {e.response.json()['message']}")

        return response

    def list_restaurants_in_group(self, restaurant_id: str, restaurant_group_id: str) -> list:
        """
        List all orders
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.get(endpoint_path=f"/restaurants/v1/groups/{restaurant_group_id}/restaurants")
        except HTTPError as e:
            raise UserException(f"Error while listing orders: {e.response.json()['message']}")

        return [r['guid'] for r in response if 'guid' in r]

    def get_restaurant_configuration(self, restaurant_id: str):
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.get(endpoint_path=f"restaurants/v1/restaurants/{restaurant_id}")
        except HTTPError as e:
            raise UserException(f"Error while listing orders: {e.response.json()['message']}")

        return response

    def list_orders(self, restaurant_id: str, date_from: datetime, date_to: datetime) -> list:
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
                response = self.get(endpoint_path='orders/v2/ordersBulk', params=query)
            except HTTPError as e:
                raise UserException(f"Error while listing orders: {e.response.json()['message']}")

            if not response:
                break

            batch.extend(response)

            if page % (ORDERS_BATCH_SIZE/ORDERS_PAGE_SIZE) == 0:
                yield batch
                batch = []

            page += 1

        if batch:
            yield batch
