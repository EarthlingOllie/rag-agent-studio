# The backend image the rehearsal pushes: the one `make images` built, plus Floci's root CA in the system bundle
# (/etc/ssl/certs/ca-certificates.crt). Floci gives its tasks no CA (ticket 23-01), and the cache's TLS and the HTTPS
# queue URLs need it; the local environment points SSL_CERT_FILE, AWS_CA_BUNDLE and REQUESTS_CA_BUNDLE at the bundle.
# scripts/deploy/rehearse.sh builds it with the CA file as the build context.
ARG IMAGE
FROM ${IMAGE}
USER root
COPY floci-root-ca.crt /usr/local/share/ca-certificates/floci-root-ca.crt
RUN update-ca-certificates
USER studio
