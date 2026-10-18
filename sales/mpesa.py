import base64
import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from django.conf import settings


class MpesaError(Exception):
    """A safe, customer-facing M-Pesa integration error."""


def _configuration():
    environment = settings.MPESA_ENVIRONMENT
    if environment not in ('sandbox', 'production'):
        raise MpesaError('M-Pesa environment must be sandbox or production.')

    values = (
        settings.MPESA_CONSUMER_KEY,
        settings.MPESA_CONSUMER_SECRET,
        settings.MPESA_SHORTCODE,
        settings.MPESA_PASSKEY,
        settings.MPESA_CALLBACK_URL,
    )
    if not all(values):
        raise MpesaError('M-Pesa is not configured. Contact the site administrator.')

    callback = urlparse(settings.MPESA_CALLBACK_URL)
    if callback.scheme != 'https' or not callback.netloc:
        raise MpesaError('M-Pesa requires a publicly accessible HTTPS callback URL.')

    host = 'api.safaricom.co.ke' if environment == 'production' else 'sandbox.safaricom.co.ke'
    return f'https://{host}'


def _read_json(request):
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise MpesaError('Could not reach M-Pesa. Please try again.') from error

    if not isinstance(result, dict):
        raise MpesaError('M-Pesa returned an invalid response.')
    return result


def _access_token(base_url):
    credentials = f'{settings.MPESA_CONSUMER_KEY}:{settings.MPESA_CONSUMER_SECRET}'
    encoded = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
    request = Request(
        f'{base_url}/oauth/v1/generate?{urlencode({"grant_type": "client_credentials"})}',
        headers={'Authorization': f'Basic {encoded}'},
    )
    response = _read_json(request)
    token = response.get('access_token')
    if not isinstance(token, str) or not token:
        raise MpesaError('M-Pesa authentication failed. Check the configured credentials.')
    return token


def _timestamp():
    return datetime.now(ZoneInfo('Africa/Nairobi')).strftime('%Y%m%d%H%M%S')


def _password(timestamp):
    raw = f'{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}'
    return base64.b64encode(raw.encode('utf-8')).decode('ascii')


def _post_json(url, token, payload):
    request = Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    return _read_json(request)


def initiate_stk_push(payment):
    base_url = _configuration()
    token = _access_token(base_url)
    timestamp = _timestamp()
    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': _password(timestamp),
        'Timestamp': timestamp,
        'TransactionType': settings.MPESA_TRANSACTION_TYPE,
        'Amount': int(payment.amount),
        'PartyA': payment.phone_number,
        'PartyB': settings.MPESA_SHORTCODE,
        'PhoneNumber': payment.phone_number,
        'CallBackURL': settings.MPESA_CALLBACK_URL,
        'AccountReference': payment.order.order_number,
        'TransactionDesc': f'Glow Beauty order {payment.order.order_number}',
    }
    response = _post_json(f'{base_url}/mpesa/stkpush/v1/processrequest', token, payload)
    if str(response.get('ResponseCode')) != '0':
        raise MpesaError('M-Pesa could not start the payment prompt. Please try again.')

    merchant_id = response.get('MerchantRequestID')
    checkout_id = response.get('CheckoutRequestID')
    if not merchant_id or not checkout_id:
        raise MpesaError('M-Pesa returned an incomplete payment reference.')
    return str(merchant_id), str(checkout_id)


def query_stk_status(checkout_request_id):
    base_url = _configuration()
    token = _access_token(base_url)
    timestamp = _timestamp()
    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': _password(timestamp),
        'Timestamp': timestamp,
        'CheckoutRequestID': checkout_request_id,
    }
    response = _post_json(f'{base_url}/mpesa/stkpushquery/v1/query', token, payload)
    if str(response.get('ResponseCode')) != '0' or 'ResultCode' not in response:
        raise MpesaError('M-Pesa has not returned a final payment result yet.')
    return str(response['ResultCode'])
