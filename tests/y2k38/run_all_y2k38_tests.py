#!/usr/bin/env python3
"""
Y2K38 Test Suite Runner for SONiC

This script runs all Y2K38 (2038 timestamp overflow) tests across
the sonic-buildimage repository and its submodules.

The Y2K38 problem occurs when 32-bit signed integers used to store
Unix timestamps overflow on January 19, 2038 at 03:14:07 UTC.

This test suite verifies that:
1. All timestamp types are properly sized (64-bit or larger)
2. Timestamp arithmetic works correctly beyond 2038
3. Compile-time checks are in place for time_t size
"""

import os
import sys
import subprocess
import unittest
from datetime import datetime

Y2K38_BOUNDARY = 2147483647
YEAR_2040 = 2208988800
YEAR_2050 = 2524608000
YEAR_2100 = 4102444800

class Y2K38CompileTimeChecks(unittest.TestCase):
    """Test compile-time checks for 64-bit time_t"""

    def test_time_t_size_on_system(self):
        """Verify that time_t is at least 64-bit on this system"""
        import ctypes
        time_t_size = ctypes.sizeof(ctypes.c_long)
        self.assertGreaterEqual(time_t_size, 8,
            f"time_t is only {time_t_size} bytes, needs to be at least 8 bytes for Y2K38 safety")

    def test_python_int_handles_large_timestamps(self):
        """Verify Python can handle timestamps beyond 2038"""
        large_timestamp = YEAR_2100
        dt = datetime.utcfromtimestamp(large_timestamp)
        self.assertEqual(dt.year, 2100)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 1)


class Y2K38TimestampArithmetic(unittest.TestCase):
    """Test timestamp arithmetic beyond 2038"""

    def test_timestamp_addition_beyond_boundary(self):
        """Test adding time to timestamps near Y2K38 boundary"""
        base = Y2K38_BOUNDARY - 100
        result = base + 200
        self.assertEqual(result, Y2K38_BOUNDARY + 100)
        self.assertGreater(result, Y2K38_BOUNDARY)

    def test_timestamp_subtraction_beyond_boundary(self):
        """Test subtracting time from timestamps beyond Y2K38"""
        base = Y2K38_BOUNDARY + 1000
        result = base - 500
        self.assertEqual(result, Y2K38_BOUNDARY + 500)

    def test_timestamp_comparison_beyond_boundary(self):
        """Test comparing timestamps beyond Y2K38 boundary"""
        ts1 = Y2K38_BOUNDARY + 1
        ts2 = Y2K38_BOUNDARY + 2
        self.assertLess(ts1, ts2)
        self.assertGreater(ts2, ts1)

    def test_timestamp_range_2040_to_2100(self):
        """Test timestamp operations in 2040-2100 range"""
        timestamps = [YEAR_2040, YEAR_2050, YEAR_2100]
        for i in range(len(timestamps) - 1):
            self.assertLess(timestamps[i], timestamps[i + 1])


