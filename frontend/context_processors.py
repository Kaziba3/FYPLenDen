from .models import Notification

def notifications(request):
    if request.user.is_authenticated:
        unread_notifications = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')
        return {
            'unread_notifications': unread_notifications,
            'unread_notifications_count': unread_notifications.count()
        }
    return {
        'unread_notifications': [],
        'unread_notifications_count': 0
    }
