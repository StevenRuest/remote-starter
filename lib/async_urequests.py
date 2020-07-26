import gc
gc.collect()
import uasyncio as asyncio
gc.collect()
import ujson
gc.collect()
gc.threshold(gc.mem_free() // 4 + gc.mem_alloc()) # sets threshold to 1/4 of heap size

HTTP_version = "1.0"
__version__ = (0, 0, 1)

# =============================================================================================================================
# ===(Class TimeoutError, ConnectionError)=====================================================================================
# =============================================================================================================================

class TimeoutError(Exception):
    pass

class ConnectionError(Exception):
    pass

# -----------------------------------------------------------------------------------------------------------------------------

async def get(url, headers={}, data=None, params={}, timeout=10):
    try:
        return await asyncio.wait_for(_request("GET", url, headers, data, params), timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(e)
    finally:
        print(gc.mem_free())
    
# -----------------------------------------------------------------------------------------------------------------------------
    
async def post(url, headers={}, data=None, params={}, timeout=10):
    try:
        return await asyncio.wait_for(_request("POST", url, headers, data, params), timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(e)
    
# -----------------------------------------------------------------------------------------------------------------------------

async def delete(url, headers={}, data=None, params={}, timeout=10):
    try:
        return await asyncio.wait_for(_request("DELETE", url, headers, data, params), timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(e)

# -----------------------------------------------------------------------------------------------------------------------------

async def put(url, headers={}, data=None, params={}, timeout=10):
    try:
        return await asyncio.wait_for(_request("PUT", url, headers, data, params), timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(e)

# =============================================================================================================================
# ===(Class urequests)==========================================================================================================
# =============================================================================================================================
# Notes: able to use urequests synchronously with a working timeout

class urequests:
# -----------------------------------------------------------------------------------------------------------------------------

    def get(url, headers={}, data=None, params={}, timeout=10):
        try:
            return asyncio.run(asyncio.wait_for(_request("GET", url, headers, data, params), timeout))
        except asyncio.TimeoutError as e:
            raise TimeoutError(e)

# -----------------------------------------------------------------------------------------------------------------------------

    def post(url, headers={}, data=None, params={}, timeout=10):
        try:
            return asyncio.wait_for(_request("POST", url, headers, data, params), timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutError(e)

# -----------------------------------------------------------------------------------------------------------------------------

    def delete(url, headers={}, data=None, params={}, timeout=10):
        try:
            return asyncio.wait_for(_request("DELETE", url, headers, data, params), timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutError(e)

# -----------------------------------------------------------------------------------------------------------------------------

    def put(url, headers={}, data=None, params={}, timeout=10):
        try:
            return asyncio.wait_for(_request("PUT", url, headers, data, params), timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutError(e)

# =============================================================================================================================
# ===(Class ClientResponse)====================================================================================================
# =============================================================================================================================
# Notes: Reads response content, sometimes fails due to memory limitations.

class ClientResponse:

# -----------------------------------------------------------------------------------------------------------------------------

    def __init__(self, reader):
        self.content = reader

# -----------------------------------------------------------------------------------------------------------------------------

    async def read(self, sz=-1):
        try:
            content = b''
            while True:
                data = await self.content.read(sz)
                if not data or data == b"":
                    break
                content += data
        finally:
            gc.collect()
            return content

# -----------------------------------------------------------------------------------------------------------------------------

    def __repr__(self):
        #return "<ClientResponse %d %s>" % (self.status_code, self.headers)
        return "<Response [%d]>" % (self.status_code)

# =============================================================================================================================
# ===(Class ChunkedClientResponse)=============================================================================================
# =============================================================================================================================
# Notes: Reads chunked response content, sometimes fails due to memory limitations.
# Issues: Sometimes the content does not seem right, always looks like encrypted.

class ChunkedClientResponse(ClientResponse):
    
# -----------------------------------------------------------------------------------------------------------------------------

    def __init__(self, reader):
        self.content = reader
        self.chunk_size = 0
        
# -----------------------------------------------------------------------------------------------------------------------------

    async def read(self, sz=4*1024*1024):
        data = b''
        try:
            while True:
                if self.chunk_size == 0:
                    l = await self.content.readline() # get Hex size
                    l = l.split(b";", 1)[0]
                    self.chunk_size = int(l, 16) # convert to int
                    if self.chunk_size == 0: # end of message
                        sep = await self.content.read(2)
                        assert sep == b"\r\n"
                        break
                data += await self.content.read(min(sz, self.chunk_size))
                self.chunk_size -= len(data)
                if self.chunk_size == 0:
                    sep = await self.content.read(2)
                    assert sep == b"\r\n"
                    break
        finally:
            gc.collect()
            return data

# -----------------------------------------------------------------------------------------------------------------------------

    def __repr__(self):
        return "<ChunkedResponse [%d]>" % (self.status_code)

# =============================================================================================================================
# ===(Function _request_raw)===================================================================================================
# =============================================================================================================================

async def _request_raw(method, url, headers, data):
    try:
        proto, dummy, host, path = url.split("/", 3)
    except ValueError:
        proto, dummy, host = url.split("/", 2)
        path = ""
    port = 80
    ssl = False
    if proto == "https:":
        port = 443
        ssl = True
    reader, writer = await open_connection(host, port, ssl)
    query = "%s /%s HTTP/%s\r\nHost: %s\r\nConnection: close\r\nUser-Agent: compat\r\n%s" % (method, path, HTTP_version, host, headers)
    if data:
        query += "Content-Type: application/json\r\n"
        query += "Content-Length: %d\r\n" % len(data)
    query += "\r\n"
    if data:
        query += data
    await writer.awrite(query.encode('latin-1'))
    return reader

# =============================================================================================================================
# ===(Function _request)=======================================================================================================
# =============================================================================================================================

async def _request(method, url, headers={}, data=None, params={}):
    try:
        #headers support
        h = ""
        for k in headers:
            h += k
            h += ": "
            h += headers[k]
            h += "\r\n"
        # params support
        if params:
            url += "?"
            for p in params:
                url += p
                url += "="
                url += params[p]
                url += "&"
            url = url[0:len(url)-1]
    except Exception as e:
        raise e
    try:
        # build in redirect support
        redir_cnt = 0
        redir_url = None
        while redir_cnt < 2:
            reader = await _request_raw(method=method, url=url, headers=h, data=data)
            sline = await reader.readline()
            sline = sline.split(None, 2)
            status_code = int(sline[1])
            if len(sline) > 1:
                reason = sline[2].decode().rstrip()
            chunked = False
            json = None
            charset = 'utf-8'
            headers = []
            # read headers
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
                headers.append(line)
                if line.startswith(b"Transfer-Encoding:"):
                    if b"chunked" in line:
                        chunked = True
                elif line.startswith(b"Location:"):
                    url = line.rstrip().split(None, 1)[1].decode("latin-1")
                elif line.startswith(b"Content-Type:"):
                    if b"application/json" in line:
                        json = True
                    if b"charset" in line:
                        charset = line.rstrip().decode().split(None, 2)[-1].split("=")[-1]
            #look for redirects
            if 301 <= status_code <= 303:
                redir_cnt += 1
                await reader.wait_closed()
                continue
            break
        # read chuncked content
        if chunked:
            resp = ChunkedClientResponse(reader)
            content_raw = await resp.read()
            try:
                resp.content = content_raw.decode(charset)
            except Exception:
                resp.content = None
        # read content
        else:
            resp = ClientResponse(reader)
            content_raw = await resp.read()
            try:
                resp.content = content_raw.decode(charset)
            except Exception:
                resp.content = content_raw

        if json and resp.content is not None:
            try:
                resp.json = ujson.loads(resp.content)
            except Exception:
                resp.json = None
                
        try:
            resp.text = str(content_raw)
        except Exception: # might get a out of memory allocation error if response is to long
            resp.text = None
        resp.status_code = status_code
        resp.headers = headers
        resp.reason = reason
        resp.url = url
        return resp
    except Exception as e:
        raise ConnectionError(e)
    finally:
        try:
            await reader.wait_closed()
        except NameError:
            pass
        gc.collect()

# =============================================================================================================================
# ===(Function open_connection)=======================================================================================================
# =============================================================================================================================
# Notes: Replaces asyncio.open_connection()

# replaced asyncio.open_coonect in order to add ssl support
async def open_connection(host, port, ssl):
    from uasyncio import core
    gc.collect()
    from uasyncio.stream import Stream
    gc.collect()
    from uerrno import EINPROGRESS
    gc.collect()
    import usocket as socket
    gc.collect()

    ai = socket.getaddrinfo(host, port)[0]  # TODO this is blocking!
    s = socket.socket(ai[0], ai[1], ai[2])
    s.setblocking(False)
    try:
        s.connect(ai[-1])
    except OSError as er:
        if er.args[0] != EINPROGRESS:
            raise er
    yield core._io_queue.queue_write(s)
    if ssl:
        import ussl
        s = ussl.wrap_socket(s, server_hostname=host) # TODO this is blocking!
    ss = Stream(s)
    yield core._io_queue.queue_write(s)
    return ss, ss
