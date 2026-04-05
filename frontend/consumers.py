import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User

from .models import ChatMessage


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.other_user_id = self.scope["url_route"]["kwargs"]["user_id"]
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        # Create a unique room name for the two users
        ids = sorted([int(self.user.id), int(self.other_user_id)])
        self.room_name = f"chat_{ids[0]}_{ids[1]}"
        self.room_group_name = f"chat_{self.room_name}"

        # Join room group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()

        # Notify room that user is online
        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "user_presence", "user_id": self.user.id, "status": "online"},
        )

    async def disconnect(self, close_code):
        # Notify room that user is offline
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "user_presence", "user_id": self.user.id, "status": "offline"},
            )
            # Leave room group
            await self.channel_layer.group_discard(
                self.room_group_name, self.channel_name
            )

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)

        # Handle presence request (from client checking status)
        if text_data_json.get("type") == "check_presence":
            await self.channel_layer.group_send(
                self.room_group_name,
                {"type": "user_presence", "user_id": self.user.id, "status": "online"},
            )
            return

        message = text_data_json["message"]
        sender_id = self.user.id
        receiver_id = self.other_user_id

        # Save message to database
        msg_obj = await self.save_message(sender_id, receiver_id, message)

        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message,
                "sender_id": sender_id,
                "timestamp": msg_obj.timestamp.strftime("%H:%M"),
            },
        )

    # Receive message from room group
    async def chat_message(self, event):
        message = event["message"]
        sender_id = event["sender_id"]
        timestamp = event.get("timestamp", "Just now")

        # Send message to WebSocket
        await self.send(
            text_data=json.dumps(
                {
                    "type": "chat_message",
                    "message": message,
                    "sender_id": sender_id,
                    "timestamp": timestamp,
                }
            )
        )

    async def user_presence(self, event):
        # Send presence status to WebSocket
        await self.send(
            text_data=json.dumps(
                {
                    "type": "presence",
                    "user_id": event["user_id"],
                    "status": event["status"],
                }
            )
        )

    @database_sync_to_async
    def save_message(self, sender_id, receiver_id, message):
        receiver = User.objects.get(id=receiver_id)
        return ChatMessage.objects.create(
            sender=self.user, receiver=receiver, message=message
        )
