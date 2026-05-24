#!/usr/bin/env bash
set -e # exit on error
cd "$(dirname "$0")"

set -a
# shellcheck disable=SC1091
source .env
set +a

AWS_REGION="${AWS_REGION:-$BUCKET_REGION}"
repo="${ECR_REPO:-youtube-ingestor}"
tag="${1:?Usage: $0 <tag>}"
uri="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${repo}"

docker build --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  -t "${uri}:${tag}" .
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
docker push "${uri}:${tag}"

echo "${uri}:${tag}"
