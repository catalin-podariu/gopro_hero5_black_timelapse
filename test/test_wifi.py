from unittest import TestCase


import unittest
from unittest.mock import patch
from lib.wifi import Wifi
from lib.config import Config


class TestWifi(unittest.TestCase):

    def setUp(self):
        self.wifi = Wifi()
        self.config = Config()

    def test_check_network_reachable(self):
        # Example logic: check_network_reachable pings a host.
        # We'll patch subprocess.run (or however your code does the ping).
        with patch('subprocess.run') as mock_run:
            # Simulate a successful ping: returncode 0 means "host reachable".
            mock_run.return_value.returncode = 0
            result = self.wifi.check_network_reachable('8.8.8.8')
            self.assertTrue(result, "Expected network to be reachable when ping succeeds")

            # Now simulate a failure: returncode != 0 means "host unreachable".
            mock_run.return_value.returncode = 1
            result = self.wifi.check_network_reachable('8.8.8.8')
            self.assertFalse(result, "Expected network to be unreachable when ping fails")

    def test_ensure_wifi_connected(self):
        # Suppose this method checks the current SSID and connects if needed.
        # We'll patch some internal function or command that does the actual connect.
        with patch('subprocess.run') as mock_run:
            # Simulate successful connection
            mock_run.return_value.returncode = 0
            success = self.wifi.ensure_wifi_connected(self.config.router_config["ssid"])
            self.assertTrue(success, "Should return True when Wi-Fi connect is successful")

            # Simulate failed connection
            mock_run.return_value.returncode = 1
            success = self.wifi.ensure_wifi_connected('InvalidNetwork')
            self.assertFalse(success, "Should return False when Wi-Fi connection fails")

    def test_switch_wifi(self):
        # This might first disconnect from one SSID, then connect to another.
        # We'll patch the calls that do that.
        with patch.object(self.wifi, 'ensure_wifi_connected') as mock_connect:
            mock_connect.return_value = True
            switched = self.wifi.switch_wifi('new_ssid')
            self.assertTrue(switched, "Expected switch_wifi to return True on success")
            self.assertEqual(self.wifi.get_current_wifi(), 'new_ssid',
                             "After switching, current_wifi should match target SSID")
            mock_connect.assert_called_once_with('new_ssid')

    def test_restart_wifi(self):
        # Suppose this calls a system command like 'sudo systemctl restart network-manager'
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            result = self.wifi.restart_wifi()
            self.assertTrue(result, "Expected True when Wi-Fi restart command succeeds")

            # Now simulate a failure
            mock_run.return_value.returncode = 1
            result = self.wifi.restart_wifi()
            self.assertFalse(result, "Expected False when Wi-Fi restart fails")

    def test_keep_alive(self):
        # keep_alive might do a small action to keep the camera awake.
        # We can check that it calls the relevant system command or function.
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            result = self.wifi.keep_alive(True)
            self.assertTrue(result, "Expected keep_alive to return True on success")

            # For a negative scenario, if the keep-alive ping fails:
            mock_run.return_value.returncode = 2
            result = self.wifi.keep_alive(False)
            self.assertFalse(result, "Expected keep_alive to return False on failure")

    def test_send_wol(self):
        # send_wol might call an external library or system command
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            result = self.wifi.send_wol(self.config.gopro_config["mac"])
            self.assertTrue(result, "send_wol should return True if WOL packet is sent successfully")

            mock_run.return_value.returncode = 1
            result = self.wifi.send_wol('00:00:00:00:00:00')
            self.assertFalse(result, "send_wol should return False if sending the WOL packet fails")

    def test_choose_wifi_password(self):
        # This might just pick the password from a config. We'll confirm it uses the right one.
        self.wifi.passwords = {
            'router': 'router_secret',
            'gopro': 'gopro_secret',
            'other': 'random_secret'
        }
        pwd = self.wifi.choose_wifi_password('router')
        self.assertEqual(pwd, 'router_secret', "Should return router_secret for 'router' SSID")

        pwd = self.wifi.choose_wifi_password('unknown_ssid')
        self.assertEqual(pwd, '', "Should return empty string if SSID is unknown")

        pwd = self.wifi.choose_wifi_password('gopro')
        self.assertEqual(pwd, 'gopro_secret', "Should return gopro_secret for 'gopro' SSID")


if __name__ == '__main__':
    unittest.main()

