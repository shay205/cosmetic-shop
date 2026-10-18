import re

from django.core import mail
from django.test import TestCase

from django.contrib.auth import get_user_model
from django.urls import reverse

from customers.models import CustomerProfile


class RegistrationTests(TestCase):
    def test_registration_creates_customer_profile(self):
        response = self.client.post(reverse('accounts:register'), {
            'first_name': 'Glow',
            'username': 'glow-customer',
            'email': 'glow@example.com',
            'password1': 'Safe-Test-Password-294!',
            'password2': 'Safe-Test-Password-294!',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/verification.html')
        user = get_user_model().objects.get(username='glow-customer')
        self.assertFalse(user.is_active)
        self.assertTrue(CustomerProfile.objects.filter(user=user).exists())
        self.assertEqual(len(mail.outbox), 1)

        match = re.search(r'/accounts/verify/([^/\s]+)/', mail.outbox[0].body)
        self.assertIsNotNone(match)
        verification = self.client.get(f'/accounts/verify/{match.group(1)}/')

        self.assertContains(verification, 'Your account is active')
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_invalid_verification_link_does_not_activate_account(self):
        user = get_user_model().objects.create_user(
            username='inactive-customer',
            email='inactive@example.com',
            password='Safe-Test-Password-294!',
            is_active=False,
        )

        response = self.client.get('/accounts/verify/invalid-token/')

        self.assertContains(response, 'Verification link invalid or expired')
        user.refresh_from_db()
        self.assertFalse(user.is_active)
