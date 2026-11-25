# Synthetic TLS fixtures — never use for a real service

These public test certificates and the deliberately public leaf private key are for loopback-only
tests. They are not provider/runtime credentials. The temporary CA signing key was discarded.
`valid.pem` and `wrong.pem` expire on 1 January 2045; `expired.pem` expired on 2 January 2020.
The synthetic CA was generated for this test run with a 7,300-day lifetime. `wrong.pem` has an
unrelated DNS SAN. No test changes a system trust store or disables verification.

Tests explicitly supply a verifying SSLContext trusting `ca.pem` to the injected test transport;
the application configuration offers no TLS-verification bypass. Default transports must reject
this CA. Generate replacement fixtures only if needed, using
`docs/mvp-improvement/tools/generate_a3_tls.py` from `/app` in the local dev container.
