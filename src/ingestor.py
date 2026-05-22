import logging
import os
import shutil

import boto3
from dotenv import load_dotenv
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.datasets.types.dataset_api_service import ApiGetDatasetRequest

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def get_dataset_current_version(dataset_id: str, api: KaggleApi | None = None) -> int:
    """Return the latest Kaggle version number for a dataset (metadata only, no download)."""
    if api is None:
        api = KaggleApi()
        api.authenticate()

    owner_slug, dataset_slug, _ = api.split_dataset_string(dataset_id)
    request = ApiGetDatasetRequest()
    request.owner_slug = owner_slug
    request.dataset_slug = dataset_slug

    with api.build_kaggle_client() as kaggle:
        dataset = kaggle.datasets.dataset_api_client.get_dataset(request)

    version = dataset.current_version_number
    logger.info(f"Latest version of {dataset_id}: {version}")
    return version


def download_kaggle_dataset(
    dataset_id, base_path, force_redownload=False
) -> tuple[list[str], int]:
    safe_folder_name = dataset_id.replace("/", "_")
    destination_dir = os.path.join(
        base_path, safe_folder_name
    )  # e.g. /tmp/datasnaek_youtube-new

    api = KaggleApi()
    api.authenticate()
    version = get_dataset_current_version(dataset_id, api=api)

    if os.path.exists(destination_dir):
        if not force_redownload:
            logger.info(
                f"Dataset already exists at {destination_dir}. Skipping download."
            )
            paths = [
                os.path.join(destination_dir, f) for f in os.listdir(destination_dir)
            ]
            return paths, version
        logger.info(
            f"Data exists, but force_redownload is True. Refreshing {destination_dir}"
        )
        shutil.rmtree(destination_dir)

    os.makedirs(destination_dir, exist_ok=True)

    pinned_dataset_id = f"{dataset_id}/{version}"
    logger.info(
        f"Downloading pinned dataset {pinned_dataset_id} to {destination_dir}"
    )
    api.dataset_download_files(pinned_dataset_id, path=destination_dir, unzip=True)
    paths = [os.path.join(destination_dir, f) for f in os.listdir(destination_dir)]
    logger.info(f"Successfully fetched {len(paths)} files.")
    return paths, version


def route_file_to_bucket(file_path, version: int):
    file_name = os.path.basename(file_path)
    region = file_name[
        :2
    ].lower()  # Extract region code from filename (e.g., 'US' -> 'us')
    is_reference_data = "_reference_data" if file_name.endswith(".json") else ""
    return (
        f"youtube/kaggle_dataset_version={version}/raw_statistics{is_reference_data}"
        f"/region={region}/{file_name}"
    )


def bucket_exists(bucket_name, s3_client):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except Exception as e:
        logger.error(f"Bucket {bucket_name} does not exist or is not accessible: {e}")
        return False
    
def lambda_handler(event, context):

    DATASET_ID = "datasnaek/youtube-new"
    INGESTION_TEMP_DIR = "/tmp/ingestion_temp"
    BRONZE_BUCKET_NAME = os.environ["BRONZE_BUCKET_NAME"]
    s3_client = boto3.client("s3")
    if not bucket_exists(BRONZE_BUCKET_NAME, s3_client):
        logger.error(
            f"Bucket {BRONZE_BUCKET_NAME} does not exist. Please create it before running the ingestor."
        )
        return {
            'statusCode': 500,
            'body': f"Bucket {BRONZE_BUCKET_NAME} does not exist. Please create it before running the ingestor."
        }
    
    try:
        file_paths, version = download_kaggle_dataset(DATASET_ID, INGESTION_TEMP_DIR)
        for file_path in file_paths:
            s3_path = route_file_to_bucket(file_path, version)
            s3_client.upload_file(file_path, BRONZE_BUCKET_NAME, s3_path)

        return {
            'statusCode': 200,
            'body': (
                f"Successfully ingested {len(file_paths)} files "
                f"(kaggle_dataset_version={version}) to S3 bucket {BRONZE_BUCKET_NAME}."
            ),
        }
    except Exception as e:
        logger.error(f"Failed to download dataset: {e}")
        return {
            'statusCode': 500,
            'body': f"Failed to download dataset: {e}"
        }
    


if __name__ == "__main__":
    load_dotenv()

    DATASET_ID = "datasnaek/youtube-new"
    INGESTION_TEMP_DIR = os.environ["INGESTION_TEMP_DIR"]
    BRONZE_BUCKET_NAME = os.environ["BRONZE_BUCKET_NAME"]
    s3_client = boto3.client("s3")
    if not bucket_exists(BRONZE_BUCKET_NAME, s3_client):
        logger.error(
            f"Bucket {BRONZE_BUCKET_NAME} does not exist. Please create it before running the ingestor."
        )
        exit(1)

    try:
        file_paths, version = download_kaggle_dataset(DATASET_ID, INGESTION_TEMP_DIR)
        for file_path in file_paths:
            s3_path = route_file_to_bucket(file_path, version)
            s3_client.upload_file(file_path, BRONZE_BUCKET_NAME, s3_path)
        logger.info(
            f"Uploaded {len(file_paths)} files under kaggle_dataset_version={version}"
        )

    except Exception as e:
        logger.error(f"Failed to download dataset: {e}")
