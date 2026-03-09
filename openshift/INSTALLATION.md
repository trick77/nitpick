# Nitpick OpenShift Deployment

## Prerequisites

- `oc` CLI installed and logged in to the cluster
- A project/namespace to deploy into

## 1. Create project

```bash
oc new-project nitpick
```

## 2. Create the secret

```bash
oc create secret generic nitpick \
  --from-literal=BITBUCKET_URL=https://bitbucket.company.com \
  --from-literal=BITBUCKET_TOKEN=<your-token> \
  --from-literal=BITBUCKET_WEBHOOK_SECRET=<your-secret> \
  --from-literal=GITHUB_TOKEN=<your-token> \
  --from-literal=REVIEW_ALLOWED_AUTHORS=user1,user2
```

## 3. Apply manifests

```bash
oc apply -f openshift/
```

## 4. Build the image

From the repository root:

```bash
oc start-build nitpick --from-dir=. --follow
```

The build uploads the repo contents to the cluster which builds the image using the `Containerfile`. The deployment rolls out automatically when the build completes.

## 5. Verify

```bash
oc get pods
oc logs deploy/nitpick
curl https://$(oc get route nitpick -o jsonpath='{.spec.host}')/health
```

Expected health response: `{"status": "ok"}`

## 6. Configure Bitbucket webhook

In Bitbucket Server, add a webhook pointing to:

```
https://<route-host>/webhook
```

The route host can be retrieved with:

```bash
oc get route nitpick -o jsonpath='{.spec.host}'
```

## Rebuilding

After code changes, trigger a new build:

```bash
oc start-build nitpick --from-dir=. --follow
```

The deployment rolls out the new image automatically.
