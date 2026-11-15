"""Directory adapters. The rest of the app only uses add(), remove() and ping()."""
import os
import ssl
from urllib.parse import urlparse


class MockDirectory:
    """In-memory fake Active Directory for learning and tests."""
    name = "mock (lab mode)"

    def __init__(self):
        self.groups = {}

    def ping(self):
        return True, self.name

    def add(self, user, group):
        self.groups.setdefault(group, set()).add(user)

    def remove(self, user, group):
        self.groups.get(group, set()).discard(user)

    def has(self, user, group):
        return user in self.groups.get(group, set())


class LdapDirectory:
    """Real Active Directory over LDAPS using a delegated service account."""
    name = "Active Directory (LDAPS)"

    def __init__(self, uri, bind_dn, password, base_dn, group_base):
        self.uri, self.bind_dn, self.password = uri, bind_dn, password
        self.base_dn, self.group_base = base_dn, group_base

    def _connect(self):
        from ldap3 import Connection, Server, Tls
        uri = urlparse(self.uri)
        if uri.scheme.lower() != 'ldaps' or not uri.hostname:
            raise ValueError('LDAP_URI must use ldaps:// with a valid hostname')
        tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=os.environ.get('LDAP_CA_CERT_FILE'),
                  valid_names=[uri.hostname])
        server = Server(uri.hostname, port=uri.port or 636, use_ssl=True, tls=tls, connect_timeout=5)
        return Connection(server, self.bind_dn, self.password, auto_bind=True, receive_timeout=10)

    def _user_dn(self, conn, sam):
        from ldap3.utils.conv import escape_filter_chars  # prevents LDAP injection
        conn.search(self.base_dn,
                    f"(&(objectClass=user)(sAMAccountName={escape_filter_chars(sam)}))", attributes=[])
        if not conn.entries:
            raise LookupError(f"user {sam} not found in AD")
        return conn.entries[0].entry_dn

    def ping(self):
        try:
            with self._connect():
                return True, self.name
        except Exception as exc:  # show the reason on the dashboard
            return False, f"{self.name}: {exc}"

    def add(self, user, group):
        from ldap3.extend.microsoft.addMembersToGroups import ad_add_members_to_groups
        with self._connect() as c:
            from ldap3.utils.dn import escape_rdn
            if not ad_add_members_to_groups(c, self._user_dn(c, user), f"CN={escape_rdn(group)},{self.group_base}", fix=True):
                raise RuntimeError('AD group membership update failed')

    def remove(self, user, group):
        from ldap3.extend.microsoft.removeMembersFromGroups import (
            ad_remove_members_from_groups,
        )
        with self._connect() as c:
            from ldap3.utils.dn import escape_rdn
            if not ad_remove_members_from_groups(c, self._user_dn(c, user), f"CN={escape_rdn(group)},{self.group_base}", fix=True):
                raise RuntimeError('AD group membership removal failed')


def from_env():
    uri = os.environ.get("LDAP_URI")
    if not uri:
        return MockDirectory()
    return LdapDirectory(uri, os.environ["LDAP_BIND_DN"], os.environ["LDAP_PASSWORD"],
                         os.environ["LDAP_BASE_DN"], os.environ["AD_GROUP_BASE"])
