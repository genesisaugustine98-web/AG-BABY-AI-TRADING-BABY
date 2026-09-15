"""Optional MT5 adapter. Secrets are read from environment; demo proof is fail-closed."""
import os
from typing import Any

class DemoOnlyMT5Gateway:
    def __init__(self):
        self.server=os.environ.get('MT5_SERVER','')
        self.allowed_server=os.environ.get('MT5_DEMO_SERVER','')
        self.login=os.environ.get('MT5_LOGIN','')
        self.password=os.environ.get('MT5_PASSWORD','')
        self.terminal=os.environ.get('MT5_TERMINAL_PATH','')
        self.connected=False
    def _import(self):
        import MetaTrader5 as mt5
        return mt5
    def connect_and_verify_demo(self) -> dict[str, Any]:
        if os.environ.get('EXECUTION_ENV','demo') != 'demo': raise RuntimeError('execution env must be demo')
        if not self.server or not self.allowed_server or self.server != self.allowed_server:
            raise RuntimeError('refusing connection: server not on demo allowlist')
        if not self.login or not self.password: raise RuntimeError('missing credentials')
        mt5=self._import()
        kwargs={'login':int(self.login),'password':self.password,'server':self.server,'timeout':60000}
        if self.terminal: ok=mt5.initialize(self.terminal, **kwargs)
        else: ok=mt5.initialize(**kwargs)
        if not ok: raise RuntimeError(f'initialize failed: {mt5.last_error()}')
        acct=mt5.account_info()
        if acct is None: mt5.shutdown(); raise RuntimeError('account info unavailable')
        explicit_demo = getattr(acct, 'trade_mode', None) is not None and str(getattr(acct, 'trade_mode')) in {'0', 'ACCOUNT_TRADE_MODE_DEMO'}
        if not explicit_demo:
            mt5.shutdown(); raise RuntimeError('could not positively prove demo account')
        self.connected=True
        return {'login':acct.login,'server':acct.server,'trade_allowed':acct.trade_allowed}
    def shutdown(self):
        if self.connected:
            self._import().shutdown(); self.connected=False
