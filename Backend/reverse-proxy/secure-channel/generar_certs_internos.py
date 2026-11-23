"""CA de desarrollo INTERNA y certificados de los reverse proxies para el tramo WAF -> Reverse Proxy.

    pip install cryptography
    python Backend/reverse-proxy/secure-channel/generar_certs_internos.py            # crea lo que falte
    python Backend/reverse-proxy/secure-channel/generar_certs_internos.py --control-negativo

Esta CA es distinta de la de mkcert (la del certificado público de desarrollo que ven el navegador y Android):
no se instala en ningún almacén de confianza y solo la conoce el WAF (se le monta ca.crt, nunca ca.key).
Así, un certificado público de desarrollo no sirve para suplantar a un proxy en la red interna y la CA
interna no sirve para suplantar al sistema ante los clientes.

Salida (carpeta certs/internal/, ignorada por Git):
    ca/ca.crt, ca/ca.key                       CA interna (la clave no se monta en ningún contenedor)
    reverse-proxy-web/tls.crt, tls.key         SAN DNS:reverse-proxy-web     -> reverse-proxy-web
    reverse-proxy-mobile/tls.crt, tls.key      SAN DNS:reverse-proxy-mobile  -> reverse-proxy-mobile
Con --control-negativo además:
    negative-wrong-name/tls.crt, tls.key       firmado por la CA interna pero con SAN DNS:otro-servicio
                                               (el WAF debe rechazarlo por nombre: prueba de verificación)

No sobrescribe nada que ya exista (usa --renovar para regenerar los certificados de los proxies; la CA
solo se regenera borrándola a mano, porque obliga a reiniciar los WAF).
"""

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
except ImportError:
    sys.exit("Falta el paquete 'cryptography': pip install cryptography")

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = ROOT / "certs" / "internal"
PROXIES = ("reverse-proxy-web", "reverse-proxy-mobile")
CA_DAYS = 3650
LEAF_DAYS = 397  # duración máxima que aceptan los clientes modernos para certificados de servidor


def now():
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)


def write_key(path, key):
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    # Lectura para uid 101 (nginx de las imágenes) en Linux; en Windows no aplica.
    os.chmod(path, 0o644 if path.parent.name != "ca" else 0o600)


def write_cert(path, cert):
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def make_ca(ca_dir):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "InsightfulGames dev"),
                      x509.NameAttribute(NameOID.COMMON_NAME, "InsightfulGames internal dev CA (WAF -> Reverse Proxy)")])
    ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now())
            .not_valid_after(now() + dt.timedelta(days=CA_DAYS))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                         crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(ski, critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(ski), critical=False)
            .sign(key, hashes.SHA256()))
    ca_dir.mkdir(parents=True, exist_ok=True)
    write_key(ca_dir / "ca.key", key)
    write_cert(ca_dir / "ca.crt", cert)
    return key, cert


def load_ca(ca_dir):
    key = serialization.load_pem_private_key((ca_dir / "ca.key").read_bytes(), password=None)
    cert = x509.load_pem_x509_certificate((ca_dir / "ca.crt").read_bytes())
    return key, cert


def make_leaf(out_dir, dns_name, ca_key, ca_cert):
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, dns_name)]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now())
            .not_valid_after(now() + dt.timedelta(days=LEAF_DAYS))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(dns_name)]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    out_dir.mkdir(parents=True, exist_ok=True)
    write_key(out_dir / "tls.key", key)
    write_cert(out_dir / "tls.crt", cert)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="carpeta de salida (por defecto certs/internal)")
    ap.add_argument("--renovar", action="store_true", help="regenera los certificados de los proxies (no la CA)")
    ap.add_argument("--control-negativo", action="store_true",
                    help="crea también negative-wrong-name/ (CA interna, nombre equivocado) para la prueba de rechazo")
    args = ap.parse_args()
    out = args.out.resolve()
    ca_dir = out / "ca"

    if (ca_dir / "ca.key").is_file() and (ca_dir / "ca.crt").is_file():
        ca_key, ca_cert = load_ca(ca_dir)
        print(f"CA interna existente: {ca_dir / 'ca.crt'}")
    else:
        if (ca_dir / "ca.crt").exists() or (ca_dir / "ca.key").exists():
            sys.exit(f"{ca_dir} tiene solo uno de ca.crt / ca.key: revísalo a mano (no se sobrescribe).")
        ca_key, ca_cert = make_ca(ca_dir)
        print(f"CA interna creada: {ca_dir / 'ca.crt'}")

    targets = [(name, name) for name in PROXIES]
    if args.control_negativo:
        targets.append(("negative-wrong-name", "otro-servicio"))
    for folder, dns_name in targets:
        d = out / folder
        if (d / "tls.crt").is_file() and (d / "tls.key").is_file() and not args.renovar:
            print(f"existente:  {d} (usa --renovar para regenerarlo)")
            continue
        make_leaf(d, dns_name, ca_key, ca_cert)
        print(f"creado:     {d / 'tls.crt'}  (SAN DNS:{dns_name})")

    print("\nMonta solo ca/ca.crt en los WAF; ca/ca.key no sale de esta máquina ni entra en Git.")


if __name__ == "__main__":
    main()
