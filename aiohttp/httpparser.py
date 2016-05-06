"""httptools integration"""
import re
from httptools import HttpRequestParser
from multidict import CIMultiDict, upstr

from . import errors, hdrs
from .protocol import VERSRE, RawRequestMessage, DeflateBuffer
from .protocol import HttpVersion, HttpVersion10, HttpVersion11
from .parsers import _ParserBufferHelper

VERSRE = re.compile('(\d+).(\d+)')


class HttpParser:

    def __init__(self, compression=True):
        self._proto = HttpProtocol()
        self._parser = HttpRequestParser(self._proto)
        self._processed = 0
        self._compression = compression
        self._headers_completed = False

    def __call__(self, out, buf):
        self._out = out
        self._buf = buf
        self._processed = 0

        if not self._headers_completed:
            print ('Start Headers processing =====: ')
        else:
            print ('Start Body processing =====: ')
        
        # payload decompression wrapper
        if (self._headers_completed and
                self._compression and self._proto.encoding):
            self._out = DeflateBuffer(out, self._proto.encoding)

        return self

    def send(self, data):
        print ('Data =====: ', data)
        if data:
            self._parser.feed_data(data)

        self._processed += len(data)

        if not self._headers_completed:
            if self._proto.headers_completed:
                # version
                ver = self._parser.get_http_version()
                match = VERSRE.match(ver)
                if match is None:
                    raise errors.BadStatusLine(ver)
                version = HttpVersion(int(match.group(1)), int(match.group(2)))

                path, headers, raw_headers, close_conn, encoding = (
                    self._proto.url, self._proto.headers,
                    self._proto.raw_headers,
                    self._proto.close_conn, self._proto.encoding)
                print ('Done Headers =====: ', path, headers, raw_headers,
                       close_conn, encoding)

                method = self._parser.get_method().decode(
                    'utf-8', 'surrogateescape')
                self._out.feed_data(
                    RawRequestMessage(
                        method, path, version, headers,
                        raw_headers, close_conn, encoding),
                    self._processed)
                self._out.feed_eof()

                self._out = None
                self._buf = None
                self._processed = 0
                self._headers_completed = True
                raise StopIteration
        else:
            print ('Feed body =====: ', self._proto.body, self._proto.message_completed)

            for chunk in self._proto.body:
                self._out.feed_data(chunk, len(chunk))
            self._proto.body.clear()

            if self._proto.message_completed:
                self._out.feed_eof()
                raise StopIteration

    def __next__(self):
        buf = self._buf
        print ('Next ====: ', buf._data)

        try:
            self.send(buf._data)

            buf._data.clear()
            buf._helper = _ParserBufferHelper(None, buf._data)
            buf._writer = buf._feed_data(buf._helper)
            next(buf._writer)
        except StopIteration:
            buf._data.clear()
            buf._helper = _ParserBufferHelper(None, buf._data)
            buf._writer = buf._feed_data(buf._helper)
            next(buf._writer)

            raise


class HttpProtocol:

    def __init__(self):
        self.path = ''
        self.close_conn = None
        self.encoding = None
        self.headers = CIMultiDict()
        self.raw_headers = []
        self.body = []

        self.headers_completed = False
        self.message_completed = False

    def on_header(self, bname, bvalue):
        print ('on_header =====: ', bname, bvalue)

        name = bname.decode('utf-8', 'surrogateescape')
        value = bvalue.decode('utf-8', 'surrogateescape')

        # keep-alive and encoding
        if name == hdrs.CONNECTION:
            v = value.lower()
            if v == 'close':
                self.close_conn = True
            elif v == 'keep-alive':
                self.close_conn = False
        elif name == hdrs.CONTENT_ENCODING:
            enc = value.lower()
            if enc in ('gzip', 'deflate'):
                self.encoding = enc

        self.headers.add(name, value)
        self.raw_headers.append((bname, bvalue))

    def on_headers_complete(self):
        print ('on_headers_complete =====: ')
        self.headers_completed = True

    def on_url(self, url):
        self.url = url.decode('utf-8', 'surrogateescape')
        print ('on_url =====: ', url)

    def on_body(self, body):
        self.body.append(body)
        print ('on_body =====: ', body)
    
    def on_message_complete(self):
        self.message_completed = True
        print ('on_message_complete =====: ')

    def on_chunk_header(self):
        print ('on_chunk_header =====: ')

    def on_chunk_complete(self):
        print ('on_chunk_complete =====: ')