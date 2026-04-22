# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.test import TestCase
from django.contrib.auth import get_user_model
import tempfile
import os
from xfc_control.scripts.xfc_scan import scan_dirs, scan_directory_logic
from xfc_control.models import CachedDirectoryScan

User = get_user_model()


# Create your tests here.
"""
Test:
the scan (unit test, no django)
adding the results to the database (integration test, likely needs to be mocked)
"""


class TestScanner(TestCase):

    def test_scan_single_directory(self):
        """Test that scanning inside a single directory ignores files instead of directories"""
        with tempfile.TemporaryDirectory() as tmp:
            # create files
            file_path = os.path.join(tmp, "file.txt")
            with open(file_path, "w") as f:
                f.write("hello")  # 5 bytes

            results, _ = scan_dirs(tmp, max_workers=1)

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

            results, _ = scan_dirs(tmp, max_workers=1)

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

            results, _ = scan_dirs(tmp, max_workers=1)

            self.assertEqual(len(results), 2)

            # turn into dict for easier assertions
            result_map = {r["dir_name"]: r for r in results}

            self.assertEqual(result_map[sub1]["size"], 16)
            self.assertEqual(result_map[sub2]["size"], 5)
            

class TestScanIntegration(TestCase):

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

            scan_directory_logic(tmp, user.email)

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

            scan_directory_logic(tmp, user.email)

            self.assertEqual(CachedDirectoryScan.objects.count(), 2)

            scans = CachedDirectoryScan.objects.all()

            result_map = {s.dir_name: s for s in scans}

            self.assertEqual(result_map[sub1].size_bytes, 11)
            self.assertEqual(result_map[sub2].size_bytes, 3)

            for scan in scans:
                self.assertEqual(scan.user, user)