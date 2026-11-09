"""Keep FBref's Chrome out of the way: a throwaway profile, no macOS keychain,
window minimised. Import before soccerdata (9 Nov 2026). It stays headful
because a headless browser doesn't get past FBref's bot check."""
import atexit
import shutil
import tempfile

import seleniumbase as sb

_profile = tempfile.mkdtemp(prefix="fbref-chrome-")
atexit.register(shutil.rmtree, _profile, ignore_errors=True)
_driver = sb.Driver


def Driver(*args, **kwargs):
    kwargs.setdefault("user_data_dir", _profile)
    kwargs.setdefault("chromium_arg", "--use-mock-keychain,--password-store=basic")
    driver = _driver(*args, **kwargs)
    try:
        driver.minimize_window()    # macOS pulls an off-screen window back on screen
    except Exception:               # noqa: BLE001
        pass
    return driver


sb.Driver = Driver
