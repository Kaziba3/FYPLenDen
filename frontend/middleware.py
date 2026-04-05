from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware


class MultiSessionMiddleware(SessionMiddleware):
    """
    Middleware that allows multiple independent sessions in the same browser
    by appending a 'session_id' parameter to the URL.
    Example: http://127.0.0.1:8000/?session_id=1
    """

    def process_request(self, request):
        session_id = request.GET.get("session_id")
        if session_id:
            # Construct a unique cookie name for this session ID
            alt_cookie_name = f"sessionid_{session_id}"

            # If the alternate cookie exists, swap it into the place of the main session cookie
            # so that the standard SessionMiddleware uses it.
            if alt_cookie_name in request.COOKIES:
                request.COOKIES[settings.SESSION_COOKIE_NAME] = request.COOKIES[
                    alt_cookie_name
                ]
            else:
                # If no alternate cookie exists, we want to start a fresh session for this ID.
                # Remove the main session cookie from this request's perspective.
                if settings.SESSION_COOKIE_NAME in request.COOKIES:
                    del request.COOKIES[settings.SESSION_COOKIE_NAME]

        super().process_request(request)

    def process_response(self, request, response):
        session_id = request.GET.get("session_id")

        # Capture the response from the base SessionMiddleware
        response = super().process_response(request, response)

        # If we are in a multi-session context and a new session cookie was set
        if session_id and settings.SESSION_COOKIE_NAME in response.cookies:
            alt_cookie_name = f"sessionid_{session_id}"
            # Copy the standard session cookie value to our alternate cookie
            cookie_val = response.cookies[settings.SESSION_COOKIE_NAME].value
            response.set_cookie(
                alt_cookie_name,
                cookie_val,
                max_age=settings.SESSION_COOKIE_AGE,
                path=settings.SESSION_COOKIE_PATH,
                domain=settings.SESSION_COOKIE_DOMAIN,
                secure=settings.SESSION_COOKIE_SECURE,
                httponly=settings.SESSION_COOKIE_HTTPONLY,
                samesite=settings.SESSION_COOKIE_SAMESITE,
            )
        return response
