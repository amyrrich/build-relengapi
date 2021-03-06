# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from relengapi.lib import time
from nose.tools import eq_
import pytz


def test_now():
    n = time.now()
    eq_(n.tzinfo, pytz.UTC)
