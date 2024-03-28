from keboola.component import UserException
from keboola.http_client import HttpClient
from requests.exceptions import HTTPError

import logging


class ToastClient(HttpClient):

    def __init__(self, client_id, client_secret, url):
        super().__init__(url)

        token = self.refresh_token(client_id, client_secret)
        self.update_auth_header({"Authorization": f'Bearer {token}'})

    def refresh_token(self, client_id, client_secret):
        headers = {"Content-Type": "application/json"}
        payload = {"clientId": client_id, "clientSecret": client_secret, "userAccessType": "TOAST_MACHINE_CLIENT"}

        refresh_rsp = self.post_raw("authentication/v1/authentication/login", headers=headers, data=payload)

        if refresh_rsp.status_code == 200:
            logging.info("Successfully refreshed access token.")
            return refresh_rsp.json()['access_token']

        else:
            raise UserException(f"Could not refresh access token. "
                                f"Received: {refresh_rsp.status_code} - {refresh_rsp.json()}.")

    def list_orders(self, restaurant_id, date_from, date_to) -> dict:
        """
        List all orders
        """

        page = 0

        url = "https://toast-api-server/orders/v2/ordersBulk"

        query = {
            "businessDate": "string",
            "endDate": date_to,
            "page": page,
            "pageSize": "100",
            "startDate": date_from
        }

        headers = {
            "Toast-Restaurant-External-ID": restaurant_id,
            "Authorization": "Bearer <YOUR_TOKEN_HERE>"
        }

        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        response = self.get(url, headers=headers, params=query)

        logging.info(response)

        # try:
        #     response = self.get("connectors")
        # except HTTPError as e:
        #     raise UserException(f"Error while listing flows: {e}")
        #
        # return response.get("data", [])

    def list_flows(self) -> dict:
        """
        List all flows
        """

        try:
            response = self.get("flows")
        except HTTPError as e:
            raise UserException(f"Error while listing flows: {e}")

        return response.get("data", [])

    def run_flow(self, flow_id: str) -> dict:
        """
        List all flows
        """

        try:
            response = self.post(f"flows/{flow_id}/run")
        except HTTPError as e:
            raise UserException(f"Error while listing flows: {e}")

        return response['message']

    def get_flow_status(self, flow_id: str) -> dict:
        """
        List all flows
        """

        try:
            response = self.get(f"flows/{flow_id}/status")
        except HTTPError as e:
            raise UserException(f"Error while listing flows: {e}")

        return response
