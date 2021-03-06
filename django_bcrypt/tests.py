#coding=utf8

from __future__ import with_statement
from contextlib import contextmanager

import bcrypt

from django import conf
from django.contrib.auth.models import User, UNUSABLE_PASSWORD
from django.test import TestCase
from django.utils.functional import LazyObject

from django_bcrypt.models import (bcrypt_check_password, bcrypt_set_password,
                                  get_rounds, is_enabled, migrate_to_bcrypt)
try:
    from django_bcrypt.models import _check_password, _set_password
except ImportError:
    pass


class CheckPasswordTest(TestCase):
    def test_bcrypt_password(self):
        user = User()
        with settings():
            bcrypt_set_password(user, 'password')
        self.assertTrue(bcrypt_check_password(user, 'password'))
        self.assertFalse(bcrypt_check_password(user, 'invalid'))

    def test_unicode_password(self):
        user = User()
        with settings():
            bcrypt_set_password(user, u"aáåäeéêëoôö")
        self.assertTrue(bcrypt_check_password(user, u"aaaaeeeeooo"))
        self.assertFalse(bcrypt_check_password(user, 'invalid'))

    def test_sha1_password(self):
        user = User()
        _set_password(user, 'password')
        self.assertTrue(bcrypt_check_password(user, 'password'))
        self.assertFalse(bcrypt_check_password(user, 'invalid'))

    def test_change_rounds(self):
        user = User()
        # Hash with 5 rounds
        with settings(BCRYPT_ROUNDS=5):
            bcrypt_set_password(user, 'password')
        password_5 = user.password
        self.assertTrue(bcrypt_check_password(user, 'password'))
        # Hash with 12 rounds
        with settings(BCRYPT_ROUNDS=12):
            bcrypt_set_password(user, 'password')
        password_12 = user.password
        self.assertTrue(bcrypt_check_password(user, 'password'))


class SetPasswordTest(TestCase):
    def assertBcrypt(self, hashed, password):
        self.assertEqual(hashed[:3], 'bc$')
        self.assertEqual(hashed[3:], bcrypt.hashpw(password, hashed[3:]))

    def test_set_password(self):
        user = User()
        with settings():
            bcrypt_set_password(user, 'password')
        self.assertBcrypt(user.password, 'password')

    def test_disabled(self):
        user = User()
        with settings(BCRYPT_ENABLED=False):
            bcrypt_set_password(user, 'password')
        self.assertFalse(user.password.startswith('bc$'), user.password)

    def test_set_unusable_password(self):
        user = User()
        with settings():
            bcrypt_set_password(user, None)
        self.assertEqual(user.password, UNUSABLE_PASSWORD)

    def test_change_rounds(self):
        user = User()
        with settings(BCRYPT_ROUNDS=0):
            settings.BCRYPT_ROUNDS = 0
            bcrypt_set_password(user, 'password')
            self.assertBcrypt(user.password, 'password')


class MigratePasswordTest(TestCase):
    def assertBcrypt(self, hashed, password):
        self.assertEqual(hashed[:3], 'bc$')
        self.assertEqual(hashed[3:], bcrypt.hashpw(password, hashed[3:]))

    def assertSha1(self, hashed, password):
        self.assertEqual(hashed[:5], 'sha1$')

    def test_migrate_sha1_to_bcrypt(self):
        user = User(username='username')
        with settings(BCRYPT_MIGRATE=True, BCRYPT_ENABLED_UNDER_TEST=True):
            _set_password(user, 'password')
            self.assertSha1(user.password, 'password')
            self.assertTrue(bcrypt_check_password(user, 'password'))
            self.assertBcrypt(user.password, 'password')
        self.assertEqual(User.objects.get(username='username').password,
                         user.password)

    def test_migrate_bcrypt_to_bcrypt(self):
        user = User(username='username')
        with settings(BCRYPT_MIGRATE=True,
                      BCRYPT_ROUNDS=10,
                      BCRYPT_ENABLED_UNDER_TEST=True):
            user.set_password('password')
        with settings(BCRYPT_MIGRATE=True,
                      BCRYPT_ROUNDS=12,
                      BCRYPT_ENABLED_UNDER_TEST=True):
            user.check_password('password')
        salt_and_hash = user.password[3:]
        self.assertEqual(salt_and_hash.split('$')[2], '12')
        self.assertEqual(User.objects.get(username='username').password,
                         user.password)

    def test_no_bcrypt_to_bcrypt(self):
        user = User(username='username')
        with settings(BCRYPT_MIGRATE=True,
                      BCRYPT_ROUNDS=10,
                      BCRYPT_ENABLED_UNDER_TEST=True):
            user.set_password('password')
            old_password = user.password
            user.check_password('password')
        self.assertEqual(old_password, user.password)

    def test_no_migrate_password(self):
        user = User()
        with settings(BCRYPT_MIGRATE=False, BCRYPT_ENABLED_UNDER_TEST=True):
            _set_password(user, 'password')
            self.assertSha1(user.password, 'password')
            self.assertTrue(bcrypt_check_password(user, 'password'))
            self.assertSha1(user.password, 'password')


class SettingsTest(TestCase):
    def test_rounds(self):
        with settings(BCRYPT_ROUNDS=0):
            self.assertEqual(get_rounds(), 0)
        with settings(BCRYPT_ROUNDS=5):
            self.assertEqual(get_rounds(), 5)
        with settings(BCRYPT_ROUNDS=NotImplemented):
            self.assertEqual(get_rounds(), 12)

    def test_enabled(self):
        with settings(BCRYPT_ENABLED=False):
            self.assertFalse(is_enabled())
        with settings(BCRYPT_ENABLED=True):
            self.assertTrue(is_enabled())
        with settings(BCRYPT_ENABLED=NotImplemented):
            self.assertTrue(is_enabled())

    def test_enabled_under_test(self):
        with settings(BCRYPT_ENABLED_UNDER_TEST=True):
            self.assertTrue(is_enabled())
        with settings(BCRYPT_ENABLED_UNDER_TEST=False):
            self.assertFalse(is_enabled())
        with settings(BCRYPT_ENABLED_UNDER_TEST=NotImplemented):
            self.assertFalse(is_enabled())

    def test_migrate_to_bcrypt(self):
        with settings(BCRYPT_MIGRATE=False):
            self.assertEqual(migrate_to_bcrypt(), False)
        with settings(BCRYPT_MIGRATE=True):
            self.assertEqual(migrate_to_bcrypt(), True)
        with settings(BCRYPT_MIGRATE=NotImplemented):
            self.assertEqual(migrate_to_bcrypt(), False)


def settings(**kwargs):
    kwargs = dict({'BCRYPT_ENABLED': True,
                   'BCRYPT_ENABLED_UNDER_TEST': True},
                  **kwargs)
    return patch(conf.settings, **kwargs)


@contextmanager
def patch(namespace, **values):
    """Patches `namespace`.`name` with `value` for (name, value) in values"""

    originals = {}

    if isinstance(namespace, LazyObject):
        if namespace._wrapped is None:
            namespace._setup()
        namespace = namespace._wrapped

    for (name, value) in values.iteritems():
        try:
            originals[name] = getattr(namespace, name)
        except AttributeError:
            originals[name] = NotImplemented
        if value is NotImplemented:
            if originals[name] is not NotImplemented:
                delattr(namespace, name)
        else:
            setattr(namespace, name, value)

    try:
        yield
    finally:
        for (name, original_value) in originals.iteritems():
            if original_value is NotImplemented:
                if values[name] is not NotImplemented:
                    delattr(namespace, name)
            else:
                setattr(namespace, name, original_value)
