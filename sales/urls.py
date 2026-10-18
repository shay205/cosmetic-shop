from django.urls import path

from . import views

app_name = 'sales'

urlpatterns = [
    path('checkout/', views.checkout, name='checkout'),
    path('mpesa/callback/', views.mpesa_callback, name='mpesa_callback'),
    path('order/<int:order_id>/success/', views.order_success, name='success'),
    path('order/<int:order_id>/payment-status/', views.payment_status, name='payment_status'),
    path('orders/', views.order_list, name='orders'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
]