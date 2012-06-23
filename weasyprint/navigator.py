# coding: utf8
"""
    weasyprint.navigator
    --------------------

    A WeasyPrint-based web browser. In your web browser.

    :copyright: Copyright 2011-2012 Simon Sapin and contributors, see AUTHORS.
    :license: BSD, see LICENSE for details.

"""

# Do NOT import unicode_literals here. Raw WSGI requires native strings.
from __future__ import division

import io
import os.path
import base64

import cairo

from weasyprint import HTML, CSS
from weasyprint.formatting_structure import boxes
from weasyprint.urls import url_is_absolute
from weasyprint.compat import izip, parse_qs


FAVICON = os.path.join(os.path.dirname(__file__),
                       'tests', 'resources', 'icon.png')

STYLESHEET = CSS(string='''
   :root { font-size: 10pt }
''')


def find_links(box, links, anchors):
    link = box.style.link
    # 'link' is inherited but redundant on text boxes
    if link and not isinstance(box, boxes.TextBox):
        type_, href = box.style.link
        if type_ == 'internal':
            href = '#' + href
        else:
            href = '/view/' + href
        # "Border area.  That's the area that hit-testing is done on."
        # http://lists.w3.org/Archives/Public/www-style/2012Jun/0318.html
        links.append((href,) + box.hit_area())

    anchor = box.style.anchor
    if anchor:
        anchors.append((anchor,) + box.hit_area())

    if isinstance(box, boxes.ParentBox):
        for child in box.children:
            find_links(child, links, anchors)


def get_pages(html):
    document, png_pages = html.get_png_pages([STYLESHEET], _with_document=True)
    for page, (width, height, png_bytes) in izip(document.pages, png_pages):
        links = []
        anchors = []
        find_links(page, links, anchors)
        data_url = 'data:image/png;base64,' + (
            base64.encodestring(png_bytes).decode('ascii').replace('\n', ''))
        yield width, height, data_url, links, anchors


def render_template(url):
    parts = ['''\
<!doctype html>
<meta charset=utf-8>
<title>WeasyPrint Navigator</title>
<style>
  form { position: fixed; z-index: 1; top: 8px; left: 16px; right: 0; }
  input { font: 24px/30px sans-serif }
  input:not([type]) { background: rgba(255, 255, 255, .9); border-width: 2px;
                      border-radius: 6px; padding: 0 3px }
  input:not([type]):focus { outline: none }
  body { margin-top: 0; padding-top: 50px }
  section { box-shadow: 0 0 10px 2px #aaa; margin: 25px; position: relative }
  section a { position: absolute; display: block }
  section a[href]:hover, a[href]:focus { outline: 1px dotted }
</style>
<body onload="var u=document.forms[0].url; u.value || u.focus()">
<form action="/" onsubmit="
  window.location.href = '/view/' + this.url.value; return false;">
<input name=url style="width: 80%" placeholder="Enter an URL to start"
  value="''']
    write = parts.append
    if url:
        html = HTML(url)
        url = html.base_url
        write(url)
    write('" />\n<input type=submit value=Go />\n')
    if url:
        write('<a href="/pdf/')
        write(url)
        write('">PDF</a>\n')
    write('</form>\n')
    if url:
        for width, height, data_url, links, anchors in get_pages(html):
            write('<section style="width: {0}px; height: {1}px">\n'
                  '  <img src="{2}">\n'.format(width, height, data_url))
            for href, pos_x, pos_y, width, height in links:
                write('  <a style="left: {0}px; top: {1}px; '
                      'width: {2}px; height: {3}px" href="{4}"></a>\n'
                      .format(pos_x, pos_y, width, height, href))
            for anchor, pos_x, pos_y, width, height in anchors:
                # Remove 60px to pos_y so that the real pos is below
                # the address bar.
                write('  <a style="left: {0}px; top: {1}px;" name="{2}"></a>\n'
                      .format(pos_x, pos_y - 60, anchor))
            write('</section>\n')
    return ''.join(parts).encode('utf8')


def normalize_url(url, query_string=None):
    if url:
        if query_string:
            url += '?' + query_string
        if not url_is_absolute(url):
            # Default to HTTP rather than relative filenames
            url = 'http://' + url
        return url


def app(environ, start_response):
    def make_response(body, status='200 OK',
                      content_type='text/html; charset=UTF-8'):
        start_response(status, [
            ('Content-Type', content_type),
            ('Content-Length', str(len(body))),
        ])
        return [body]

    path = environ['PATH_INFO']

    if path == '/favicon.ico':
        with open(FAVICON, 'rb') as fd:
            return make_response(fd.read(), content_type='image/x-icon')

    elif path.startswith('/pdf/') and len(path) > 5: # len('/pdf/') == 5
        url = normalize_url(path[5:], environ.get('QUERY_STRING'))
        body = HTML(url=url).write_pdf(stylesheets=[STYLESHEET])
        return make_response(body, content_type='application/pdf')

    elif path.startswith('/view/'):
        url = normalize_url(path[6:], environ.get('QUERY_STRING'))
        return make_response(render_template(url))

    elif path == '/':
        args = parse_qs(environ.get('QUERY_STRING', ''))
        url = normalize_url(args.get('url', [''])[0])
        return make_response(render_template(url))

    return make_response(b'<h1>Not Found</h1>', status='404 Not Found')

def run(port=5000):
    host = '127.0.0.1'
    try:
        from werkzeug.serving import run_simple
    except ImportError:
        pass
    else:
        run_simple(host, port, app, use_reloader=True, use_debugger=True)
        return
    print('Could not import Werkzeug, running without the reloader '
          'or debugger.')
    from wsgiref.simple_server import make_server
    server = make_server(host, port, app)
    print('Listening on http://%s:%s/ ...' % (host, port))
    server.serve_forever()


if __name__ == '__main__':
    run()