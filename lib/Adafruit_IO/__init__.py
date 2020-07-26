from .client import Client
from .errors import AdafruitIOError, RequestError, ThrottlingError
from .model import Data, Feed, Group
from async_requests import urequests as requests
__version__ = (0, 0, 1)
