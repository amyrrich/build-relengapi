# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import sys
import mock
from flask import json
from flask import redirect
from nose.tools import eq_
from nose.tools import assert_raises
from relengapi.lib import api
from relengapi.lib.permissions import p
from relengapi import testing
import wsme.types
from werkzeug.exceptions import BadRequest


p.test_api.doc('test permission')


def app_setup(app):
    @app.route('/apimethod/ok')
    @api.apimethod([unicode])
    def ok():
        return ['ok']

    @app.route('/apimethod/fail')
    @api.apimethod(unicode)
    def fail():
        raise BadRequest

    @app.route('/apimethod/201')
    @api.apimethod([unicode])
    def ok_201():
        return ['ok'], 201

    @app.route('/apimethod/201/header')
    @api.apimethod([unicode])
    def ok_201_header():
        return ['ok'], 201, {'X-Header': 'Header'}

    @app.route('/apimethod/header')
    @api.apimethod([unicode])
    def ok_header():
        return ['ok'], {'X-Header': 'Header'}

    @app.route('/get_data')
    @api.apimethod(unicode)
    def get_some_data():
        return repr(api.get_data(ok))

    @app.route('/apimethod/notallowed')
    @p.test_api.require()
    def notallowed():
        pass

    @app.route('/get_data/notallowed')
    @api.apimethod(unicode)
    def get_some_data_notallowed():
        return repr(api.get_data(notallowed))

    @app.route('/redirect')
    @api.apimethod(unicode)
    def return_response():
        return redirect('/foo')


test_context = testing.TestContext(app_setup=app_setup, reuse_app=True)


def test_get_handler():
    @mock.patch('relengapi.util.is_browser')
    def t(util_is_browser, is_browser, expected):
        util_is_browser.return_value = is_browser
        eq_(str(api._get_handler().media_type), expected)

    yield lambda: t(is_browser=True, expected='text/html')
    yield lambda: t(is_browser=False, expected='application/json')


@test_context
def test_JsonHandler_render_response(app):
    h = api.JsonHandler()
    with app.test_request_context():
        eq_(json.loads(h.render_response([1, 2, 3], 200, {}).data),
            {'result': [1, 2, 3]})


@test_context
def test_JsonHandler_handle_exception_httpexception(app):
    """JsonHandler handles HTTP exceptions with an error response containing
    information about the status code"""
    h = api.JsonHandler()
    with app.test_request_context():
        try:
            raise BadRequest()
        except Exception:
            resp = h.handle_exception(*sys.exc_info())
            eq_(resp.status_code, 400)
            eq_(json.loads(resp.data)['error']['code'], 400)
            # the message comes from Werkzeug and might change, so
            # it's not tested


@test_context
def test_JsonHandler_handle_exception(app):
    """JsonHandler handles regular exceptions with an error response"""
    h = api.JsonHandler()
    with app.test_request_context():
        app.debug = True
        # mock out log_exception, since it prints to stdout
        with mock.patch("flask.current_app.log_exception"):
            try:
                raise RuntimeError('oh noes')
            except Exception:
                resp = h.handle_exception(*sys.exc_info())
                eq_(resp.status_code, 500)
                data = json.loads(resp.data)
                eq_(data['error']['code'], 500)
                assert 'oh noes' in data['error']['description']


@test_context
def test_HtmlHandler_render_response(app):
    h = api.HtmlHandler()
    with app.test_request_context():
        resp = h.render_response([1, 2, 3], 200, {})
        assert '<html' in resp.data, resp.data
        assert "1," in resp.data, resp.data


@test_context
def test_HtmlHandler_handle_exception_httpexception(app):
    """HTMLHandler passes HTTP exceptions to app.handle_http_exception"""
    h = api.HtmlHandler()
    with app.test_request_context():
        with mock.patch("flask.current_app.handle_http_exception") as hhe:
            br = BadRequest()
            try:
                raise br
            except Exception:
                h.handle_exception(*sys.exc_info())
            hhe.assert_called_with(br)


@test_context
def test_HtmlHandler_handle_exception(app):
    """HTMLHandler passes regular exceptions through to the caller"""
    h = api.HtmlHandler()
    with app.test_request_context():
        try:
            raise RuntimeError("oh noes")
        except Exception:
            # just passes through regular exceptions
            assert_raises(RuntimeError, lambda:
                          h.handle_exception(*sys.exc_info()))


def test_apimethod():
    @test_context
    def t(client, path, exp_status_code=200, exp_data=None, exp_headers=None):
        resp = client.get(path)
        eq_(resp.status_code, exp_status_code)
        eq_(json.loads(resp.data), exp_data or {'result': ['ok']})
        for k, v in (exp_headers or {}).iteritems():
            assert resp.headers[k] == v

    yield lambda: t(path='/apimethod/ok')
    yield lambda: t(path='/apimethod/fail', exp_status_code=400,
                    exp_data={'error': {
                        'code': 400,
                        'description': '<p>The browser (or proxy) sent a request that this '
                        'server could not understand.</p>',
                        'name': 'Bad Request',
                    }})
    yield lambda: t(path='/apimethod/201', exp_status_code=201)
    yield lambda: t(path='/apimethod/201/header', exp_status_code=201,
                    exp_headers={'X-Header': 'Header'})
    yield lambda: t(path='/apimethod/header', exp_headers={'X-Header': 'Header'})


@test_context
def test_apimethod_redirect(client):
    resp = client.get('/redirect')
    eq_(resp.status_code, 302)


class TestType(wsme.types.Base):
    name = unicode
    value = int


@test_context
def test_encoder(app):
    with app.test_request_context():
        eq_(json.loads(json.dumps({'x': 10})), {'x': 10})

        # check that a WSME type is properly handled
        o = TestType(name='test', value=5)
        eq_(json.loads(json.dumps(o)), {'name': 'test', 'value': 5})

        # and that such types are handled within other structures
        eq_(json.loads(json.dumps([o])), [{'name': 'test', 'value': 5}])
        eq_(json.loads(json.dumps(dict(x=o))),
            {'x': {'name': 'test', 'value': 5}})


@test_context
def test_get_data(client):
    resp = client.get('/get_data')
    eq_(json.loads(resp.data)['result'], "['ok']")


@test_context
def test_get_data_notallowed(client):
    resp = client.get('/get_data/notallowed')
    eq_(resp.status_code, 403)
