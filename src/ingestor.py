import logging
import os
import shutil

from dotenv import load_dotenv
from kaggle.api.kaggle_api_extended import KaggleApi

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def download_kaggle_dataset(dataset_id, base_path, force_redownload=False):
    # owner_slug, dataset_slug = dataset_id.split("/")

    safe_folder_name = dataset_id.replace("/", "_")
    destination_dir = os.path.join(base_path, safe_folder_name)

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


if __name__ == "__main__":
    load_dotenv()

    DATASET_ID = "datasnaek/youtube-new"
    INGESTION_TEMP_DIR = os.environ["INGESTION_TEMP_DIR"]
    try:
        file_paths = download_kaggle_dataset(DATASET_ID, INGESTION_TEMP_DIR)
    except Exception as e:
        logger.error(f"Failed to download dataset: {e}")
