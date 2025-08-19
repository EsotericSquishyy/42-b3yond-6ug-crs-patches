#!/bin/bash

cd ../b3yond-crs
helm dependency update
helm uninstall dev

# wait 2 seconds
sleep 2
for pod in $(kubectl get pods | grep dev | awk '{print $1}'); do
    kubectl delete pod $pod --grace-period=0 --force
done

helm install dev . -f secret-values.yaml