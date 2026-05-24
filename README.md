# Deploy ingestor image

From repo root:

```bash
export AWS_REGION=ap-southeast-2
export AWS_ACCOUNT_ID=123456789012
export ECR_REPO=youtube-ingestor
export IMAGE_TAG=latest
export ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
```

**Build**

```bash
docker build --platform linux/amd64 -t "${ECR_URI}:${IMAGE_TAG}" .
```

**ECR login**

```bash
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
```

**Push**

```bash
docker push "${ECR_URI}:${IMAGE_TAG}"
```
