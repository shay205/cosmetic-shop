from django.test import TestCase

from django.contrib.auth import get_user_model

from .models import CustomerProfile


class CustomerProfileTests(TestCase):
    def test_profile_links_delivery_details_to_user(self):
        user = get_user_model().objects.create_user(
            username='glow-customer',
            password='test-password',
        )
        profile = CustomerProfile.objects.create(
            user=user,
            phone='0712345678',
            address='12 Rose Street',
            city='Nairobi',
        )

        self.assertEqual(user.customer_profile, profile)
        self.assertEqual(profile.city, 'Nairobi')
