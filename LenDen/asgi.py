"""
ASGI config for LenDen project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from frontend.channels_middleware import MultiSessionCookieMiddleware
import frontend.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LenDen.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": MultiSessionCookieMiddleware(
        AuthMiddlewareStack(
            URLRouter(
                frontend.routing.websocket_urlpatterns
            )
        )
    ),
})
