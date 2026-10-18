from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from inventory.models import InventoryMovement
from inventory.services import record_stock_movement
from products.models import Category, Product

from .models import MpesaPayment, Order, OrderItem
from .mpesa import MpesaError, _post_json, initiate_stk_push, query_stk_status


class CheckoutInventoryTests(TestCase):
    def test_checkout_creates_sale_movement_and_decrements_stock(self):
        category = Category.objects.create(name='Skincare')
        product = Product.objects.create(
            category=category,
            name='Rose Serum',
            price='1200.00',
            stock_quantity=4,
        )
        self.client.post(
            f'/cart/add/{product.pk}/',
            {'quantity': '2'},
        )

        response = self.client.post('/checkout/', {
            'full_name': 'Glow Customer',
            'email': 'customer@example.com',
            'phone': '0712345678',
            'address': '12 Rose Street',
            'city': 'Nairobi',
            'notes': '',
        })

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        movement = InventoryMovement.objects.get()
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 2)
        self.assertEqual(movement.reason, 'sale')
        self.assertEqual(movement.quantity_change, -2)
        self.assertEqual(movement.order_item.order, order)


class OrderAdminTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Haircare')
        self.product = Product.objects.create(
            category=category,
            name='Hair Oil',
            price='500.00',
            stock_quantity=5,
        )
        self.order = Order.objects.create(
            full_name='Admin Customer',
            email='admin-customer@example.com',
            phone='0712345678',
            address='1 Shop Street',
            city='Nairobi',
            total='1000.00',
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            product_name=self.product.name,
            price='500.00',
            quantity=2,
        )
        record_stock_movement(
            product=self.product,
            quantity_change=-2,
            reason='sale',
            notes=f'Order {self.order.order_number}',
            order_item=self.item,
        )
        staff = get_user_model().objects.create_superuser(
            username='orders-admin',
            email='orders-admin@example.com',
            password='Safe-Test-Password-294!',
        )
        self.client.force_login(staff)
        self.changelist_url = reverse('admin:sales_order_changelist')

    def _set_status_in_list(self, status):
        return self.client.post(self.changelist_url, {
            '_save': 'Save',
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '1',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-id': str(self.order.pk),
            'form-0-status': status,
        })

    def test_order_list_cancellation_restores_stock_once(self):
        response = self.client.get(self.changelist_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.order.order_number)

        change_response = self._set_status_in_list('cancelled')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled', change_response.content.decode()[:1000])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)
        self.assertEqual(
            InventoryMovement.objects.filter(
                order_item=self.item,
                reason='adjustment',
            ).count(),
            1,
        )

        self._set_status_in_list('pending')
        self._set_status_in_list('cancelled')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)
        self.assertEqual(
            InventoryMovement.objects.filter(
                order_item=self.item,
                reason='adjustment',
            ).count(),
            1,
        )


class MpesaPaymentTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name='Makeup')
        self.product = Product.objects.create(
            category=category,
            name='Lip Balm',
            price='1200.00',
            stock_quantity=5,
        )
        self.client.post(f'/cart/add/{self.product.pk}/', {'quantity': '2'})
        self.checkout_data = {
            'full_name': 'Glow Customer',
            'email': 'customer@example.com',
            'phone': '0712345678',
            'payment_method': 'mpesa',
            'mpesa_phone': '0712 345 678',
            'address': '12 Rose Street',
            'city': 'Nairobi',
            'notes': '',
        }

    @patch('sales.views.initiate_stk_push', return_value=('merchant-1', 'checkout-1'))
    def test_mpesa_checkout_uses_server_total_and_normalized_phone(self, initiate):
        response = self.client.post('/checkout/', self.checkout_data)

        self.assertEqual(response.status_code, 302)
        payment = MpesaPayment.objects.get()
        self.assertEqual(payment.amount, 2400)
        self.assertEqual(payment.phone_number, '254712345678')
        self.assertEqual(payment.status, 'pending')
        self.assertEqual(payment.checkout_request_id, 'checkout-1')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)
        initiate.assert_called_once_with(payment)

    @patch('sales.views.query_stk_status', return_value='0')
    @patch('sales.views.initiate_stk_push', return_value=('merchant-1', 'checkout-1'))
    def test_success_callback_marks_payment_successful_once(self, initiate, query):
        self.client.post('/checkout/', self.checkout_data)
        callback = {
            'Body': {
                'stkCallback': {
                    'MerchantRequestID': 'merchant-1',
                    'CheckoutRequestID': 'checkout-1',
                    'ResultCode': 0,
                    'ResultDesc': 'The service request is processed successfully.',
                    'CallbackMetadata': {
                        'Item': [
                            {'Name': 'Amount', 'Value': 2400},
                            {'Name': 'MpesaReceiptNumber', 'Value': 'ABC123XYZ'},
                            {'Name': 'PhoneNumber', 'Value': 254712345678},
                        ],
                    },
                },
            },
        }

        first = self.client.post('/mpesa/callback/', callback, content_type='application/json')
        second = self.client.post('/mpesa/callback/', callback, content_type='application/json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        payment = MpesaPayment.objects.get()
        self.assertEqual(payment.status, 'successful')
        self.assertEqual(payment.receipt_number, 'ABC123XYZ')
        self.assertEqual(InventoryMovement.objects.count(), 1)
        query.assert_called_once_with('checkout-1')

    @patch('sales.views.query_stk_status', return_value='1032')
    @patch('sales.views.initiate_stk_push', return_value=('merchant-1', 'checkout-1'))
    def test_cancelled_callback_restores_stock_once(self, initiate, query):
        self.client.post('/checkout/', self.checkout_data)
        callback = {
            'Body': {
                'stkCallback': {
                    'MerchantRequestID': 'merchant-1',
                    'CheckoutRequestID': 'checkout-1',
                    'ResultCode': 1032,
                    'ResultDesc': 'Request cancelled by user.',
                },
            },
        }

        self.client.post('/mpesa/callback/', callback, content_type='application/json')
        self.client.post('/mpesa/callback/', callback, content_type='application/json')

        payment = MpesaPayment.objects.get()
        payment.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(payment.status, 'cancelled')
        self.assertEqual(payment.order.status, 'cancelled')
        self.assertEqual(self.product.stock_quantity, 5)
        self.assertEqual(InventoryMovement.objects.count(), 2)

    @patch('sales.views.initiate_stk_push', side_effect=MpesaError('M-Pesa could not start the payment prompt. Please try again.'))
    def test_failed_stk_initiation_restores_stock_and_keeps_cart(self, initiate):
        response = self.client.post('/checkout/', self.checkout_data)

        self.assertEqual(response.status_code, 200)
        payment = MpesaPayment.objects.get()
        self.product.refresh_from_db()
        self.assertEqual(payment.status, 'failed')
        self.assertEqual(payment.order.status, 'cancelled')
        self.assertEqual(self.product.stock_quantity, 5)
        self.assertEqual(len(self.client.session.get('cart', {})), 1)

    @patch('sales.views.query_stk_status', return_value='0')
    @patch('sales.views.initiate_stk_push', return_value=('merchant-1', 'checkout-1'))
    def test_callback_with_wrong_amount_does_not_mark_payment_paid(self, initiate, query):
        self.client.post('/checkout/', self.checkout_data)
        callback = {
            'Body': {
                'stkCallback': {
                    'MerchantRequestID': 'merchant-1',
                    'CheckoutRequestID': 'checkout-1',
                    'ResultCode': 0,
                    'CallbackMetadata': {
                        'Item': [
                            {'Name': 'Amount', 'Value': 1},
                            {'Name': 'MpesaReceiptNumber', 'Value': 'ABC123XYZ'},
                            {'Name': 'PhoneNumber', 'Value': 254712345678},
                        ],
                    },
                },
            },
        }

        response = self.client.post('/mpesa/callback/', callback, content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(MpesaPayment.objects.get().status, 'pending')

    @override_settings(
        MPESA_ENVIRONMENT='sandbox',
        MPESA_CONSUMER_KEY='sandbox-key',
        MPESA_CONSUMER_SECRET='sandbox-secret',
        MPESA_SHORTCODE='174379',
        MPESA_PASSKEY='sandbox-passkey',
        MPESA_CALLBACK_URL='https://shop.example.test/mpesa/callback/',
    )
    @patch('sales.mpesa._access_token', return_value='sandbox-token')
    @patch('sales.mpesa._post_json', return_value={
        'ResponseCode': '0',
        'MerchantRequestID': 'merchant-2',
        'CheckoutRequestID': 'checkout-2',
    })
    def test_stk_request_uses_sandbox_and_server_payment_values(self, post_json, access_token):
        order = Order.objects.create(
            full_name='Glow Customer',
            email='customer@example.com',
            phone='0712345678',
            address='12 Rose Street',
            city='Nairobi',
            total='2400.00',
        )
        payment = MpesaPayment.objects.create(
            order=order,
            phone_number='254712345678',
            amount=Decimal('2400.00'),
        )

        result = initiate_stk_push(payment)

        self.assertEqual(result, ('merchant-2', 'checkout-2'))
        self.assertEqual(
            post_json.call_args.args[0],
            'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest',
        )
        payload = post_json.call_args.args[2]
        self.assertEqual(payload['Amount'], 2400)
        self.assertEqual(payload['PhoneNumber'], '254712345678')
        self.assertEqual(payload['AccountReference'], order.order_number)
        access_token.assert_called_once()

    @patch('sales.mpesa.urlopen')
    def test_daraja_post_uses_bearer_token(self, mocked_urlopen):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = b'{}'

        _post_json('https://sandbox.safaricom.co.ke/example', 'sandbox-token', {})

        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer sandbox-token')

    @override_settings(
        MPESA_ENVIRONMENT='sandbox',
        MPESA_CONSUMER_KEY='sandbox-key',
        MPESA_CONSUMER_SECRET='sandbox-secret',
        MPESA_SHORTCODE='174379',
        MPESA_PASSKEY='sandbox-passkey',
        MPESA_CALLBACK_URL='https://shop.example.test/mpesa/callback/',
    )
    @patch('sales.mpesa._access_token', return_value='sandbox-token')
    @patch('sales.mpesa._post_json', return_value={'ResponseCode': '0', 'ResultCode': '0'})
    def test_stk_query_checks_provider_result(self, post_json, access_token):
        result = query_stk_status('checkout-1')

        self.assertEqual(result, '0')
        self.assertEqual(
            post_json.call_args.args[0],
            'https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query',
        )
        self.assertEqual(post_json.call_args.args[2]['CheckoutRequestID'], 'checkout-1')
        access_token.assert_called_once()
