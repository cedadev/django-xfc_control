# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.test import TestCase
from django.contrib.auth import get_user_model
import tempfile
import os
from xfc_control.scripts.xfc_scan import scan_dirs, scan_directory_logic, scan_directory, send_scan_request, handle_message
from xfc_control.models import CachedDirectoryScan
from click.testing import CliRunner
from unittest.mock import patch
import pika
import json
import time
from unittest.mock import MagicMock

User = get_user_model()


# Create your tests here.
"""
python manage.py test

docker containing rabbits is required for integration tests
"""


class TestScannerFunctionality(TestCase):

    def test_scan_single_directory(self):
        """Test that scanning inside a single directory ignores files instead of directories"""
        with tempfile.TemporaryDirectory() as tmp:
            # create files
            file_path = os.path.join(tmp, "file.txt")
            with open(file_path, "w") as f:
                f.write("hello")  # 5 bytes

            results, _ = scan_dirs(tmp, "default", max_workers=1)

            self.assertEqual(len(results), 0)
    
    def test_scan_subdirectory_size(self):
        """Test that scanning a directory with a subdirectory correctly sums the sizes of files in the subdirectory"""
        with tempfile.TemporaryDirectory() as tmp:
            file_path = os.path.join(tmp, "file.txt")
            with open(file_path, "w") as f:
                f.write("ignore")  # 6 bytes
            sub = os.path.join(tmp, "subdir")
            os.mkdir(sub)

            with open(os.path.join(sub, "file.txt"), "w") as f:
                f.write("hello")  # 5 bytes
            with open(os.path.join(sub, "file2.txt"), "w") as f:
                f.write("world.")  # 6 bytes
            
            # nested directory
            nested = os.path.join(sub, "nested")
            os.mkdir(nested)

            with open(os.path.join(nested, "inner.txt"), "w") as f:
                f.write("stuff")  # 5 bytes
            
            empty = os.path.join(sub, "empty")
            os.mkdir(empty)

            results, _ = scan_dirs(tmp, "default", max_workers=1)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["size"], 16)
            self.assertTrue(results[0]["dir_name"].endswith("subdir"))
    
    def test_scan_multiple_directories(self):
        """Test that scanning a directory with multiple subdirectories correctly returns results for both directories with the correct sizes"""
        with tempfile.TemporaryDirectory() as tmp:
            # ---- subdir1 ----
            sub1 = os.path.join(tmp, "subdir1")
            os.mkdir(sub1)

            with open(os.path.join(sub1, "file.txt"), "w") as f:
                f.write("hello")  # 5 bytes

            with open(os.path.join(sub1, "file2.txt"), "w") as f:
                f.write("world.")  # 6 bytes

            nested = os.path.join(sub1, "nested")
            os.mkdir(nested)

            with open(os.path.join(nested, "inner.txt"), "w") as f:
                f.write("stuff")  # 5 bytes

            # total = 16

            # ---- subdir2 ----
            sub2 = os.path.join(tmp, "subdir2")
            os.mkdir(sub2)

            with open(os.path.join(sub2, "a.txt"), "w") as f:
                f.write("what?")  # 5 bytes

            results, _ = scan_dirs(tmp, "default", max_workers=1)

            self.assertEqual(len(results), 2)

            # turn into dict for easier assertions
            result_map = {r["dir_name"]: r for r in results}

            self.assertEqual(result_map[sub1]["size"], 16)
            self.assertEqual(result_map[sub2]["size"], 5)
    
    def test_scan_nonexistant_directory(self):
        """Test scanning a directory that doesn't exist"""
        with self.assertRaises(FileNotFoundError):
            results, _ = scan_dirs("/path/that/doesnt/exist/8764ertyfgut76rtf6t7ujhyf", "default", max_workers=1)
        
            

