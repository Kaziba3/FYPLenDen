from django.conf import settings
import urllib.parse

class MultiSessionCookieMiddleware:
    """
    Channels middleware that swaps the sessionid cookie based on the session_id query parameter.
    This ensures that subsequent middlewares (like SessionMiddleware) see the correct session.
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Only process if it's a websocket and has a query string
        if scope['type'] == 'websocket':
            query_string = scope.get('query_string', b'').decode()
            params = urllib.parse.parse_qs(query_string)
            session_id = params.get('session_id', [None])[0]

            if session_id:
                # Find the Cookie header
                headers = list(scope.get('headers', []))
                for i, (name, value) in enumerate(headers):
                    if name == b'cookie':
                        cookie_str = value.decode()
                        cookies = {}
                        for c in cookie_str.split(';'):
                            if '=' in c:
                                k, v = c.strip().split('=', 1)
                                cookies[k] = v
                        
                        alt_cookie_name = f"sessionid_{session_id}"
                        if alt_cookie_name in cookies:
                            # Swap the main session ID with our alternate one
                            cookies[settings.SESSION_COOKIE_NAME] = cookies[alt_cookie_name]
                            
                            # Re-assemble the cookie header
                            new_cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                            headers[i] = (b'cookie', new_cookie_str.encode())
                            scope['headers'] = headers
                            break
        
        return await self.inner(scope, receive, send)