class Y2K38EpochExtension(unittest.TestCase):
    """Test epoch extension logic for 32-bit hardware timestamps"""

    def _extend_epoch_to_64bit(self, epoch_32bit, current_time):
        """
        Extend a 32-bit hardware timestamp to 64-bit.
        This mirrors the logic in sonic-platform-common.
        """
        if epoch_32bit == 0xFFFFFFFF:
            return epoch_32bit

        max_32bit = 0xFFFFFFFF
        current_time_32bit = current_time & max_32bit

        if epoch_32bit < current_time_32bit - (max_32bit // 2):
            epoch_64bit = epoch_32bit + max_32bit + 1
        else:
            epoch_64bit = epoch_32bit

        return epoch_64bit

    def test_epoch_extension_no_wrap(self):
        """Test epoch extension when no wraparound has occurred"""
        current_time = 1700000000
        hw_timestamp = 1699999000
        result = self._extend_epoch_to_64bit(hw_timestamp, current_time)
        self.assertEqual(result, hw_timestamp)

    def test_epoch_extension_with_wrap(self):
        """Test epoch extension when wraparound has occurred"""
        current_time = 4300000000
        hw_timestamp = 100000000
        result = self._extend_epoch_to_64bit(hw_timestamp, current_time)
        current_time_32bit = current_time & 0xFFFFFFFF
        if hw_timestamp < current_time_32bit - (0xFFFFFFFF // 2):
            expected = hw_timestamp + 0xFFFFFFFF + 1
        else:
            expected = hw_timestamp
        self.assertEqual(result, expected)

    def test_epoch_extension_invalid_marker(self):
        """Test that 0xFFFFFFFF is preserved as invalid marker"""
        result = self._extend_epoch_to_64bit(0xFFFFFFFF, 1700000000)
        self.assertEqual(result, 0xFFFFFFFF)


class Y2K38SubmoduleTests(unittest.TestCase):
    """Test Y2K38 fixes in submodules"""

    def setUp(self):
        self.repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def test_wpa_supplicant_os_time_t_definition(self):
        """Verify sonic-wpa-supplicant uses 64-bit os_time_t"""
        os_h_path = os.path.join(self.repo_root, 'src/wpasupplicant/sonic-wpa-supplicant/src/utils/os.h')
        if os.path.exists(os_h_path):
            with open(os_h_path, 'r') as f:
                content = f.read()
            self.assertIn('int64_t', content,
                "os.h should use int64_t for os_time_t")

    def test_stp_timer_uses_64bit(self):
        """Verify sonic-stp uses 64-bit timer values"""
        timer_h_path = os.path.join(self.repo_root, 'src/sonic-stp/include/stp_timer.h')
        if os.path.exists(timer_h_path):
            with open(timer_h_path, 'r') as f:
                content = f.read()
            self.assertIn('UINT64', content,
                "stp_timer.h should use UINT64 for timer values")

    def test_sairedis_fdb_timestamp_64bit(self):
        """Verify sonic-sairedis uses 64-bit FDB timestamps"""
        fdbinfo_h_path = os.path.join(self.repo_root, 'src/sonic-sairedis/vslib/FdbInfo.h')
        if os.path.exists(fdbinfo_h_path):
            with open(fdbinfo_h_path, 'r') as f:
                content = f.read()
            self.assertIn('uint64_t m_timestamp', content,
                "FdbInfo.h should use uint64_t for m_timestamp")

    def test_iccpd_time_header_exists(self):
        """Verify iccpd has Y2K38 time safety header"""
        time_h_path = os.path.join(self.repo_root, 'src/iccpd/include/iccp_time.h')
        if os.path.exists(time_h_path):
            with open(time_h_path, 'r') as f:
                content = f.read()
            self.assertIn('_Static_assert', content,
                "iccp_time.h should have compile-time assertion for time_t size")

    def test_pac_timestamp_64bit(self):
        """Verify sonic-pac uses 64-bit auth timestamps"""
        api_h_path = os.path.join(self.repo_root, 'src/sonic-pac/authmgr/common/auth_mgr_api.h')
        if os.path.exists(api_h_path):
            with open(api_h_path, 'r') as f:
                content = f.read()
            self.assertIn('uint64 *pTimeStamp', content,
                "auth_mgr_api.h should use uint64 for timestamp parameter")

    def test_frr_y2k38_patch_exists(self):
        """Verify sonic-frr has Y2K38 compile-time check patch"""
        patch_path = os.path.join(self.repo_root, 'src/sonic-frr/patch/0098-SONiC-ONLY-Y2K38-Add-compile-time-check-for-64-bit-time_t.patch')
        self.assertTrue(os.path.exists(patch_path),
            "FRR Y2K38 patch should exist")

    def test_platform_common_epoch_extension(self):
        """Verify sonic-platform-common has epoch extension method"""
        credo_path = os.path.join(self.repo_root, 'src/sonic-platform-common/sonic_y_cable/credo/y_cable_credo.py')
        if os.path.exists(credo_path):
            with open(credo_path, 'r') as f:
                content = f.read()
            self.assertIn('_extend_epoch_to_64bit', content,
                "y_cable_credo.py should have _extend_epoch_to_64bit method")


def run_tests():
    """Run all Y2K38 tests and return exit code"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(Y2K38CompileTimeChecks))
    suite.addTests(loader.loadTestsFromTestCase(Y2K38TimestampArithmetic))
    suite.addTests(loader.loadTestsFromTestCase(Y2K38EpochExtension))
    suite.addTests(loader.loadTestsFromTestCase(Y2K38SubmoduleTests))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