class TestScanDatabase(TestCase):

    def test_scan_creates_db_entries(self):
        """Test that scanning a directory creates the expected database entries"""
        user = User.objects.create(email="test@example.com")

        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "subdir")
            os.mkdir(sub)

            with open(os.path.join(sub, "file.txt"), "w") as f:
                f.write("hello")  # 5 bytes
            with open(os.path.join(sub, "file2.txt"), "w") as f:
                f.write("world.")  # 6 bytes

            scan_directory_logic(tmp, user.email, "default")

            self.assertEqual(CachedDirectoryScan.objects.count(), 1)

            scan = CachedDirectoryScan.objects.first()
            self.assertEqual(scan.user, user)
            self.assertEqual(scan.size_bytes, 11)
            self.assertTrue(scan.dir_name.endswith("subdir"))
            self.assertIsNotNone(scan.scan_time)
            self.assertIsNotNone(scan.dir_mtime)
    
    def test_scan_multiple_directories_db(self):
        """Test that scanning a directory with multiple subdirectories creates the expected database entries"""
        user = User.objects.create(email="test@example.com")

        with tempfile.TemporaryDirectory() as tmp:
            # subdir1
            sub1 = os.path.join(tmp, "subdir1")
            os.mkdir(sub1)

            with open(os.path.join(sub1, "file.txt"), "w") as f:
                f.write("hello")  # 5

            with open(os.path.join(sub1, "file2.txt"), "w") as f:
                f.write("world.")  # 6

            # subdir2
            sub2 = os.path.join(tmp, "subdir2")
            os.mkdir(sub2)

            with open(os.path.join(sub2, "a.txt"), "w") as f:
                f.write("abc")  # 3

            scan_directory_logic(tmp, user.email, "default")

            self.assertEqual(CachedDirectoryScan.objects.count(), 2)

            scans = CachedDirectoryScan.objects.all()

            result_map = {s.dir_name: s for s in scans}

            self.assertEqual(result_map[sub1].size_bytes, 11)
            self.assertEqual(result_map[sub2].size_bytes, 3)

            for scan in scans:
                self.assertEqual(scan.user, user)
    
    def test_scan_wrong_email(self):
        user = User.objects.create(email="test@example.com")

        with tempfile.TemporaryDirectory() as tmp:
            # subdir1
            sub1 = os.path.join(tmp, "subdir1")
            os.mkdir(sub1)
            
            with open(os.path.join(sub1, "file.txt"), "w") as f:
                f.write("hello")  # 5
            
            with self.assertRaises(ValueError):
                scan_directory_logic(tmp, "fake.email@example.com", "default")


class TestScannerIntegration(TestCase):
    """
    Integration tests are different to unit tests
    https://www.testrail.com/blog/unit-testing-vs-integration-testing/
    
    Require the user to docker with rabbits on (or the test will fail)
    """

    def test_cli_rabbit_flag(self):
        runner = CliRunner()

        result = runner.invoke(scan_directory, [
            "--path", "/tmp",
            "--email", "test@example.com",
            "--rabbit"
        ])

        assert result.exit_code == 0
        
    @patch("xfc_control.scripts.xfc_scan.pika.BlockingConnection")
    def test_send_no_connection(self, mock_conn):
        mock_conn.side_effect = Exception("Connection failed")

        with self.assertRaises(Exception):
            send_scan_request("a", "b", "default")
    
    def test_producer_success(self):
        send_scan_request("test@example.com", "/tmp", "default")

        connection = pika.BlockingConnection(
            pika.ConnectionParameters("localhost")
        )
        channel = connection.channel()
        channel.queue_declare(queue="scanner_request", durable=True)

        method, _, body = None, None, None

        for _ in range(5):
            method, _, body = channel.basic_get(queue="scanner_request")
            if method:
                break
            time.sleep(0.2)

        self.assertIsNotNone(method)

        msg = json.loads(body)
        self.assertEqual(msg["email"], "test@example.com")
        self.assertEqual(msg["work_dir"], "/tmp")

        channel.basic_ack(method.delivery_tag)
        connection.close()

    def test_consumer_success(self):
        user = User.objects.create(email="test@example.com")

        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "subdir")
            os.mkdir(sub)

            with open(os.path.join(sub, "file.txt"), "w") as f:
                f.write("hello")

            body = json.dumps({
                "email": user.email,
                "work_dir": tmp
            })

            mock_channel = MagicMock()
            mock_method = MagicMock()
            mock_method.delivery_tag = 123

            handle_message(mock_channel, mock_method, body)

            mock_channel.basic_ack.assert_called_once()
            self.assertEqual(CachedDirectoryScan.objects.count(), 1)
    
    def test_consumer_missing_email(self):
        body = json.dumps({"work_dir": "/tmp"})

        mock_channel = MagicMock()
        mock_method = MagicMock()
        mock_method.delivery_tag = 1

        handle_message(mock_channel, mock_method, body)

        mock_channel.basic_nack.assert_called_once()
