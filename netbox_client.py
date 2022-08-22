import requests
from pynetbox.core.api import Api
from pynetbox.core.query import RequestError
from requests.adapters import HTTPAdapter


class TimeoutHTTPAdapter(HTTPAdapter):
    """
    There are no other ways to change request timeout to netbox.
    https://pynetbox.readthedocs.io/en/latest/advanced.html#timeouts
    """

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get('timeout', 5)
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        kwargs['timeout'] = self.timeout
        return super().send(request, **kwargs)


class NetboxClient(Api):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        adapter = TimeoutHTTPAdapter()
        session = requests.Session()
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        self.http_session = session

    def get_device(self, hostname: str):
        try:
            return self.dcim.devices.get(name=hostname)
        except requests.exceptions.ConnectTimeout:
            raise SystemExit(f'Netbox connection timeout: {self.base_url}') from None
        except requests.exceptions.ConnectionError:
            raise SystemExit(f'Unable to connect to Netbox: {self.base_url}') from None
        except RequestError as e:
            raise SystemExit(e) from None
