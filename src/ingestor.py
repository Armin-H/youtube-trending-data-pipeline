import logging
import os
import shutil

import boto3
from dotenv import load_dotenv
from kaggle.api.kaggle_api_extended import KaggleApi

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ToDo : download the dataset metadata and log the dataset version
def download_kaggle_dataset(dataset_id, base_path, force_redownload=False):
    # owner_slug, dataset_slug = dataset_id.split("/")

    safe_folder_name = dataset_id.replace("/", "_")
    destination_dir = os.path.join(
        base_path, safe_folder_name
    )  # e.g. /tmp/datasnaek_youtube-new

    if os.path.exists(destination_dir):
        if not force_redownload:
            logger.info(
                f"Dataset already exists at {destination_dir}. Skipping download."
            )
            return [
                os.path.join(destination_dir, f) for f in os.listdir(destination_dir)
            ]
        else:
            logger.info(
                f"Data exists, but force_redownload is True. Refreshing {destination_dir}"
            )
            shutil.rmtree(destination_dir)

    os.makedirs(destination_dir, exist_ok=True)

    api = KaggleApi()
    api.authenticate()

    logger.info(f"Downloading {dataset_id} to {destination_dir}")
    api.dataset_download_files(dataset_id, path=destination_dir, unzip=True)
    paths = [os.path.join(destination_dir, f) for f in os.listdir(destination_dir)]
    logger.info(f"Successfully fetched {len(paths)} files.")
    return paths


def route_file_to_bucket(file_path):
    file_name = os.path.basename(file_path)
    region = file_name[
        :2
    ].lower()  # Extract region code from filename (e.g., 'US' -> 'us')
    is_reference_data = "_reference_data" if file_name.endswith(".json") else ""
    return f"youtube/raw_statistics{is_reference_data}/region={region}/{file_name}"


def bucket_exists(bucket_name, s3_client):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except Exception as e:
        logger.error(f"Bucket {bucket_name} does not exist or is not accessible: {e}")
        return False


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
        file_paths = download_kaggle_dataset(DATASET_ID, INGESTION_TEMP_DIR)
        for file_path in file_paths:
            s3_path = route_file_to_bucket(file_path)
            s3_client.upload_file(file_path, BRONZE_BUCKET_NAME, s3_path)

    except Exception as e:
        logger.error(f"Failed to download dataset: {e}")
