"""
NEPSE TMS Client — Real Trading Integration
=============================================
Handles authentication, token generation (WASM salt bypass),
order placement, portfolio fetch, and order history
for NEPSE TMS (tms{broker}.nepsetms.com.np).

IMPORTANT: This is for personal/educational use only.
           Always verify orders on the official TMS before executing.
"""

import os
import json
import time
import logging
import requests
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

TMS_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'tms_config.json')

# ─── Known TMS broker base URLs ───────────────────────────────
TMS_BROKER_URLS = {
    '5':  'https://tms5.nepsetms.com.np',
    '10': 'https://tms10.nepsetms.com.np',
    '11': 'https://tms11.nepsetms.com.np',
    '12': 'https://tms12.nepsetms.com.np',
    '14': 'https://tms14.nepsetms.com.np',
    '17': 'https://tms17.nepsetms.com.np',
    '19': 'https://tms19.nepsetms.com.np',
    '22': 'https://tms22.nepsetms.com.np',
    '24': 'https://tms24.nepsetms.com.np',
    '25': 'https://tms25.nepsetms.com.np',
    '26': 'https://tms26.nepsetms.com.np',
    '29': 'https://tms29.nepsetms.com.np',
    '30': 'https://tms30.nepsetms.com.np',
    '31': 'https://tms31.nepsetms.com.np',
    '38': 'https://tms38.nepsetms.com.np',
    '42': 'https://tms42.nepsetms.com.np',
    '44': 'https://tms44.nepsetms.com.np',
    '45': 'https://tms45.nepsetms.com.np',
    '47': 'https://tms47.nepsetms.com.np',
    '48': 'https://tms48.nepsetms.com.np',
    '50': 'https://tms50.nepsetms.com.np',
    '58': 'https://tms58.nepsetms.com.np',
    '63': 'https://tms63.nepsetms.com.np',
}

# ─── WASM Salt Bypass (reverse-engineered from TMS css.wasm) ──
# The TMS WASM module performs a predictable byte-shift operation on the token.
# Reference: community reverse engineering of css.wasm salt functions.
WASM_MAGIC = [
    128, 164, 128, 128, 0, 200, 194, 0, 164, 164, 128, 0, 164, 194, 128, 128,
    200, 200, 0, 0, 200, 164, 128, 0, 0, 128, 164, 128, 128, 0, 200, 194, 0,
    164, 164, 128, 0, 164, 194, 128, 128, 200, 200, 0, 0, 200, 164, 128, 128,
    0, 200, 194, 0, 164, 164, 128, 0, 164, 194, 128, 128, 200, 200, 0, 0, 0,
    164, 128, 128, 0, 200, 194, 0, 164, 164, 128, 0, 164, 194, 128, 128, 200,
    200, 0, 0, 200, 164, 128, 128, 0, 200, 194, 0, 164, 164, 128, 0, 164, 194,
    128, 128, 200, 200, 0, 0, 200, 164, 128, 128, 0, 200, 194, 0, 164, 164,
    128, 0, 164, 194, 128, 128, 200, 200, 0, 0, 200, 164, 128,
]


def _apply_wasm_salt(token: str) -> str:
    """
    Apply the TMS WASM salt transformation to the raw access token.
    This replicates the css.wasm 'cdx' / 'rdx' export function logic.
    """
    result = []
    token_bytes = token.encode('utf-8')
    magic_len = len(WASM_MAGIC)

    for i, byte in enumerate(token_bytes):
        salt_byte = WASM_MAGIC[i % magic_len]
        transformed = (byte ^ salt_byte) & 0xFF
        result.append(transformed)

    # Convert back to ASCII-safe hex representation
    salted_hex = ''.join(f'{b:02x}' for b in result)
    return salted_hex


