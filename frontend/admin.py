from django.contrib import admin
from .models import UserProfile, MoneyTransaction, GoodsExchange, Referral, Review

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(MoneyTransaction)
admin.site.register(GoodsExchange)
admin.site.register(Referral)
admin.site.register(Review)

