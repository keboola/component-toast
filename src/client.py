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
            raise UserException(f"Error while listing restaurants: {e.response.json()['message']}")

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
            raise UserException(f"Error while listing orders: {e.response.json()['message']}")

        return [str(r['guid']) for r in response if 'guid' in r]

    def get_restaurant_configuration(self, restaurant_id: str) -> Dict:
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.request("GET", endpoint_path=f"restaurants/v1/restaurants/{restaurant_id}")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while listing restaurant details: {e.response.json()['message']}")

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
                raise UserException(f"Error while listing orders: {e.response.json()['message']}")

            if not response.json():
                break

            batch.extend(response.json())

            if page % (ORDERS_BATCH_SIZE/ORDERS_PAGE_SIZE) == 0:
                yield batch
                batch = []

            page += 1

        if batch:
            yield batch

    def get_cash_entries(self, restaurant_id: str, business_date: str) -> Dict:
        """
        Get cash entries for a specific business date

        Args:
            restaurant_id: The GUID of the restaurant
            business_date: The business date in format YYYYMMDD

        Returns:
            List of cash entry objects
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        query = {
            "businessDate": business_date
        }

        try:
            response = self.request("GET", endpoint_path='cashmgmt/v1/entries', params=query)
            response.raise_for_status()
        except HTTPError as e:
            raise UserException(f"Error while fetching cash entries: {e.response.json()['message']}")

        return response.json()

    def get_deposits(self, restaurant_id: str, business_date: str) -> Dict:
        """
        Get deposits for a specific business date

        Args:
            restaurant_id: The GUID of the restaurant
            business_date: The business date in format YYYYMMDD

        Returns:
            List of deposit objects containing information about cash removed
            from a restaurant to be deposited in a bank
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        query = {
            "businessDate": business_date
        }

        try:
            response = self.request("GET", endpoint_path='cashmgmt/v1/deposits', params=query)
            response.raise_for_status()
        except HTTPError as e:
            raise UserException(f"Error while fetching deposits: {e.response.json()['message']}")

        return response.json()

    def get_employees(self, restaurant_id: str) -> Dict:
        """
        Get employee information from the labor API

        Args:
            restaurant_id: The GUID of the restaurant

        Returns:
            List of employee objects containing information about restaurant employees
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.request("GET", endpoint_path='labor/v1/employees')
            response.raise_for_status()
        except HTTPError as e:
            raise UserException(f"Error while fetching employees: {e.response.json()['message']}")

        return response.json()

    def get_shifts(self, restaurant_id: str, start_date: datetime.datetime, end_date: datetime.datetime) -> Dict:
        """
        Get shift information from the labor API

        Args:
            restaurant_id: The GUID of the restaurant
            start_date: Start date and time of the period to match shifts
            end_date: End date and time of the period to match shifts

        Returns:
            List of shift objects containing information about restaurant employee shifts
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})


        query = {
            "startDate": start_date.isoformat(timespec="milliseconds") + 'Z',
            "endDate": end_date.isoformat(timespec="milliseconds") + 'Z'
        }

        try:
            response = self.request("GET", endpoint_path='labor/v1/shifts', params=query)
            response.raise_for_status()
        except HTTPError as e:
            raise UserException(f"Error while fetching shifts: {e.response.json()['message']}")

        return response.json()

    def get_jobs(self, restaurant_id: str, job_ids: list[str] = None) -> Dict:
        """
        Get job information from the labor API

        Args:
            restaurant_id: The GUID of the restaurant
            job_ids: Optional list of job identifiers to filter results

        Returns:
            List of job objects containing information about restaurant jobs
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        query = {}
        if job_ids:
            query["jobIds"] = job_ids

        try:
            response = self.request("GET", endpoint_path='labor/v1/jobs', params=query)
            response.raise_for_status()
        except HTTPError as e:
            raise UserException(f"Error while fetching jobs: {e.response.json()['message']}")

        return response.json()

    def get_time_entries(self, restaurant_id: str,
                         start_date: datetime.datetime = None,
                         end_date: datetime.datetime = None,
                         ) -> Dict:
        """
        Get time entry information from the labor API

        Args:
            restaurant_id: The GUID of the restaurant
            start_date: Optional start date and time of period to match time entries
            end_date: Optional end date and time of period to match time entries

        Returns:
            List of time entry objects containing information about employee shift events

        Note:
            Valid requests must include one of:
            - One or more time_entry_ids
            - Both start_date and end_date
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        query = {'startDate': start_date.isoformat(timespec="milliseconds") + 'Z', 'endDate': end_date.isoformat(timespec="milliseconds") + 'Z'}

        try:
            response = self.request("GET", endpoint_path='labor/v1/timeEntries', params=query)
            response.raise_for_status()
        except HTTPError as e:
            raise UserException(f"Error while fetching time entries: {e.response.json()['message']}")

        return response.json()
