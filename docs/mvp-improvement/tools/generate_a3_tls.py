"""One-time local fixture generation with OpenSSL. No runtime/provider credentials involved.

Run from /app in the dev container. Tests consume the checked-in synthetic PEM files and do not
need OpenSSL. The temporary CA signing key is destroyed; the leaf key is deliberately public.
"""

import subprocess
import tempfile
from pathlib import Path

out = Path("tests/support/provider_tls")
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="a3-test-ca-") as folder:
    tmp = Path(folder)

    def run(*args: str) -> None:
        subprocess.run(["openssl", *args], cwd=tmp, check=True, capture_output=True)

    run(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "7300",
        "-subj",
        "/CN=AUD03 synthetic test CA",
        "-addext",
        "keyUsage=critical,keyCertSign,cRLSign",
        "-keyout",
        "ca.key",
        "-out",
        "ca.pem",
    )
    run(
        "req",
        "-new",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        "/CN=localhost",
        "-keyout",
        "fixture-key.pem",
        "-out",
        "leaf.csr",
    )
    (tmp / "index.txt").touch()
    (tmp / "serial").write_text("1000\n")
    (tmp / "ca.conf").write_text("""[ca]
default_ca=authority
[authority]
unique_subject=no
database=index.txt
serial=serial
new_certs_dir=.
default_md=sha256
policy=policy
[policy]
commonName=supplied
[valid]
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1
[wrong]
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid,issuer
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:wrong.example.test
""")
    for name, extension, end in [
        ("valid", "valid", "20450101000000Z"),
        ("expired", "valid", "20200102000000Z"),
        ("wrong", "wrong", "20450101000000Z"),
    ]:
        run(
            "ca",
            "-batch",
            "-config",
            "ca.conf",
            "-cert",
            "ca.pem",
            "-keyfile",
            "ca.key",
            "-in",
            "leaf.csr",
            "-out",
            name + ".pem",
            "-startdate",
            "20200101000000Z",
            "-enddate",
            end,
            "-extensions",
            extension,
            "-notext",
        )
    for name in ["ca.pem", "fixture-key.pem", "valid.pem", "expired.pem", "wrong.pem"]:
        (out / name).write_bytes((tmp / name).read_bytes())
print("Generated synthetic CA/leaf fixtures; CA signing key discarded.")
