from django.db import migrations
from django.contrib.auth.hashers import make_password

def create_admin_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    if not User.objects.filter(username='admin').exists():
        User.objects.create(
            username='admin',
            email='admin@lenden.com',
            password=make_password('admin123'),
            is_staff=True,
            is_superuser=True
        )

def remove_admin_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    User.objects.filter(username='admin').delete()

class Migration(migrations.Migration):
    dependencies = [
        ('frontend', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_admin_user, reverse_code=remove_admin_user),
    ]