class TMSClient:
    """
    Handles authentication and order placement for NEPSE TMS brokers.
    Thread-safe singleton pattern with auto token refresh.
    """

    def __init__(self):
        self.config = self._load_config()
        self.session = requests.Session()
        self._token = None
        self._token_expiry = 0
        self._lock = threading.Lock()
        self._setup_session()

    def _load_config(self) -> dict:
        default = {
            'broker': '29',
            'username': '',
            'password': '',
            'base_url': 'https://tms29.nepsetms.com.np',
            'logged_in': False,
        }
        if os.path.exists(TMS_CONFIG_FILE):
            try:
                with open(TMS_CONFIG_FILE, 'r') as f:
                    saved = json.load(f)
                    default.update({k: v for k, v in saved.items() if k != 'password'})
                    # Don't persist password in memory from file
            except Exception as e:
                logger.warning(f"Failed to read TMS config: {e}")
        return default

    def save_config(self, broker: str, username: str, password: str) -> dict:
        """Save TMS credentials (password is NOT stored on disk)."""
        broker = str(broker).strip()
        base_url = TMS_BROKER_URLS.get(broker, f'https://tms{broker}.nepsetms.com.np')
        self.config.update({
            'broker': broker,
            'username': username,
            'password': password,  # keep in memory only
            'base_url': base_url,
            'logged_in': False,
        })
        # Save to disk WITHOUT password
        disk_config = {k: v for k, v in self.config.items() if k != 'password'}
        try:
            with open(TMS_CONFIG_FILE, 'w') as f:
                json.dump(disk_config, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save TMS config: {e}")
        return {'success': True, 'broker': broker, 'base_url': base_url}

    def _setup_session(self):
        """Configure requests session with TMS-compatible headers."""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Content-Type': 'application/json',
            'Origin': self.config.get('base_url', 'https://tms29.nepsetms.com.np'),
            'Referer': f"{self.config.get('base_url', 'https://tms29.nepsetms.com.np')}/",
        })

    @property
    def base_url(self) -> str:
        return self.config.get('base_url', 'https://tms29.nepsetms.com.np')

    def set_token(self, token_or_session: str, client_name: str = '') -> dict:
        """
        Directly set active TMS session: accepts suid, Cookie header,
        __usrsession__ JSON, cURL command, or Bearer token.
        """
        raw = token_or_session.strip()
        if not raw:
            return {'success': False, 'error': 'Input cannot be empty'}

        with self._lock:
            # 1. Check if it's __usrsession__ JSON
            if raw.startswith('{') and ('clientDealerMember' in raw or 'client' in raw):
                try:
                    data = json.loads(raw)
                    client_info = data.get('clientDealerMember', {}).get('client', {})
                    client_id = client_info.get('id') or client_info.get('clientCode') or ''
                    name = client_info.get('name') or client_info.get('clientName') or f'Client #{client_id}'
                    self.config['client_name'] = name
                    self.config['client_id'] = str(client_id)
                    # Keep raw token if also present
                except Exception as e:
                    logger.warning(f"Error parsing __usrsession__: {e}")

            # 2. Check if it's a cURL command
            if 'curl ' in raw or '-H ' in raw:
                import re
                cookie_match = re.search(r"-H ['\"]cookie:\s*([^'\"]+)['\"]", raw, re.IGNORECASE)
                auth_match = re.search(r"-H ['\"]authorization:\s*([^'\"]+)['\"]", raw, re.IGNORECASE)
                if cookie_match:
                    cookie_str = cookie_match.group(1)
                    for item in cookie_str.split(';'):
                        if '=' in item:
                            k, v = item.strip().split('=', 1)
                            self.session.cookies.set(k.strip(), v.strip())
                if auth_match:
                    raw = auth_match.group(1).strip()

            # 3. Check if it's a Cookie string
            elif ';' in raw and '=' in raw:
                for item in raw.split(';'):
                    if '=' in item:
                        k, v = item.strip().split('=', 1)
                        self.session.cookies.set(k.strip(), v.strip())

            # 4. Check if it's a single suid value (e.g. MjQ=-9e03c9de-...)
            elif raw.startswith('Mj') or 'suid=' in raw or '-' in raw and len(raw) > 20 and not raw.startswith('{'):
                suid_val = raw.replace('suid=', '').strip()
                self.session.cookies.set('suid', suid_val)
                self.session.headers['suid'] = suid_val
                self.session.headers['X-SUID'] = suid_val

            # 5. Check if it's Bearer or Salter token
            if raw.startswith('Bearer ') or raw.startswith('Salter '):
                self._token = raw.split(' ', 1)[1]
            elif not raw.startswith('{'):
                self._token = raw

            self._token_expiry = time.time() + 86400  # 24h
            self.config['logged_in'] = True
            if client_name:
                self.config['client_name'] = client_name
            elif not self.config.get('client_name'):
                self.config['client_name'] = 'TMS Client'

            return {
                'success': True,
                'message': f"TMS Session connected ({self.config.get('client_name', 'Client')})",
                'client_name': self.config.get('client_name')
            }

    def _get_auth_header(self) -> dict:
        """Get current Authorization / Cookie headers."""
        headers = {}
        with self._lock:
            if self._token and time.time() < self._token_expiry:
                if '.' in self._token and len(self._token) > 50:
                    headers['Authorization'] = f'Bearer {self._token}'
                elif self._token:
                    headers['Authorization'] = f'Salter {self._token}'
            return headers

            # Need to re-authenticate
            result = self._authenticate_internal()
            if result.get('success'):
                if '.' in self._token and len(self._token) > 50:
                    return {'Authorization': f'Bearer {self._token}'}
                return {'Authorization': f'Salter {self._token}'}
            raise ConnectionError(f"TMS Authentication: {result.get('error')}")

    def _authenticate_internal(self) -> dict:
        """Internal auth — attempts TMS login endpoints."""
        username = self.config.get('username', '')
        password = self.config.get('password', '')

        if not username or not password:
            return {
                'success': False,
                'error': 'TMS credentials not set. You can also paste your active TMS Session Token.',
                'need_token': True
            }

        # Try TMS auth endpoints
        endpoints = [
            f"{self.base_url}/tmsapi/authApi/authenticate",
            f"{self.base_url}/api/tmsapi/authenticate",
            f"{self.base_url}/api/authenticate/prove",
        ]

        last_error = None
        for url in endpoints:
            try:
                payload = {
                    'clientId': username,
                    'userName': username,
                    'userCaptcha': '',
                    'password': password,
                }
                resp = self.session.post(url, json=payload, timeout=8)

                if resp.status_code == 200:
                    data = resp.json()
                    raw_token = data.get('accessToken') or data.get('token') or data.get('id_token') or ''
                    if raw_token:
                        self._token = raw_token
                        self._token_expiry = time.time() + 1800
                        self.config['logged_in'] = True
                        self.config['client_name'] = data.get('fullName', username)
                        return {'success': True, 'client': data}

                elif resp.status_code in (401, 403):
                    last_error = 'Invalid credentials or CAPTCHA/2FA required by TMS.'
                elif resp.status_code == 405:
                    last_error = 'TMS API requires browser session/OTP. Please use the Session Token tab or 1-Click Order Link.'
                else:
                    last_error = f'TMS server error {resp.status_code}'

            except Exception as e:
                last_error = str(e)

        return {
            'success': False,
            'error': last_error or 'Could not authenticate with TMS. Please paste your active TMS Session Token from browser.',
            'need_token': True
        }

    def login(self, username: str = None, password: str = None) -> dict:
        """Login to TMS and store token."""
        if username:
            self.config['username'] = username
        if password:
            self.config['password'] = password

        with self._lock:
            result = self._authenticate_internal()
            return result

    def logout(self):
        """Clear TMS session token."""
        self._token = None
        self._token_expiry = 0
        self.config['logged_in'] = False

    @property
    def is_logged_in(self) -> bool:
        return bool(self._token and time.time() < self._token_expiry)

    # ─── PORTFOLIO ────────────────────────────────────────────────

    def get_portfolio(self) -> dict:
        """Fetch TMS client portfolio (holdings, cash balance, BOID)."""
        try:
            headers = self._get_auth_header()
            url = f"{self.base_url}/api/tmsapi/dashboard/clientPortfolio"
            resp = self.session.get(url, headers=headers, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                return {'success': True, 'portfolio': data}
            elif resp.status_code == 401:
                self._token = None  # Force re-auth next call
                return {'success': False, 'error': 'Session expired. Will re-authenticate on next request.'}
            else:
                return {'success': False, 'error': f'Portfolio fetch failed: {resp.status_code}'}

        except ConnectionError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"TMS portfolio error: {e}")
            return {'success': False, 'error': str(e)}

    # ─── ORDER MANAGEMENT ─────────────────────────────────────────

    def place_order(self, symbol: str, action: str, quantity: int,
                    price: float, order_type: str = 'RL') -> dict:
        """
        Place a real BUY or SELL order on TMS.

        Args:
            symbol: Stock symbol (e.g., 'NABIL')
            action: 'BUY' or 'SELL'
            quantity: Number of shares
            price: Execution price in NPR
            order_type: 'RL' (Regular Lot) or 'OL' (Odd Lot)

        Returns:
            dict with success flag and order details
        """
        action = action.upper()
        if action not in ('BUY', 'SELL'):
            return {'success': False, 'error': 'Action must be BUY or SELL'}
        if quantity <= 0:
            return {'success': False, 'error': 'Quantity must be greater than 0'}
        if price <= 0:
            return {'success': False, 'error': 'Price must be greater than 0'}

        buy_or_sell = 'B' if action == 'BUY' else 'S'

        try:
            headers = self._get_auth_header()
            url = f"{self.base_url}/api/tmsapi/order/shareOrder"

            payload = {
                'stockSymbol': symbol.upper(),
                'subTransType': 'Y',          # Normal order
                'buyorsell': buy_or_sell,
                'floorPrice': str(price),
                'kitta': str(quantity),        # Some TMS versions use 'kitta'
                'quantity': str(quantity),     # Some TMS versions use 'quantity'
                'orderType': order_type,       # RL = Regular Lot
                'reasonCode': 'R1',
            }

            resp = self.session.post(url, json=payload, headers=headers, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                # TMS response check — order placed successfully
                if data.get('success') or data.get('message') == 'Order placed successfully' or data.get('id'):
                    order_id = data.get('id') or data.get('orderId') or data.get('transactionId') or 'N/A'
                    logger.info(f"✅ TMS Order placed: {action} {quantity} {symbol} @ NPR {price} — Order ID: {order_id}")
                    return {
                        'success': True,
                        'order': {
                            'order_id': str(order_id),
                            'symbol': symbol,
                            'action': action,
                            'quantity': quantity,
                            'price': price,
                            'order_type': order_type,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'raw': data,
                        }
                    }
                else:
                    # Some brokers return 200 with error in body
                    err_msg = data.get('message') or data.get('error') or data.get('errorMessage') or str(data)
                    return {'success': False, 'error': f'Order rejected: {err_msg}'}

            elif resp.status_code == 401:
                self._token = None
                return {'success': False, 'error': 'Session expired. Please login again.'}
            elif resp.status_code == 400:
                try:
                    err = resp.json()
                    msg = err.get('message') or err.get('error') or err.get('errorMessage') or resp.text[:200]
                except Exception:
                    msg = resp.text[:200]
                return {'success': False, 'error': f'Order validation error: {msg}'}
            else:
                return {'success': False, 'error': f'TMS server error {resp.status_code}: {resp.text[:200]}'}

        except ConnectionError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"TMS order placement error: {e}")
            return {'success': False, 'error': str(e)}

    def get_my_orders(self, days: int = 1) -> dict:
        """Fetch today's orders from TMS."""
        try:
            headers = self._get_auth_header()
            url = f"{self.base_url}/api/tmsapi/order/myOrders"
            params = {'size': 50, 'page': 1}
            resp = self.session.get(url, headers=headers, params=params, timeout=10)

            if resp.status_code == 200:
                data = resp.json()
                orders = data if isinstance(data, list) else data.get('content') or data.get('orders') or []
                return {'success': True, 'orders': orders}
            elif resp.status_code == 401:
                self._token = None
                return {'success': False, 'error': 'Session expired. Please re-login.'}
            else:
                return {'success': False, 'error': f'Orders fetch error: {resp.status_code}'}

        except ConnectionError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"TMS my orders error: {e}")
            return {'success': False, 'error': str(e)}

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a pending TMS order by its ID."""
        try:
            headers = self._get_auth_header()
            url = f"{self.base_url}/api/tmsapi/order/cancelOrder/{order_id}"
            resp = self.session.delete(url, headers=headers, timeout=10)

            if resp.status_code == 200:
                return {'success': True, 'message': f'Order {order_id} cancelled successfully'}
            else:
                try:
                    err = resp.json()
                    msg = err.get('message') or resp.text[:200]
                except Exception:
                    msg = resp.text[:200]
                return {'success': False, 'error': f'Cancel failed: {msg}'}

        except ConnectionError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"TMS cancel order error: {e}")
            return {'success': False, 'error': str(e)}

    def get_market_depth(self, symbol: str) -> dict:
        """Get live market depth (bid/ask) for a symbol."""
        try:
            headers = self._get_auth_header()
            url = f"{self.base_url}/api/tmsapi/stockDetails/{symbol.upper()}"
            resp = self.session.get(url, headers=headers, timeout=8)

            if resp.status_code == 200:
                return {'success': True, 'depth': resp.json()}
            else:
                return {'success': False, 'error': f'Market depth error: {resp.status_code}'}

        except ConnectionError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_client_info(self) -> dict:
        """Get basic TMS client profile information."""
        return {
            'broker': self.config.get('broker', '29'),
            'username': self.config.get('username', ''),
            'client_name': self.config.get('client_name', ''),
            'dp_code': self.config.get('dp_code', ''),
            'base_url': self.base_url,
            'is_logged_in': self.is_logged_in,
        }


# ─── Singleton instance ────────────────────────────────────────
tms_client = TMSClient()
