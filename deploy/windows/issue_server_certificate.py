"""Issue a long-lived TLS server certificate from a locally held CA key.

Run this only on the CA host with a root key protected from the web service.
The generated server key must be ACL-restricted to SYSTEM, Administrators,
and the account that runs the web task.
"""

import argparse
import hashlib
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-certificate", type=Path, required=True)
    parser.add_argument("--ca-private-key", type=Path, required=True)
    parser.add_argument("--server-name", required=True, help="IP address or DNS name clients will use")
    parser.add_argument("--certificate-output", type=Path, required=True)
    parser.add_argument("--private-key-output", type=Path, required=True)
    parser.add_argument("--valid-days", type=int, default=365)
    args = parser.parse_args()

    if not 30 <= args.valid_days <= 825:
        parser.error("--valid-days must be between 30 and 825")

    ca_cert = x509.load_pem_x509_certificate(args.ca_certificate.read_bytes())
    ca_key = serialization.load_pem_private_key(args.ca_private_key.read_bytes(), password=None)
    constraints = ca_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
    if not constraints.ca:
        raise SystemExit("The supplied certificate is not a CA certificate")
    ca_public = ca_cert.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_public = ca_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if ca_public != key_public:
        raise SystemExit("The supplied CA certificate and private key do not match")
    if not isinstance(ca_key, ec.EllipticCurvePrivateKey):
        raise SystemExit("This tool currently expects the FileGuard ECDSA CA key")

    try:
        ip = ipaddress.ip_address(args.server_name)
        san = x509.SubjectAlternativeName([x509.IPAddress(ip)])
        common_name = str(ip)
    except ValueError:
        san = x509.SubjectAlternativeName([x509.DNSName(args.server_name)])
        common_name = args.server_name

    now = datetime.now(timezone.utc)
    not_before = (now - timedelta(minutes=5)).replace(tzinfo=None)
    not_after = (now + timedelta(days=args.valid_days)).replace(tzinfo=None)
    ca_expiry = ca_cert.not_valid_after_utc.replace(tzinfo=None)
    if not_after > ca_expiry:
        not_after = ca_expiry
    if not_after <= now.replace(tzinfo=None) + timedelta(days=30):
        raise SystemExit("The CA certificate expires too soon for a 30-day server certificate")

    server_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(san, critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    args.certificate_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_key_output.parent.mkdir(parents=True, exist_ok=True)
    args.certificate_output.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    args.private_key_output.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    print(f"Certificate SHA-256: {hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()}")
    print(f"Expires UTC: {not_after.isoformat()}Z")


if __name__ == "__main__":
    main()
