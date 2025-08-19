#!/bin/bash

# Exit on error
set -e

# Check if required environment variables are set
if [ -z "$TS_CLIENT_ID" ] || [ -z "$TS_CLIENT_SECRET" ] || [ -z "$TS_OP_TAG" ] || [ -z "$TS_HOSTNAME" ] || [ -z "$CRS_API_HOSTNAME" ]; then
  echo "Error: Required environment variables not set"
  echo "Please ensure TS_CLIENT_ID, TS_CLIENT_SECRET, TS_OP_TAG, TS_HOSTNAME and CRS_API_HOSTNAME are set"
  exit 1
fi

# Add Tailscale Helm repository
helm repo add tailscale https://pkgs.tailscale.com/helmcharts
helm repo update

echo -e "Installing Tailscale operator"
echo -e "This may take a while..."
echo -e "TS_CLIENT_ID: $TS_CLIENT_ID"
echo -e "TS_CLIENT_SECRET: $TS_CLIENT_SECRET"
echo -e "TS_DEFAULT_TAGS: $TS_OP_TAG"
echo -e "TS_HOSTNAME: $TS_HOSTNAME"
echo -e "CRS_API_HOSTNAME: $CRS_API_HOSTNAME"

# Install Tailscale operator
helm upgrade \
  --install \
  tailscale-operator \
  tailscale/tailscale-operator \
  --namespace=tailscale \
  --create-namespace \
  --set-string oauth.clientId="$TS_CLIENT_ID" \
  --set-string oauth.clientSecret="$TS_CLIENT_SECRET" \
  --set-string operatorConfig.defaultTags="$TS_OP_TAG" \
  --set-string operatorConfig.hostname="$TS_HOSTNAME" \
  --set-string proxyConfig.defaultTags="$TS_OP_TAG" \
  --wait

kubectl apply -f dnsconfig.yaml

echo -e "Waiting for the service nameserver to exist"
timeout 5m bash -c "until kubectl get svc -n tailscale nameserver > /dev/null 2>&1; do sleep 1; done" || echo -e "Error: nameserver failed to exist within 5 minutes"

echo -e "Waiting for nameserver to have a valid ClusterIP"
timeout 5m bash -c "until kubectl get svc -n tailscale nameserver -o jsonpath='{.spec.clusterIP}' | grep -v '<none>' > /dev/null 2>&1; do sleep 1; done" || echo -e "Error: nameserver failed to obtain a valid CLusterIP within 5 minutes"

TS_DNS_IP=$(kubectl get svc -n tailscale nameserver -o jsonpath='{.spec.clusterIP}')

TMP_FILE=$(mktemp)
cat coredns.yaml | sed "s/\${TS_DNS_IP}/${TS_DNS_IP}/g" >"$TMP_FILE"
kubectl apply -f "$TMP_FILE"
rm "$TMP_FILE"

echo -e "Restarting CoreDNS deployment"
kubectl delete pod -n kube-system -l k8s-app=kube-dns

echo -e "Waiting for CoreDNS to be ready"
timeout 5m bash -c "until kubectl get pods -n kube-system -l k8s-app=kube-dns -o jsonpath='{.items[0].status.phase}' | grep -q Running; do sleep 1; done" || echo -e "Error: CoreDNS failed to start within 5 minutes"

