from django.contrib import admin

from .models import GoodsExchange, MoneyTransaction, Referral, Review, UserProfile

# Register your models here.
admin.site.register(UserProfile)
admin.site.register(MoneyTransaction)
admin.site.register(GoodsExchange)
admin.site.register(Referral)
admin.site.register(Review)
