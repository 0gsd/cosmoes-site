# Deploying cosmoes.org to Cloud Run

One service, `cosmoes-site`, in project `i0app-010010`, region `us-central1`, beside `comprise-site` and
`comprise-connect` (which it never touches). Eight domain mappings point at it. The specifications ship in the image
(`site/specs/`, built from `specs/` by `scripts/build_specs.py`): no bucket, no secret, no environment variable. Run everything from the repository's root, in order;
each step is idempotent enough to re-run.

## 0. Names

```sh
export PROJECT=i0app-010010
export REGION=us-central1
export SERVICE=cosmoes-site
export SA_NAME=cosmoes-site
export SA=$SA_NAME@$PROJECT.iam.gserviceaccount.com
export REPO=cosmoes
export IMAGE=$REGION-docker.pkg.dev/$PROJECT/$REPO/site:$(git rev-parse --short HEAD)
export DOMAIN=cosmoes.org
export HOSTS="$DOMAIN www.$DOMAIN macro.$DOMAIN thym.$DOMAIN ascribe.$DOMAIN comprise.$DOMAIN docoes.$DOMAIN mini.$DOMAIN"

gcloud config set project $PROJECT
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iam.googleapis.com
```

## 1. The service account

The service reads nothing in the project, so its account has no role at all (an identity, so that the default
compute account is not used):

```sh
gcloud iam service-accounts create $SA_NAME --display-name="cosmoes.org (Cloud Run)"
```

## 2. Build

```sh
gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION --description="cosmoes.org images"
gcloud builds submit --tag $IMAGE .
```

`.dockerignore` keeps the tests, the venv and the markdown out of the image; `site/specs/` goes in.

## 3. Deploy

```sh
gcloud run deploy $SERVICE --image $IMAGE --region $REGION \
  --service-account $SA --allow-unauthenticated \
  --cpu 1 --memory 512Mi --concurrency 80 --min-instances 0 --max-instances 3 --timeout 60
export URL=$(gcloud run services describe $SERVICE --region $REGION --format='value(status.url)')
curl -s $URL/health                                    # {"ok":true,"edition":"0.5.4"}: up, and the edition its manifest says
curl -s $URL/ | grep -c 'class="tile"'                 # 4: the run.app address is outside the domain, so it serves the apex
curl -s $URL/raw/source.md | head -1                   # "# The OES specifications": the apex text, raw
```

`--allow-unauthenticated`: it is a public site with nothing to protect. `/healthz` is not a check here: on Cloud Run,
Google's front end answers that exact path itself with a 404 and the request never reaches the container (the service
log shows none), so the health route is `/health`.

## 4. The domain

DNS, at the registrar (Squarespace Domains), already set 2026-11-02: the apex `A` 216.239.32.21 / 216.239.34.21 /
216.239.36.21 / 216.239.38.21 and `AAAA` 2001:4860:4802:32::15 / :34::15 / :36::15 / :38::15; `CNAME
ghs.googlehosted.com` for `www`, `macro`, `thym`, `ascribe`, `comprise`, `docoes` and `mini`. Cloud Run domain
mappings need the domain verified for the gcloud account first (once, in Search Console); check, then map all eight:

```sh
gcloud domains list-user-verified                      # must list cosmoes.org; if not, stop: verify it, do not work around
for h in $HOSTS; do
  gcloud beta run domain-mappings create --service $SERVICE --domain $h --region $REGION
done
gcloud beta run domain-mappings list --region $REGION  # each host, its records (already set) and its certificate's state
```

If `create` is refused because the domain is not verified for the account, stop there: verify `cosmoes.org` for that
account (Search Console: add the property, add the account as an owner) and run the loop again. The certificates
follow on their own, minutes to an hour; `describe --domain <host>` shows `CertificateProvisioned` when one is ready.

## 5. Check

```sh
for h in macro thym ascribe comprise; do
  curl -sI https://$h.$DOMAIN/ | grep -i -e '^HTTP' -e '^cache-control' -e '^strict-transport'
  curl -s https://$h.$DOMAIN/ | grep -c '<h1'               # 1
  curl -s https://$h.$DOMAIN/robots.txt                     # Allow: / and the host's sitemap
  curl -s https://$h.$DOMAIN/sitemap.xml | grep -c '<loc>'  # 3
  curl -sI https://$h.$DOMAIN/raw/source.md | grep -i -e '^HTTP' -e '^content-type' -e '^access-control'   # 200, text/markdown, *
done
curl -s https://$DOMAIN/ | grep -c 'class="tile"'          # 4: the apex text, then the four homes
curl -s https://$DOMAIN/sitemap.xml | grep -c '<loc>'       # 15: the apex at three densities and the four hosts
curl -s https://$DOMAIN/manifest.json | grep -o '"slug"' | wc -l   # 5: every document, with each file's sha256
curl -sI https://www.$DOMAIN/atem | grep -i -e '^HTTP' -e '^location'      # 301 https://cosmoes.org/atem
curl -sI https://docoes.$DOMAIN/ | grep -i -e '^HTTP' -e '^location'       # 302 https://macro.cosmoes.org/#docs-sec-18-5
curl -sI https://mini.$DOMAIN/ | grep -i -e '^HTTP' -e '^location'         # 302 https://cosmoes.org/
```

## Updating

When a text changes (a pull request against `specs/`, CONTRIBUTING.md), build, look, commit, check, build the image,
deploy:

```sh
.venv/bin/python scripts/build_specs.py --enough ~/METMcloud/METMroot/enough-dev
.venv/bin/uvicorn cosmoes.app:app --port 8097             # look (README.md), then commit what the build wrote with the text
.venv/bin/python scripts/build_specs.py --enough ~/METMcloud/METMroot/enough-dev --check   # the commit is in step: exit 0
export IMAGE=$REGION-docker.pkg.dev/$PROJECT/$REPO/site:$(git rev-parse --short HEAD)
gcloud builds submit --tag $IMAGE .
gcloud run deploy $SERVICE --image $IMAGE --region $REGION
```

A code change deploys the same way without the build. Nothing here touches `comprise-site` or `comprise-connect`.
