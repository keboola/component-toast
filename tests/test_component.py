'''
Created on 12. 11. 2018

@author: esner
'''
import datetime
import unittest
import mock
import os
from freezegun import freeze_time
from requests.exceptions import ChunkedEncodingError, HTTPError

from component import Component
from client import ToastClient
from keboola.component import UserException


class TestComponent(unittest.TestCase):

    # set global time to 2010-10-10 - affects functions like datetime.now()
    @freeze_time("2010-10-10")
    # set KBC_DATADIR env to non-existing dir
    @mock.patch.dict(os.environ, {'KBC_DATADIR': './non-existing-dir'})
    def test_run_no_cfg_fails(self):
        with self.assertRaises(ValueError):
            comp = Component()
            comp.run()


def _response(payload):
    rsp = mock.MagicMock()
    rsp.json.return_value = payload
    return rsp


@mock.patch('client.time.sleep')
@mock.patch.object(ToastClient, 'get_token', return_value='token')
@mock.patch.object(ToastClient, 'request')
class TestTransientErrorRetry(unittest.TestCase):

    def _client(self):
        return ToastClient('id', 'secret', 'https://example.com/')

    def test_connection_reset_during_orders_page_is_retried(self, request, _token, sleep):
        request.side_effect = [
            ChunkedEncodingError("Connection broken: ConnectionResetError(104, 'Connection reset by peer')"),
            _response([{'guid': 'o1'}]),
            _response([]),
        ]
        batches = list(self._client().list_orders('r1', datetime.datetime(2020, 1, 1), datetime.datetime(2020, 1, 2)))

        self.assertEqual(batches, [[{'guid': 'o1'}]])
        self.assertEqual(request.call_count, 3)
        # the retried call repeats the same page
        self.assertEqual(request.call_args_list[0], request.call_args_list[1])
        sleep.assert_called_once()

    def test_persistent_connection_reset_reraises_after_retries(self, request, _token, sleep):
        request.side_effect = ConnectionResetError(104, 'Connection reset by peer')

        with self.assertRaises(ConnectionResetError):
            self._client().menus('r1')

        self.assertEqual(request.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    def test_http_error_is_not_retried(self, request, _token, sleep):
        rsp = _response({})
        rsp.raise_for_status.side_effect = HTTPError(response=mock.MagicMock(text='bad'))
        request.return_value = rsp

        with self.assertRaises(UserException):
            self._client().dining_options('r1')

        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
