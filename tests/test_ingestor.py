import os
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from ingestor import (
    bucket_exists,
    download_kaggle_dataset,
    get_dataset_current_version,
    lambda_handler,
    route_file_to_bucket,
)

DATASET_ID = "datasnaek/youtube-new"


class TestRouteFileToBucket:
    def test_route_csv_file(self):
        path = route_file_to_bucket("/tmp/USvideos.csv", version=42)
        assert (
            path
            == "youtube/kaggle_dataset_version=42/raw_statistics/region=us/USvideos.csv"
        )

    def test_route_reference_json(self):
        path = route_file_to_bucket("/tmp/US_category_id.json", version=7)
        assert path == (
            "youtube/kaggle_dataset_version=7/raw_statistics_reference_data"
            "/region=us/US_category_id.json"
        )


class TestGetDatasetCurrentVersion:
    def test_returns_version_from_api(self):
        mock_api = MagicMock()
        mock_api.split_dataset_string.return_value = ("datasnaek", "youtube-new", None)

        mock_dataset = MagicMock()
        mock_dataset.current_version_number = 115

        mock_kaggle_client = MagicMock()
        mock_kaggle_client.datasets.dataset_api_client.get_dataset.return_value = (
            mock_dataset
        )
        mock_api.build_kaggle_client.return_value.__enter__.return_value = (
            mock_kaggle_client
        )

        version = get_dataset_current_version(DATASET_ID, api=mock_api)

        assert version == 115
        mock_api.authenticate.assert_not_called()
        mock_api.split_dataset_string.assert_called_once_with(DATASET_ID)
        mock_kaggle_client.datasets.dataset_api_client.get_dataset.assert_called_once()


class TestDownloadKaggleDataset:
    @patch("ingestor.KaggleApi")
    @patch("ingestor.get_dataset_current_version", return_value=99)
    def test_skips_download_when_cache_exists(
        self, mock_get_version, mock_kaggle_cls, tmp_path
    ):
        mock_api = MagicMock()
        mock_kaggle_cls.return_value = mock_api

        base = tmp_path / "ingestion"
        dest = base / "datasnaek_youtube-new"
        dest.mkdir(parents=True)
        (dest / "USvideos.csv").write_text("x")

        paths, version = download_kaggle_dataset(
            DATASET_ID, str(base), force_redownload=False
        )

        assert version == 99
        assert len(paths) == 1
        assert paths[0].endswith("USvideos.csv")
        mock_api.dataset_download_files.assert_not_called()

    @patch("ingestor.get_dataset_current_version", return_value=99)
    @patch("ingestor.KaggleApi")
    def test_downloads_pinned_dataset_id(
        self, mock_kaggle_cls, mock_get_version, tmp_path
    ):
        mock_api = MagicMock()
        mock_kaggle_cls.return_value = mock_api

        def fake_download(dataset_id, path, unzip):
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, "USvideos.csv"), "w") as f:
                f.write("x")

        mock_api.dataset_download_files.side_effect = fake_download

        base = tmp_path / "ingestion"
        paths, version = download_kaggle_dataset(DATASET_ID, str(base))

        assert version == 99
        assert len(paths) == 1
        mock_api.dataset_download_files.assert_called_once_with(
            f"{DATASET_ID}/99",
            path=os.path.join(str(base), "datasnaek_youtube-new"),
            unzip=True,
        )

    @patch("ingestor.get_dataset_current_version", return_value=99)
    @patch("ingestor.KaggleApi")
    def test_force_redownload_removes_existing_dir(
        self, mock_kaggle_cls, mock_get_version, tmp_path
    ):
        mock_api = MagicMock()
        mock_kaggle_cls.return_value = mock_api

        def fake_download(dataset_id, path, unzip):
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, "GBvideos.csv"), "w") as f:
                f.write("x")

        mock_api.dataset_download_files.side_effect = fake_download

        base = tmp_path / "ingestion"
        dest = base / "datasnaek_youtube-new"
        dest.mkdir(parents=True)
        (dest / "stale.csv").write_text("old")

        paths, version = download_kaggle_dataset(
            DATASET_ID, str(base), force_redownload=True
        )

        assert version == 99
        assert len(paths) == 1
        assert paths[0].endswith("GBvideos.csv")
        mock_api.dataset_download_files.assert_called_once()


class TestBucketExists:
    def test_returns_false_when_head_bucket_raises(self):
        mock_s3 = MagicMock()
        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadBucket",
        )

        assert bucket_exists("missing-bucket", mock_s3) is False

    @mock_aws
    def test_returns_true_when_bucket_exists(self):
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bronze-bucket")

        assert bucket_exists("test-bronze-bucket", s3) is True


class TestLambdaHandler:
    @patch.dict(os.environ, {"BRONZE_BUCKET_NAME": "my-bronze"})
    @patch("ingestor.boto3")
    @patch("ingestor.download_kaggle_dataset")
    @patch("ingestor.bucket_exists", return_value=True)
    def test_success(self, mock_bucket_exists, mock_download, mock_boto3):
        mock_download.return_value = (["/tmp/USvideos.csv"], 42)

        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        result = lambda_handler({}, None)

        assert result["statusCode"] == 200
        assert "kaggle_dataset_version=42" in result["body"]
        assert "Successfully ingested 1 files" in result["body"]
        mock_s3.upload_file.assert_called_once_with(
            "/tmp/USvideos.csv",
            "my-bronze",
            "youtube/kaggle_dataset_version=42/raw_statistics/region=us/USvideos.csv",
        )

    @patch.dict(os.environ, {"BRONZE_BUCKET_NAME": "my-bronze"})
    @patch("ingestor.boto3")
    @patch("ingestor.bucket_exists", return_value=False)
    def test_bucket_missing(self, mock_bucket_exists, mock_boto3):
        result = lambda_handler({}, None)

        assert result["statusCode"] == 500
        assert "does not exist" in result["body"]

    @patch.dict(os.environ, {"BRONZE_BUCKET_NAME": "my-bronze"})
    @patch("ingestor.boto3")
    @patch("ingestor.download_kaggle_dataset")
    @patch("ingestor.bucket_exists", return_value=True)
    def test_download_failure(self, mock_bucket_exists, mock_download, mock_boto3):
        mock_download.side_effect = RuntimeError("Kaggle unavailable")

        result = lambda_handler({}, None)

        assert result["statusCode"] == 500
        assert "Kaggle unavailable" in result["body"]
