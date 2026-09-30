import logging
import datetime
import time
from functools import wraps
from collections.abc import Iterator
from typing import Dict
from requests.exceptions import HTTPError
from ratelimit import limits, sleep_and_retry
import requests

from keboola.component import UserException
from keboola.http_client import HttpClient

ORDERS_PAGE_SIZE = 100
ORDERS_BATCH_SIZE = 1000


def retry_on_transient_error(max_retries=3, initial_backoff=0.5):
    """
    Retry on transient network errors with exponential backoff.

    Catches:
    - ConnectionResetError, ConnectionError (TCP-level)
    - requests.exceptions.ConnectionError, Timeout, ChunkedEncodingError (HTTP client)

    Re-raises immediately on non-transient errors (HTTPError, etc.).
    After max_retries exhausted, re-raises the last exception.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            backoff = initial_backoff
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (ConnectionResetError, ConnectionError,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                        requests.exceptions.ChunkedEncodingError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        logging.warning(
                            f"Transient network error in {func.__name__} "
                            f"(attempt {attempt+1}/{max_retries+1}): {type(e).__name__}: {e}. "
                            f"Retrying in {backoff}s..."
                        )
                        time.sleep(backoff)
                        backoff *= 2
                    else:
                        logging.exception(
                            f"Transient network error persisted after {max_retries} retries in {func.__name__}"
                        )
                        raise
                except Exception:
                    # Non-transient errors (HTTPError, UserException, etc.) re-raise immediately
                    raise

            # Should not reach here, but re-raise just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


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

    def _request_with_retry(self, method: str, endpoint_path: str, max_retries: int = 3,
                            initial_backoff: float = 0.5, **kwargs):
        """
        Wrapper around request() that retries on transient network errors.

        Catches ConnectionResetError, ConnectionError, and other transient exceptions.
        Re-raises immediately on non-transient errors (HTTPError, etc.).

        Args:
            method: HTTP method
            endpoint_path: API endpoint path
            max_retries: Number of retry attempts
            initial_backoff: Initial backoff in seconds (exponential)
            **kwargs: Additional arguments passed to self.request()

        Returns:
            requests.Response

        Raises:
            The last exception after all retries exhausted
        """
        backoff = initial_backoff
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                return self.request(method, endpoint_path, **kwargs)
            except (ConnectionResetError, ConnectionError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError) as e:
                last_exception = e
                if attempt < max_retries:
                    logging.warning(
                        f"Transient network error on {method} {endpoint_path} "
                        f"(attempt {attempt+1}/{max_retries+1}): {type(e).__name__}: {e}. "
                        f"Retrying in {backoff}s..."
                    )
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    logging.exception(
                        f"Transient network error persisted after {max_retries} retries on {method} {endpoint_path}"
                    )
                    raise
            except Exception:
                # Non-transient errors re-raise immediately
                raise

        # Should not reach here, but re-raise just in case
        if last_exception:
            raise last_exception

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

    @retry_on_transient_error(max_retries=3, initial_backoff=0.5)
    def list_restaurants(self) -> list[Dict]:
        """
        List all restaurants
        """

        try:
            response = self.request("GET", "partners/v1/restaurants")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while listing restaurants: {_parse_http_error(e)}")

        return response.json()

    @retry_on_transient_error(max_retries=3, initial_backoff=0.5)
    def list_restaurants_in_group(self, restaurant_id: str, restaurant_group_id: str) -> list[str]:
        """
        List restaurants in group
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.request("GET", endpoint_path=f"/restaurants/v1/groups/{restaurant_group_id}/restaurants")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while listing restaurants in group: {_parse_http_error(e)}")

        return [str(r['guid']) for r in response if 'guid' in r]

    @retry_on_transient_error(max_retries=3, initial_backoff=0.5)
    def get_restaurant_configuration(self, restaurant_id: str) -> Dict:
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.request("GET", endpoint_path=f"restaurants/v1/restaurants/{restaurant_id}")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while getting restaurant configuration: {_parse_http_error(e)}")

        return response.json()

    def list_orders(self, restaurant_id: str, date_from: datetime, date_to: datetime) -> Iterator[list[Dict]]:
        """
        List all orders (paginated). Retries on transient network errors.
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

            # Retry on transient network errors (connection reset, timeout, etc.)
            response = self._request_with_retry("GET", 'orders/v2/ordersBulk', params=query)

            try:
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

    @retry_on_transient_error(max_retries=3, initial_backoff=0.5)
    def dining_options(self, restaurant_id: str) -> list[Dict]:
        """
        List all dining options
        """
        self.update_auth_header({"Toast-Restaurant-External-ID": restaurant_id})

        try:
            response = self.request("GET", "config/v2/diningOptions")
            response.raise_for_status()

        except HTTPError as e:
            raise UserException(f"Error while getting dining options: {_parse_http_error(e)}")

        return response.json()

    @retry_on_transient_error(max_retries=3, initial_backoff=0.5)
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
