'''
Created on 12. 11. 2018

@author: esner
'''
import unittest
import mock
import os
import datetime
from freezegun import freeze_time

from component import Component
from client import ToastClient


class TestComponent(unittest.TestCase):

    # set global time to 2010-10-10 - affects functions like datetime.now()
    @freeze_time("2010-10-10")
    # set KBC_DATADIR env to non-existing dir
    @mock.patch.dict(os.environ, {'KBC_DATADIR': './non-existing-dir'})
    def test_run_no_cfg_fails(self):
        with self.assertRaises(ValueError):
            comp = Component()
            comp.run()


class TestTransientErrorRetry(unittest.TestCase):
    """Test that transient network errors (ConnectionResetError) are retried."""

    @mock.patch.object(ToastClient, 'request')
    @mock.patch.object(ToastClient, 'update_auth_header')
    @mock.patch.object(ToastClient, 'get_token', return_value='fake_token')
    def test_list_restaurants_retries_on_connection_reset(self, mock_get_token, mock_update_auth, mock_request):
        """Verify list_restaurants retries on ConnectionResetError and succeeds on retry."""
        # First call raises ConnectionResetError, second call succeeds
        success_response = mock.MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = [{'restaurantGuid': 'guid1'}]
        success_response.raise_for_status = mock.MagicMock()

        mock_request.side_effect = [
            ConnectionResetError(104, 'Connection reset by peer'),
            success_response
        ]

        client = ToastClient('client_id', 'client_secret', 'http://api.example.com')

        # This should NOT raise; the retry should succeed on the second attempt
        result = client.list_restaurants()

        # Verify we got the mocked response and request was called twice (first failed, second succeeded)
        self.assertEqual(mock_request.call_count, 2)
        self.assertEqual(result, [{'restaurantGuid': 'guid1'}])

    @mock.patch.object(ToastClient, 'request')
    @mock.patch.object(ToastClient, 'update_auth_header')
    @mock.patch.object(ToastClient, 'get_token', return_value='fake_token')
    def test_list_orders_retries_then_fails_after_max_retries(self, mock_get_token, mock_update_auth, mock_request):
        """Verify list_orders retries up to max_retries and then re-raises."""
        # All calls raise ConnectionResetError
        mock_request.side_effect = ConnectionResetError(104, 'Connection reset by peer')

        client = ToastClient('client_id', 'client_secret', 'http://api.example.com')

        # This should raise after exhausting retries
        with self.assertRaises(ConnectionResetError):
            list(client.list_orders('restaurant_id', datetime.datetime(2010, 1, 1), datetime.datetime(2010, 1, 2)))

        # Verify request was called max_retries + 1 times (3 + 1 = 4)
        self.assertEqual(mock_request.call_count, 4)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
